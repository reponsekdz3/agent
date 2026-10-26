from typing import Dict, Any, Optional
from nova_apex.core.schemas import ActionRequest, ActionDomain, ActionType
from nova_apex.controllers.browser_controller import browser_controller
from nova_apex.core.logger import agent_logger

class WebAccountCreatorSkill:
    """
    Assisted account-registration preparation. It fills a form for user review and
    stops before accepting terms, submitting, or entering verification codes.
    """

    async def create_account(self, target_url: str, email: Optional[str] = None) -> Dict[str, Any]:
        agent_logger.info(f"Preparing a registration form for review at: {target_url}", domain="SKILL")

        nav_req = ActionRequest(
            domain=ActionDomain.BROWSER,
            action_type=ActionType.NAVIGATE,
            description=f"Navigate to {target_url}",
            target=target_url
        )
        nav_res = await browser_controller.execute_action(nav_req)
        if not nav_res.success:
            return {"success": False, "error": f"Failed to open {target_url}: {nav_res.error}"}

        fill_req = ActionRequest(
            domain=ActionDomain.BROWSER,
            action_type=ActionType.CREATE_ACCOUNT,
            description="Fill registration fields for user review without submitting",
            params={"email": email} if email else {}
        )
        fill_res = await browser_controller.execute_action(fill_req)
        if not fill_res.success:
            return {"success": False, "error": fill_res.error}

        return {
            "success": fill_res.success,
            "details": fill_res.data,
            "screenshot": fill_res.screenshot_path,
            "error": fill_res.error,
            "requires_user_review": True
        }

web_account_creator = WebAccountCreatorSkill()
