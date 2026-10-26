import asyncio
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any
from nova_apex.config.settings import settings
from nova_apex.core.logger import agent_logger
from nova_apex.core.schemas import StepResult, ActionRequest
from nova_apex.core.memory import agent_memory

class ShellController:
    """
    Subprocess and PowerShell Execution Controller:
    Executes terminal commands, build tools, package installations, and system maintenance scripts.
    """

    def __init__(self):
        self.workspace_dir = settings.workspace_dir

    async def execute_action(self, action: ActionRequest) -> StepResult:
        if not settings.allow_shell_execution:
            return StepResult(
                action_id=action.action_id,
                success=False,
                error="Shell execution is disabled by default. Review the command and set ALLOW_SHELL_EXECUTION=true in your local .env to enable it.",
            )

        cmd_text = agent_memory.resolve_placeholders(action.value or action.target or "")
        if not cmd_text.strip():
            return StepResult(action_id=action.action_id, success=False, error="A non-empty shell command is required.")
        agent_logger.action("Executing shell command (explicit local opt-in enabled).", domain="SHELL")

        try:
            # Pass the command as a single argv element; never interpolate it into
            # a second shell command string.
            import os
            if os.name == "nt":
                proc = await asyncio.create_subprocess_exec(
                    "powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", cmd_text,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(self.workspace_dir),
                )
            else:
                proc = await asyncio.create_subprocess_exec(
                    "/bin/bash", "-lc", cmd_text,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(self.workspace_dir),
                )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=action.timeout_seconds)
            except asyncio.TimeoutError:
                proc.kill()
                agent_logger.error(f"Command timed out after {action.timeout_seconds}s", domain="SHELL")
                return StepResult(action_id=action.action_id, success=False, error=f"Timeout after {action.timeout_seconds} seconds")

            stdout_str = stdout_bytes.decode("utf-8", errors="replace").strip()
            stderr_str = stderr_bytes.decode("utf-8", errors="replace").strip()

            success = (proc.returncode == 0)
            if success:
                agent_logger.success(f"Command finished (exit 0)", domain="SHELL")
            else:
                agent_logger.warning(f"Command exited with code {proc.returncode}", domain="SHELL")

            return StepResult(
                action_id=action.action_id,
                success=success,
                output=stdout_str,
                error=stderr_str if not success else None,
                data={"exit_code": proc.returncode, "stdout": stdout_str, "stderr": stderr_str}
            )

        except Exception as e:
            agent_logger.error(f"Failed to execute command: {e}", domain="SHELL")
            return StepResult(action_id=action.action_id, success=False, error=str(e))

shell_controller = ShellController()
