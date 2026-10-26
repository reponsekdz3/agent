from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nova_apex.config.settings import settings
from nova_apex.core.engine import AutonomousEngine
from nova_apex.core.memory import AgentMemory
from nova_apex.core.schemas import AgentGoal, GoalStatus
from nova_apex.security import resolve_inside


def test_resolve_inside_allows_workspace_paths_and_rejects_traversal(tmp_path: Path):
    root = tmp_path / "workspace"
    root.mkdir()
    assert resolve_inside(root, "reports/new.md") == (root / "reports" / "new.md").resolve()
    with pytest.raises(ValueError):
        resolve_inside(root, "../outside.txt")
    with pytest.raises(ValueError):
        resolve_inside(root, str(tmp_path / "outside.txt"))


def test_resolve_inside_rejects_symlink_escape(tmp_path: Path):
    root = tmp_path / "workspace"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation is unavailable for this user or operating system.")
    with pytest.raises(ValueError):
        resolve_inside(root, "escape/secret.txt")


def test_credential_vault_never_persists_plaintext_secrets(tmp_path: Path):
    vault_path = tmp_path / "vault.json"
    memory = AgentMemory(vault_path)
    secret = "test-secret-that-must-not-reach-disk"
    memory.store_credential("example.test", "alice", secret, {"scope": "unit-test"})
    serialized = vault_path.read_text(encoding="utf-8")
    assert secret not in serialized
    assert "secret" not in memory.vault["credentials"][0]
    assert memory.credential_metadata()[0]["secret"] == "••••••••"
    assert memory.get_credentials_for("example.test")["secret"] == secret
    assert memory.delete_credential("example.test", "alice") is True
    assert memory.get_credentials_for("example.test") is None


def test_invalid_workspace_path_returns_bad_request():
    from nova_apex.server.app import app
    client = TestClient(app)
    response = client.get("/api/manage/workspace/file", params={"path": "../../.env"})
    assert response.status_code == 400


def test_untrusted_origin_is_rejected_before_control_action():
    from nova_apex.server.app import app
    client = TestClient(app)
    response = client.post("/api/pause", headers={"Origin": "https://attacker.example"})
    assert response.status_code == 403


def test_shell_execution_is_disabled_without_explicit_opt_in(monkeypatch, tmp_path: Path):
    from nova_apex.controllers.shell_controller import shell_controller
    from nova_apex.core.schemas import ActionDomain, ActionRequest, ActionType
    monkeypatch.setattr(settings, "allow_shell_execution", False)
    monkeypatch.setattr(settings, "workspace_dir", tmp_path)
    action = ActionRequest(domain=ActionDomain.SHELL, action_type=ActionType.EXECUTE_SHELL, description="safety test", value="echo must-not-run")
    result = asyncio.run(shell_controller.execute_action(action))
    assert result.success is False
    assert "disabled by default" in (result.error or "")


def test_empty_plan_is_failed_not_success(monkeypatch):
    from nova_apex.core.planner import planner
    async def empty_plan(prompt: str):
        return AgentGoal(prompt=prompt, status=GoalStatus.PLANNING, steps=[])
    monkeypatch.setattr(planner, "create_plan", empty_plan)
    goal = asyncio.run(AutonomousEngine().run_goal("verify empty plan"))
    assert goal.status == GoalStatus.FAILED
    assert "no executable steps" in (goal.summary or "").lower()
