import os
import shutil
import platform
from pathlib import Path
from typing import Dict, Any, List
from nova_apex.config.settings import settings
from nova_apex.core.logger import agent_logger

class SystemAdminSkill:
    """
    Autonomous high-level skill:
    Automates system administration, disk inspection, workspace cleanup, and environment diagnostics.
    """

    def get_system_telemetry(self) -> Dict[str, Any]:
        info = {
            "os": platform.system(),
            "os_release": platform.release(),
            "os_version": platform.version(),
            "architecture": platform.machine(),
            "processor": platform.processor(),
            "python_version": platform.python_version(),
            "workspace": str(settings.workspace_dir),
            "artifacts_dir": str(settings.artifacts_dir),
            "free_disk_gb": round(shutil.disk_usage(settings.workspace_dir).free / (1024**3), 2)
        }
        agent_logger.info(f"System Telemetry: OS {info['os']} ({info['architecture']}) | Disk Free: {info['free_disk_gb']} GB", domain="SKILL")
        return info

    def clean_temporary_artifacts(self, older_than_days: int = 7) -> int:
        deleted = 0
        for item in settings.artifacts_dir.glob("*.png"):
            try:
                item.unlink()
                deleted += 1
            except Exception:
                pass
        agent_logger.success(f"Cleaned {deleted} temporary artifact files.", domain="SKILL")
        return deleted

system_admin = SystemAdminSkill()
