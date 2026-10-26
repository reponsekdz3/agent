from typing import Any, Dict, Optional
from urllib.parse import urlsplit

from nova_apex.core.schemas import ActionRequest, ActionDomain, ActionType
from nova_apex.controllers.browser_controller import browser_controller
from nova_apex.core.logger import agent_logger


class WebAccountCreatorSkill:
    """Help prepare a signup form for an account the user owns.

    The skill never invents an email identity, accepts terms, submits a form,
    bypasses CAPTCHAs, extracts verification codes, or stores passwords. The user
    remains responsible for reviewing the site and completing confirmation.
    """

    async def create_account(
        self,
        target_url: str,
        custom_username: Optional[str] = None,
        email: Optional[str] = None,
        password: Optional[str] = None,
    ) -> Dict[str, Any]:
        parsed = urlsplit((target_url or "").strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return {"success": False, "error": "Enter a valid http:// or https:// signup URL."}
        if not email or not email.strip():
            return {
                "success": False,
                "needs_input": True,
                "required": ["email"],
                "message": "Provide an email address you control before preparing the signup form.",
            }

        agent_logger.info("Preparing a user-requested signup form; submission and verification remain manual.", domain="SKILL")
        navigation = await browser_controller.execute_action(ActionRequest(
            domain=ActionDomain.BROWSER,
            action_type=ActionType.NAVIGATE,
            description="Open the user-selected signup page",
            target=target_url.strip(),
        ))
        if not navigation.success:
            return {"success": False, "error": navigation.error}

        fill = await browser_controller.execute_action(ActionRequest(
            domain=ActionDomain.BROWSER,
            action_type=ActionType.CREATE_ACCOUNT,
            description="Fill only the user-provided signup details",
            params={
                "email": email.strip(),
                "username": (custom_username or "").strip(),
            },
        ))
        if not fill.success:
            return {"success": False, "error": fill.error, "screenshot": fill.screenshot_path}

        agent_logger.success("Signup fields prepared for user review; no submit or verification action was performed.", domain="SKILL")
        return {
            "success": True,
            "status": "requires_user_review",
            "submitted": False,
            "details": fill.data,
            "screenshot": fill.screenshot_path,
            "message": "Review the page, terms, and destination yourself, then submit manually if appropriate.",
        }


web_account_creator = WebAccountCreatorSkill()
