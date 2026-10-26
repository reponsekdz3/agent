import json
import os
import ctypes
import tempfile
from ctypes import wintypes
from pathlib import Path
from typing import Any, Dict, Optional, List
from datetime import datetime
from nova_apex.config.settings import settings
from nova_apex.core.logger import agent_logger

_DPAPI_HEADER = b"NOVA-APEX-DPAPI-V1\n"

class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte))
    ]

def _dpapi_transform(data: bytes, protect: bool) -> bytes:
    if os.name != "nt":
        raise RuntimeError("Windows DPAPI is required to protect the credential vault.")

    crypt32 = ctypes.WinDLL("Crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("Kernel32", use_last_error=True)
    source = ctypes.create_string_buffer(data)
    source_blob = _DataBlob(
        len(data),
        ctypes.cast(source, ctypes.POINTER(ctypes.c_byte))
    )
    output_blob = _DataBlob()

    if protect:
        operation = crypt32.CryptProtectData
        operation.argtypes = [
            ctypes.POINTER(_DataBlob), wintypes.LPCWSTR, ctypes.POINTER(_DataBlob),
            ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DataBlob)
        ]
        operation.restype = wintypes.BOOL
        succeeded = operation(
            ctypes.byref(source_blob), "NOVA-APEX credential vault",
            None, None, None, 0, ctypes.byref(output_blob)
        )
    else:
        description = wintypes.LPWSTR()
        operation = crypt32.CryptUnprotectData
        operation.argtypes = [
            ctypes.POINTER(_DataBlob), ctypes.POINTER(wintypes.LPWSTR),
            ctypes.POINTER(_DataBlob), ctypes.c_void_p, ctypes.c_void_p,
            wintypes.DWORD, ctypes.POINTER(_DataBlob)
        ]
        operation.restype = wintypes.BOOL
        succeeded = operation(
            ctypes.byref(source_blob), ctypes.byref(description),
            None, None, None, 0, ctypes.byref(output_blob)
        )
        if description:
            kernel32.LocalFree.argtypes = [ctypes.c_void_p]
            kernel32.LocalFree(description)

    if not succeeded:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree(output_blob.pbData)

class AgentMemory:
    """
    Persistent dual-tier memory system:
    1. Working Memory (ephemeral context, step variables, scratchpad)
    2. Long-term Knowledge Vault (credentials, created accounts, system variables, successful recipes)
    """
    def __init__(self, persistence_file: Optional[Path] = None):
        self.persistence_file = persistence_file or (settings.artifacts_dir / "agent_memory_vault.json")
        self.working_memory: Dict[str, Any] = {}
        self.vault: Dict[str, Any] = {
            "credentials": [],
            "created_accounts": [],
            "saved_entities": {},
            "learned_patterns": {},
            "execution_notes": []
        }
        self.load()

    def set_working(self, key: str, value: Any):
        self.working_memory[key] = value

    def get_working(self, key: str, default: Any = None) -> Any:
        return self.working_memory.get(key, default)

    def store_credential(self, service: str, username: str, secret: str, extra: Dict[str, Any] = None):
        extra_data = extra or {}
        entry = {
            "service": service,
            "username": username,
            "secret": secret,
            "extra": extra_data,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.vault["credentials"].append(entry)
        if extra_data.get("status") != "draft":
            self.vault["created_accounts"].append({
                "service": service,
                "username": username,
                "timestamp": entry["timestamp"]
            })
        self.save()
        agent_logger.success(f"Vault stored new credential for [{service}]", domain="MEMORY")

    def get_credentials_for(self, service: str) -> Optional[Dict[str, Any]]:
        for cred in reversed(self.vault["credentials"]):
            if cred["service"].lower() == service.lower():
                return cred
        return None

    def store_entity(self, key: str, value: Any):
        self.vault["saved_entities"][key] = {
            "value": value,
            "updated_at": datetime.utcnow().isoformat()
        }
        self.save()

    def get_entity(self, key: str, default: Any = None) -> Any:
        entry = self.vault["saved_entities"].get(key)
        return entry["value"] if entry else default

    def resolve_placeholders(self, text: str) -> str:
        """
        Resolves `${key}` patterns against working memory and vault
        """
        if not text or not isinstance(text, str):
            return text

        # Check working memory
        for k, v in self.working_memory.items():
            token = f"${{{k}}}"
            if token in text:
                text = text.replace(token, str(v))

        # Check vault entities
        for k, v in self.vault.get("saved_entities", {}).items():
            token = f"${{{k}}}"
            if token in text:
                text = text.replace(token, str(v.get("value", "")))

        return text

    def save(self):
        temporary_path = None
        try:
            serialized = json.dumps(self.vault, indent=2).encode("utf-8")
            if os.name == "nt":
                protected = _dpapi_transform(serialized, protect=True)
                contents = _DPAPI_HEADER + protected
            else:
                contents = serialized
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=self.persistence_file.parent,
                prefix=f".{self.persistence_file.name}.",
                suffix=".tmp",
                delete=False
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(contents)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, self.persistence_file)
        except Exception as e:
            if temporary_path and temporary_path.exists():
                temporary_path.unlink()
            agent_logger.error(f"Failed to persist memory vault: {e}", domain="MEMORY")
            raise

    def load(self):
        if self.persistence_file.exists():
            try:
                contents = self.persistence_file.read_bytes()
                if contents.startswith(_DPAPI_HEADER):
                    contents = _dpapi_transform(contents[len(_DPAPI_HEADER):], protect=False)
                self.vault.update(json.loads(contents.decode("utf-8")))
            except Exception as e:
                agent_logger.error(f"Unable to load credential vault safely: {e}", domain="MEMORY")
                raise RuntimeError("Credential vault could not be read; refusing to start with an empty vault.") from e
            else:
                if os.name == "nt" and not self.persistence_file.read_bytes().startswith(_DPAPI_HEADER):
                    self.save()

agent_memory = AgentMemory()
