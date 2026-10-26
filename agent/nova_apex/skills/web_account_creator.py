import asyncio
from typing import Dict, Any, Optional
from nova_apex.core.schemas import ActionRequest, ActionDomain, ActionType
from nova_apex.controllers.browser_controller import browser_controller
from nova_apex.controllers.mobile_controller import mobile_controller
from nova_apex.core.memory import agent_memory
from nova_apex.core.logger import agent_logger

class WebAccountCreatorSkill:
    """
    Autonomous high-level skill:
    Navigates to arbitrary service signup portals, detects registration form inputs,
    generates secure realistic identities, populates and submits forms,
    intercepts 2FA verification codes if requested, and archives credentials to vault.
    """

    async def create_account(self, target_url: str, custom_username: Optional[str] = None) -> Dict[str, Any]:
        agent_logger.info(f"Initiating Autonomous Account Generation procedure for: {target_url}", domain="SKILL")

        # 1. Navigate to target portal
        nav_req = ActionRequest(
            domain=ActionDomain.BROWSER,
            action_type=ActionType.NAVIGATE,
            description=f"Navigate to {target_url}",
            target=target_url
        )
        nav_res = await browser_controller.execute_action(nav_req)
        if not nav_res.success:
            return {"success": False, "error": f"Failed to open {target_url}: {nav_res.error}"}

        # 2. Execute intelligent form filling & synthesis
        fill_req = ActionRequest(
            domain=ActionDomain.BROWSER,
            action_type=ActionType.CREATE_ACCOUNT,
            description="Auto-fill registration form and credentials",
            value=custom_username or "auto"
        )
        fill_res = await browser_controller.execute_action(fill_req)
        if not fill_res.success:
            return {"success": False, "error": fill_res.error}

        # 3. Post-submission check for OTP / Verification Code field
        page = browser_controller.page
        if page:
            await asyncio.sleep(2)
            otp_selectors = [
                "input[name*='code' i]", "input[id*='code' i]", "input[placeholder*='code' i]",
                "input[name*='otp' i]", "input[id*='otp' i]", "input[aria-label*='verification' i]"
            ]
            for sel in otp_selectors:
                if await page.is_visible(sel):
                    agent_logger.warning("Detected 2FA / Verification Code input on page. Scanning for OTP...", domain="SKILL")
                    # Try reading mobile notification OTP
                    devices = mobile_controller.get_connected_devices()
                    if devices:
                        otp_code = mobile_controller.extract_latest_otp(devices[0])
                        if otp_code:
                            await browser_controller.human_type(sel, otp_code)
                            agent_logger.success(f"Injected intercepted 2FA code [{otp_code}] into verification form!", domain="SKILL")
                            # Look for verify/confirm button
                            verify_btn = await page.query_selector("button:has-text('Verify'), button:has-text('Confirm')")
                            if verify_btn:
                                await verify_btn.click()
                    break

        shot = await browser_controller.take_screenshot("account_final")
        return {
            "success": True,
            "details": fill_res.data,
            "screenshot": shot,
            "error": None
        }

web_account_creator = WebAccountCreatorSkill()
