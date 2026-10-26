from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from uuid import uuid4
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
    service = f"test-{uuid4().hex}.example.test"
    memory.store_credential(service, "alice", secret, {"scope": "unit-test", "password": secret})
    serialized = vault_path.read_text(encoding="utf-8")
    assert secret not in serialized
    assert "secret" not in memory.vault["credentials"][0]
    assert memory.vault["credentials"][0]["extra"]["password"] == "[redacted]"
    assert memory.credential_metadata()[0]["secret"] == "••••••••"
    assert memory.get_credentials_for(service)["secret"] == secret
    assert memory.delete_credential(service, "alice") is True
    assert memory.get_credentials_for(service) is None


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


def test_vault_api_never_returns_credential_values():
    from nova_apex.server.app import app

    client = TestClient(app)
    secret = "api-response-test-secret-do-not-return"
    service = f"test-{uuid4().hex}.vault-api.local"
    username = "automated-safety-check"
    try:
        response = client.post("/api/manage/vault/credential", json={
            "service": service, "username": username, "secret": secret,
        })
        assert response.status_code == 200, response.text
        assert secret not in response.text

        vault = client.get("/api/vault")
        assert vault.status_code == 200
        assert secret not in vault.text
        record = next(item for item in vault.json()["credentials"] if item["service"] == service and item["username"] == username)
        assert record["secret"] == "••••••••"
    finally:
        client.delete("/api/manage/vault/credential", params={"service": service, "username": username})


def test_unknown_planner_action_is_rejected(monkeypatch):
    from nova_apex.core.llm_provider import llm
    from nova_apex.core.planner import planner
    from nova_apex.core.schemas import ActionType

    async def invalid_plan(**_kwargs):
        return '{"goal":"test","explanation":"test invalid action","steps":[{"step_id":1,"title":"invalid","description":"bad type","domain":"browser","action_type":"invented_action"}]}'

    monkeypatch.setattr(llm, "generate_response", invalid_plan)
    goal = asyncio.run(planner.create_plan("test an unsupported action"))
    assert len(goal.steps) == 1
    assert goal.steps[0].action_type == ActionType.FAIL
    assert goal.steps[0].suggested_action.action_type == ActionType.FAIL
