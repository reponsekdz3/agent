import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime
from nova_apex.config.settings import settings
from nova_apex.core.logger import agent_logger


class AgentMemory:
    """Working memory plus a persistent metadata-only account vault.

    Credential secrets are stored in the OS credential manager when available.
    If no secure backend exists, a secret is process-memory-only and is not
    serialized to disk.
    """

    KEYRING_SERVICE = "nova-apex"

    def __init__(self, persistence_file: Optional[Path] = None):
        self.persistence_file = persistence_file or (settings.artifacts_dir / "agent_memory_vault.json")
        self.working_memory: Dict[str, Any] = {}
        self._ephemeral_secrets: Dict[str, str] = {}
        self.vault: Dict[str, Any] = {
            "credentials": [],
            "created_accounts": [],
            "saved_entities": {},
            "learned_patterns": {},
            "execution_notes": [],
        }
        self.load()

    @staticmethod
    def _credential_key(service: str, username: str) -> str:
        return f"{service.strip()}::{username.strip()}"

    def _store_secret(self, service: str, username: str, secret: str) -> bool:
        key = self._credential_key(service, username)
        try:
            import keyring
            keyring.set_password(self.KEYRING_SERVICE, key, secret)
            self._ephemeral_secrets.pop(key, None)
            return True
        except Exception:
            self._ephemeral_secrets[key] = secret
            agent_logger.warning(
                "OS credential store unavailable; this credential will not survive restart.",
                domain="MEMORY",
            )
            return False

    def _read_secret(self, service: str, username: str) -> Optional[str]:
        key = self._credential_key(service, username)
        if key in self._ephemeral_secrets:
            return self._ephemeral_secrets[key]
        try:
            import keyring
            return keyring.get_password(self.KEYRING_SERVICE, key)
        except Exception:
            return None

    def _delete_secret(self, service: str, username: str) -> None:
        key = self._credential_key(service, username)
        self._ephemeral_secrets.pop(key, None)
        try:
            import keyring
            if keyring.get_password(self.KEYRING_SERVICE, key) is not None:
                keyring.delete_password(self.KEYRING_SERVICE, key)
        except Exception:
            pass

    def set_working(self, key: str, value: Any):
        self.working_memory[key] = value

    def get_working(self, key: str, default: Any = None) -> Any:
        return self.working_memory.get(key, default)

    @classmethod
    def _sanitize_metadata(cls, value: Any, depth: int = 0) -> Any:
        """Redact obvious secrets from arbitrary metadata before persistence."""
        if depth > 8:
            return "[depth-limit]"
        sensitive_markers = ("secret", "password", "passwd", "token", "cookie", "authorization", "api_key", "apikey", "otp", "verification_code")
        if isinstance(value, dict):
            safe = {}
            for key, item in list(value.items())[:100]:
                name = str(key)
                if any(marker in name.lower().replace("-", "_") for marker in sensitive_markers):
                    safe[name] = "[redacted]"
                else:
                    safe[name] = cls._sanitize_metadata(item, depth + 1)
            return safe
        if isinstance(value, list):
            return [cls._sanitize_metadata(item, depth + 1) for item in value[:100]]
        if isinstance(value, str):
            return value[:4096]
        if value is None or isinstance(value, (int, float, bool)):
            return value
        return str(value)[:512]

    def store_credential(self, service: str, username: str, secret: str, extra: Optional[Dict[str, Any]] = None):
        service = (service or "").strip()
        username = (username or "").strip()
        if not service or not username:
            raise ValueError("Credential service and username are required.")
        if not secret:
            raise ValueError("Credential secret cannot be empty.")
        if len(service) > 256 or len(username) > 256 or len(secret) > 4096:
            raise ValueError("Credential fields exceed the supported size limit.")

        stored_in_keyring = self._store_secret(service, username, secret)
        timestamp = datetime.utcnow().isoformat()
        entry = {
            "service": service,
            "username": username,
            "extra": self._sanitize_metadata(extra or {}),
            "timestamp": timestamp,
            "secret_storage": "os_keyring" if stored_in_keyring else "process_memory",
        }
        self.vault["credentials"] = [
            item for item in self.vault.get("credentials", [])
            if not (item.get("service", "").lower() == service.lower() and item.get("username", "").lower() == username.lower())
        ]
        self.vault["credentials"].append(entry)
        self.vault["created_accounts"] = [
            item for item in self.vault.get("created_accounts", [])
            if not (item.get("service", "").lower() == service.lower() and item.get("username", "").lower() == username.lower())
        ]
        self.vault["created_accounts"].append({
            "service": service, "username": username, "timestamp": timestamp,
        })
        self.save()
        agent_logger.success(f"Credential metadata stored for [{service}]; secret kept outside the JSON vault.", domain="MEMORY")
        return {"service": service, "username": username, "timestamp": timestamp, "secret_storage": entry["secret_storage"]}

    def get_credentials_for(self, service: str) -> Optional[Dict[str, Any]]:
        for entry in reversed(self.vault.get("credentials", [])):
            if entry.get("service", "").lower() == service.lower():
                secret = self._read_secret(entry.get("service", ""), entry.get("username", ""))
                if secret is not None:
                    return {**entry, "secret": secret}
        return None

    def delete_credential(self, service: str, username: str) -> bool:
        matches = [
            item for item in self.vault.get("credentials", [])
            if item.get("service", "").lower() == service.lower() and item.get("username", "").lower() == username.lower()
        ]
        for entry in matches:
            self._delete_secret(entry.get("service", ""), entry.get("username", ""))
        self.vault["credentials"] = [
            item for item in self.vault.get("credentials", [])
            if not (item.get("service", "").lower() == service.lower() and item.get("username", "").lower() == username.lower())
        ]
        self.vault["created_accounts"] = [
            item for item in self.vault.get("created_accounts", [])
            if not (item.get("service", "").lower() == service.lower() and item.get("username", "").lower() == username.lower())
        ]
        self.save()
        return bool(matches)

    def credential_metadata(self) -> list[Dict[str, Any]]:
        return [
            {
                "service": item.get("service", ""),
                "username": item.get("username", ""),
                "timestamp": item.get("timestamp", ""),
                "secret": "••••••••",
                "secret_storage": item.get("secret_storage", "unknown"),
            }
            for item in self.vault.get("credentials", [])
        ]

    def store_entity(self, key: str, value: Any):
        self.vault["saved_entities"][key] = {"value": value, "updated_at": datetime.utcnow().isoformat()}
        self.save()

    def get_entity(self, key: str, default: Any = None) -> Any:
        entry = self.vault["saved_entities"].get(key)
        return entry["value"] if entry else default

    def resolve_placeholders(self, text: str) -> str:
        """Resolve ${key} placeholders against working memory and saved entities."""
        if not text or not isinstance(text, str):
            return text
        for key, value in self.working_memory.items():
            text = text.replace(f"${{{key}}}", str(value))
        for key, entry in self.vault.get("saved_entities", {}).items():
            text = text.replace(f"${{{key}}}", str(entry.get("value", "")))
        return text

    def save(self):
        try:
            self.persistence_file.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.persistence_file.with_suffix(self.persistence_file.suffix + ".tmp")
            with open(temp_path, "w", encoding="utf-8") as handle:
                json.dump(self.vault, handle, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.chmod(temp_path, 0o600)
            except OSError:
                pass
            os.replace(temp_path, self.persistence_file)
        except Exception as exc:
            agent_logger.error(f"Failed to persist memory metadata: {exc}", domain="MEMORY")

    def load(self):
        if not self.persistence_file.exists():
            return
        try:
            with open(self.persistence_file, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if not isinstance(loaded, dict):
                raise ValueError("Vault root must be an object.")
            self.vault.update(loaded)
            # Keep legacy account records to a non-sensitive metadata allowlist.
            self.vault["created_accounts"] = [
                {key: account.get(key, "") for key in ("service", "username", "timestamp")}
                for account in self.vault.get("created_accounts", [])
                if isinstance(account, dict)
            ]
            for credential in self.vault.get("credentials", []):
                if isinstance(credential, dict):
                    credential["extra"] = self._sanitize_metadata(credential.get("extra", {}))
            migrated = False
            # Migrate legacy plaintext secrets out of the tracked JSON vault.
            for entry in self.vault.get("credentials", []):
                if isinstance(entry, dict) and entry.get("secret"):
                    legacy_secret = str(entry.pop("secret"))
                    stored_in_keyring = self._store_secret(
                        entry.get("service", ""), entry.get("username", ""), legacy_secret
                    )
                    entry["secret_storage"] = "os_keyring" if stored_in_keyring else "process_memory"
                    migrated = True
            if migrated:
                self.save()
                agent_logger.warning("Migrated legacy plaintext credentials out of the JSON vault.", domain="MEMORY")
        except Exception as exc:
            agent_logger.warning(f"Failed to load memory metadata: {exc}", domain="MEMORY")


agent_memory = AgentMemory()
