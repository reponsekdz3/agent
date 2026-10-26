import asyncio
import importlib
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from fastapi import HTTPException

from nova_apex.config.settings import settings
from nova_apex.controllers.browser_controller import BrowserController
from nova_apex.core.engine import AutonomousEngine
from nova_apex.core.memory import agent_memory
from nova_apex.core.schemas import ActionDomain, ActionRequest, ActionType, PlanStep

server_module = importlib.import_module("nova_apex.server.app")


class ControlSecurityTests(unittest.TestCase):
    def setUp(self):
        self.original_settings = {
            "auth_password": settings.auth_password,
            "auth_cookie_secure": settings.auth_cookie_secure,
            "auth_session_ttl_seconds": settings.auth_session_ttl_seconds,
            "server_host": settings.server_host,
            "workspace_dir": settings.workspace_dir,
        }
        settings.auth_password = "test-only-password-longer-than-16"
        settings.auth_cookie_secure = False
        settings.auth_session_ttl_seconds = 120
        settings.server_host = "127.0.0.1"
        server_module._auth_sessions.clear()
        server_module._failed_logins.clear()
        self.client = TestClient(server_module.app)

    def tearDown(self):
        self.client.close()
        server_module._auth_sessions.clear()
        server_module._failed_logins.clear()
        for key, value in self.original_settings.items():
            setattr(settings, key, value)

    def sign_in(self):
        response = self.client.post(
            "/api/auth/login",
            json={"password": settings.auth_password},
            headers={"Origin": "http://testserver"},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["csrf_token"]

    def post_headers(self, csrf_token):
        return {
            "Origin": "http://testserver",
            "X-CSRF-Token": csrf_token,
        }

    def test_authentication_session_csrf_origin_and_expiry(self):
        self.assertEqual(self.client.get("/api/status").status_code, 401)

        csrf_token = self.sign_in()
        self.assertEqual(self.client.get("/api/status").status_code, 200)
        self.assertEqual(
            self.client.post("/api/pause", headers={"Origin": "http://testserver"}).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/pause",
                headers={
                    "Origin": "https://attacker.invalid",
                    "X-CSRF-Token": csrf_token,
                },
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post("/api/pause", headers=self.post_headers(csrf_token)).status_code,
            200,
        )

        session_id = self.client.cookies.get(server_module.AUTH_COOKIE_NAME)
        server_module._auth_sessions[session_id]["expires_at"] = 0
        status = self.client.get("/api/auth/status").json()
        self.assertFalse(status["authenticated"])
        self.assertEqual(self.client.get("/api/status").status_code, 401)

    def test_login_rate_limit(self):
        for _ in range(5):
            response = self.client.post(
                "/api/auth/login",
                json={"password": "wrong"},
                headers={"Origin": "http://testserver"},
            )
            self.assertEqual(response.status_code, 401)
        limited = self.client.post(
            "/api/auth/login",
            json={"password": "wrong"},
            headers={"Origin": "http://testserver"},
        )
        self.assertEqual(limited.status_code, 429)

    def test_workspace_path_containment(self):
        workspace = Path(__file__).resolve().parent / ".security-workspace"
        settings.workspace_dir = workspace
        self.assertEqual(server_module.resolve_workspace_path("notes.txt"), workspace / "notes.txt")
        for invalid in ("../outside.txt", str(workspace.parent / "outside.txt")):
            with self.assertRaises(HTTPException):
                server_module.resolve_workspace_path(invalid)

    def test_vault_listing_redacts_secret_and_reveal_is_explicit(self):
        csrf_token = self.sign_in()
        original_vault = agent_memory.vault
        agent_memory.vault = {
            "credentials": [
                {
                    "service": "example.test",
                    "username": "review-user",
                    "secret": "do-not-return-this",
                    "extra": {"status": "draft"},
                    "timestamp": "2026-01-01T00:00:00",
                }
            ],
            "created_accounts": [],
            "saved_entities": {},
        }
        try:
            listed = self.client.get("/api/manage/vault/credentials")
            self.assertEqual(listed.status_code, 200)
            self.assertNotIn("do-not-return-this", listed.text)
            metadata = self.client.get("/api/vault")
            self.assertEqual(metadata.status_code, 200)
            self.assertNotIn("do-not-return-this", metadata.text)

            revealed = self.client.post(
                "/api/manage/vault/credential/reveal",
                json={"service": "example.test", "username": "review-user"},
                headers=self.post_headers(csrf_token),
            )
            self.assertEqual(revealed.status_code, 200)
            self.assertEqual(revealed.json()["secret"], "do-not-return-this")
        finally:
            agent_memory.vault = original_vault

    def test_browser_clicks_and_recovery_actions_require_approval(self):
        engine = AutonomousEngine()
        click = ActionRequest(
            domain=ActionDomain.BROWSER,
            action_type=ActionType.CLICK_ELEMENT,
            description="Click checkout",
            target="button.checkout",
        )
        navigate = ActionRequest(
            domain=ActionDomain.BROWSER,
            action_type=ActionType.NAVIGATE,
            description="Search products",
            target="https://example.test",
        )
        self.assertTrue(engine._requires_approval(click))
        self.assertFalse(engine._requires_approval(navigate))

    def test_direct_form_submission_requires_confirmation(self):
        csrf_token = self.sign_in()
        browser_module = importlib.import_module("nova_apex.controllers.browser_controller")
        browser = browser_module.browser_controller
        original_execute = browser.execute_action
        browser.execute_action = AsyncMock(
            return_value=importlib.import_module("nova_apex.core.schemas").StepResult(
                action_id="test",
                success=True,
                output="submitted",
            )
        )
        try:
            body = {"action": "submit_form", "target": "button[type=submit]"}
            denied = self.client.post(
                "/api/browser/action",
                json=body,
                headers=self.post_headers(csrf_token),
            )
            self.assertEqual(denied.status_code, 428)
            browser.execute_action.assert_not_awaited()

            approved = self.client.post(
                "/api/browser/action",
                json={**body, "confirmed": True},
                headers=self.post_headers(csrf_token),
            )
            self.assertEqual(approved.status_code, 200)
            browser.execute_action.assert_awaited_once()
            action = browser.execute_action.await_args.args[0]
            self.assertTrue(action.params["user_confirmed"])
        finally:
            browser.execute_action = original_execute

    def test_controller_refuses_unconfirmed_browser_click(self):
        controller = BrowserController()
        controller.initialize = AsyncMock()
        action = ActionRequest(
            domain=ActionDomain.BROWSER,
            action_type=ActionType.CLICK_ELEMENT,
            description="Potential final action",
            target="button#continue",
        )
        result = asyncio.run(controller.execute_action(action))
        self.assertFalse(result.success)
        self.assertIn("explicit user confirmation", result.error)

    def test_browser_viewport_click_requires_confirmation(self):
        csrf_token = self.sign_in()
        response = self.client.post(
            "/api/interact/click",
            json={"x": 10, "y": 10, "domain": "browser"},
            headers=self.post_headers(csrf_token),
        )
        self.assertEqual(response.status_code, 428)


if __name__ == "__main__":
    unittest.main()
