import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Dict, Any
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from nova_apex.config.settings import settings

console = Console()

class AgentLogger:
    def __init__(self):
        self.listeners: List[Callable[[Dict[str, Any]], None]] = []
        self.history: List[Dict[str, Any]] = []
        self.log_file = settings.session_logs_dir / f"session_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.jsonl"

    def register_listener(self, callback: Callable[[Dict[str, Any]], None]):
        self.listeners.append(callback)

    def log(self, level: str, message: str, domain: str = "SYSTEM", data: Dict[str, Any] = None):
        payload = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": level.upper(),
            "domain": domain.upper(),
            "message": message,
            "data": data or {}
        }
        self.history.append(payload)
        if len(self.history) > 1000:
            self.history.pop(0)

        # Write to JSONL log
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload) + "\n")
        except Exception:
            pass

        # Broadcast to active WebSockets / listeners
        for listener in self.listeners:
            try:
                listener(payload)
            except Exception:
                pass

        # Rich console output
        color = {
            "INFO": "cyan",
            "SUCCESS": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "THINKING": "magenta",
            "ACTION": "bright_blue"
        }.get(level.upper(), "white")

        domain_badge = f"[{color}][{domain.upper()}][/{color}]"
        console.print(f"{domain_badge} {message}")

    def info(self, msg: str, domain: str = "SYSTEM", **kwargs):
        self.log("INFO", msg, domain, kwargs)

    def success(self, msg: str, domain: str = "SYSTEM", **kwargs):
        self.log("SUCCESS", msg, domain, kwargs)

    def warning(self, msg: str, domain: str = "SYSTEM", **kwargs):
        self.log("WARNING", msg, domain, kwargs)

    def error(self, msg: str, domain: str = "SYSTEM", **kwargs):
        self.log("ERROR", msg, domain, kwargs)

    def thinking(self, msg: str, domain: str = "AGENT", **kwargs):
        self.log("THINKING", msg, domain, kwargs)

    def action(self, msg: str, domain: str = "AGENT", **kwargs):
        self.log("ACTION", msg, domain, kwargs)

agent_logger = AgentLogger()
