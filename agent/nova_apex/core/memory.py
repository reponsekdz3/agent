import json
from pathlib import Path
from typing import Any, Dict, Optional, List
from datetime import datetime
from nova_apex.config.settings import settings
from nova_apex.core.logger import agent_logger

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
        entry = {
            "service": service,
            "username": username,
            "secret": secret,
            "extra": extra or {},
            "timestamp": datetime.utcnow().isoformat()
        }
        self.vault["credentials"].append(entry)
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
        try:
            with open(self.persistence_file, "w", encoding="utf-8") as f:
                json.dump(self.vault, f, indent=2)
        except Exception as e:
            agent_logger.error(f"Failed to persist memory vault: {e}", domain="MEMORY")

    def load(self):
        if self.persistence_file.exists():
            try:
                with open(self.persistence_file, "r", encoding="utf-8") as f:
                    self.vault.update(json.load(f))
            except Exception as e:
                agent_logger.warning(f"Failed to load memory vault, starting fresh: {e}", domain="MEMORY")

agent_memory = AgentMemory()
