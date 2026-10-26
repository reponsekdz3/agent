import os
import asyncio
import secrets
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from urllib.parse import urlsplit
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from nova_apex.config.settings import settings
from nova_apex.core.logger import agent_logger
from nova_apex.core.schemas import StepResult, ActionRequest
from nova_apex.core.memory import agent_memory

class BrowserController:
    """
    Playwright browser automation engine:
    - Direct CDP (Chrome DevTools Protocol) attachment to real running user browsers
    - Multi-browser support (Chromium, Firefox, WebKit, Edge, Chrome)
    - Persistent session state & cookie preservation
    """

    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._is_initialized = False
        self._cursor_pos: Tuple[float, float] = (100.0, 100.0)
        self.state_file = settings.user_data_dir / "storage_state.json"

    async def initialize(self, browser_type: str = "chromium", cdp_url: Optional[str] = None):
        if self._is_initialized and self.page and not self.page.is_closed():
            return

        agent_logger.info("Initializing browser automation subsystem...", domain="BROWSER")
        self.playwright = await async_playwright().start()

        # Connect to real running browser if CDP URL specified
        if cdp_url or os.getenv("CHROME_CDP_URL"):
            endpoint = cdp_url or os.getenv("CHROME_CDP_URL", "http://localhost:9222")
            try:
                agent_logger.info(f"Connecting to real user browser via CDP at {endpoint}...", domain="BROWSER")
                self.browser = await self.playwright.chromium.connect_over_cdp(endpoint)
                self.context = self.browser.contexts[0] if self.browser.contexts else await self.browser.new_context()
                self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
                self._is_initialized = True
                agent_logger.success("Attached directly to active user browser instance!", domain="BROWSER")
                return
            except Exception as e:
                agent_logger.warning(f"CDP connection to {endpoint} failed ({e}). Starting an isolated browser.", domain="BROWSER")

        # Select browser driver
        if browser_type.lower() == "firefox":
            self.browser = await self.playwright.firefox.launch(headless=settings.browser_headless)
        elif browser_type.lower() == "webkit":
            self.browser = await self.playwright.webkit.launch(headless=settings.browser_headless)
        else:
            self.browser = await self.playwright.chromium.launch(
                headless=settings.browser_headless
            )

        storage_path = str(self.state_file) if self.state_file.exists() else None

        self.context = await self.browser.new_context(
            viewport={"width": settings.browser_viewport_width, "height": settings.browser_viewport_height},
            storage_state=storage_path
        )

        self.page = await self.context.new_page()
        self._is_initialized = True
        agent_logger.success("Browser automation subsystem initialized.", domain="BROWSER")

    async def move_mouse(self, target_x: float, target_y: float):
        await self.page.mouse.move(target_x, target_y)
        self._cursor_pos = (target_x, target_y)

    async def type_text(self, selector: str, text: str):
        await self.page.locator(selector).fill(text)

    async def execute_action(self, action: ActionRequest) -> StepResult:
        await self.initialize()
        action_type = action.action_type.value

        try:
            if action_type == "navigate":
                url = agent_memory.resolve_placeholders(action.target or action.value)
                if url in {"back", "forward", "reload"}:
                    if url == "back":
                        await self.page.go_back()
                    elif url == "forward":
                        await self.page.go_forward()
                    else:
                        await self.page.reload()
                    shot = await self.take_screenshot(f"browser_{url}")
                    return StepResult(action_id=action.action_id, success=True, output=f"Browser {url} completed.", screenshot_path=shot)
                if not url.startswith("http://") and not url.startswith("https://"):
                    url = f"https://{url}"
                agent_logger.action(f"Stealth navigating to {url}", domain="BROWSER")
                await self.page.goto(url, wait_until="domcontentloaded", timeout=action.timeout_seconds * 1000)
                await asyncio.sleep(0.4)
                # Save session cookies
                try:
                    await self.context.storage_state(path=str(self.state_file))
                except Exception:
                    pass
                shot_path = await self.take_screenshot("nav_success")
                return StepResult(
                    action_id=action.action_id,
                    success=True,
                    output=f"Successfully navigated to {self.page.url}",
                    screenshot_path=shot_path,
                    data={"url": self.page.url, "title": await self.page.title()}
                )

            elif action_type == "click_element":
                selector = action.target or ""
                if not selector:
                    return StepResult(action_id=action.action_id, success=False, error="A browser click target is required.")
                if not action.params.get("user_confirmed"):
                    return StepResult(
                        action_id=action.action_id,
                        success=False,
                        error="Browser clicks require explicit user confirmation because they may submit, purchase, or book."
                    )
                agent_logger.action(f"Locating browser click target: {selector}", domain="BROWSER")

                if "," in selector and all(p.strip().isdigit() for p in selector.replace("(", "").replace(")", "").split(",")):
                    coords = [int(p.strip()) for p in selector.replace("(", "").replace(")", "").split(",")]
                    await self.move_mouse(coords[0], coords[1])
                    await self.page.mouse.click(coords[0], coords[1])
                else:
                    el = await self.page.wait_for_selector(selector, state="visible", timeout=action.timeout_seconds * 1000)
                    await el.click()

                await asyncio.sleep(0.2)
                shot = await self.take_screenshot("click_result")
                return StepResult(action_id=action.action_id, success=True, output=f"Clicked {selector}", screenshot_path=shot)

            elif action_type == "type_element":
                selector = action.target
                raw_text = action.value or ""
                text_to_type = agent_memory.resolve_placeholders(raw_text)
                agent_logger.action(f"Filling browser field: {selector}", domain="BROWSER")
                await self.page.wait_for_selector(selector, state="visible", timeout=action.timeout_seconds * 1000)
                await self.type_text(selector, text_to_type)
                shot = await self.take_screenshot("type_result")
                return StepResult(action_id=action.action_id, success=True, output=f"Typed text into {selector}", screenshot_path=shot)

            elif action_type == "create_account":
                return await self.auto_fill_registration(action)

            elif action_type == "submit_form":
                if not action.params.get("user_confirmed"):
                    return StepResult(action_id=action.action_id, success=False, error="Form submission requires explicit user confirmation.")
                selector = action.target or "button[type='submit'], input[type='submit']"
                submit_button = await self.page.wait_for_selector(selector, state="visible", timeout=action.timeout_seconds * 1000)
                await submit_button.click()
                shot = await self.take_screenshot("form_submitted")
                return StepResult(action_id=action.action_id, success=True, output="Form submission requested after confirmation.", screenshot_path=shot)

            elif action_type == "switch_tab":
                if not self.context or not action.target or not action.target.isdigit():
                    return StepResult(action_id=action.action_id, success=False, error="A valid browser tab index is required.")
                tab_index = int(action.target)
                pages = self.context.pages
                if tab_index >= len(pages):
                    return StepResult(action_id=action.action_id, success=False, error="Browser tab index is out of range.")
                self.page = pages[tab_index]
                shot = await self.take_screenshot("tab_selected")
                return StepResult(action_id=action.action_id, success=True, output=f"Selected browser tab {tab_index}.", screenshot_path=shot)

            elif action_type == "close_browser":
                await self.close()
                return StepResult(action_id=action.action_id, success=True, output="Browser session closed.")

            elif action_type == "extract_content":
                agent_logger.action("Extracting page accessibility snapshot & interactive tree...", domain="BROWSER")
                dom_summary = await self.extract_interactive_elements()
                return StepResult(
                    action_id=action.action_id,
                    success=True,
                    output=f"Extracted {len(dom_summary.get('inputs', []))} inputs and {len(dom_summary.get('buttons', []))} buttons.",
                    data=dom_summary
                )

            elif action_type == "browser_screenshot":
                shot_path = await self.take_screenshot("manual_capture")
                return StepResult(action_id=action.action_id, success=True, output="Screenshot captured", screenshot_path=shot_path)

            elif action_type == "evaluate_js":
                if not action.params.get("user_confirmed"):
                    return StepResult(
                        action_id=action.action_id,
                        success=False,
                        error="Page JavaScript execution requires explicit user confirmation."
                    )
                script = action.value or action.target
                agent_logger.action("Evaluating JavaScript in page context...", domain="BROWSER")
                res = await self.page.evaluate(script)
                return StepResult(action_id=action.action_id, success=True, output=str(res), data={"result": res})

            else:
                return StepResult(action_id=action.action_id, success=False, error=f"Unknown browser action: {action_type}")

        except Exception as e:
            agent_logger.error(f"Browser action failed: {str(e)}", domain="BROWSER")
            shot = await self.take_screenshot("error_capture") if self.page else None
            return StepResult(action_id=action.action_id, success=False, error=str(e), screenshot_path=shot)

    async def auto_fill_registration(self, action: ActionRequest) -> StepResult:
        """Fill a registration form for user review without accepting terms or submitting it."""
        agent_logger.info("Scanning page for registration fields...", domain="BROWSER")
        rand_id = secrets.token_hex(4)
        generated_username = f"nova_agent_{rand_id}"
        generated_password = f"NovaApex#{secrets.token_urlsafe(16)}"
        fields_filled = []
        supplied_email = action.params.get("email")

        email_selectors = [
            "input[type='email']", "input[name*='email' i]", "input[id*='email' i]",
            "input[placeholder*='email' i]", "input[autocomplete='email']"
        ]
        email_selector = None
        for sel in email_selectors:
            if await self.page.is_visible(sel):
                email_selector = sel
                break
        if email_selector and not supplied_email:
            return StepResult(
                action_id=action.action_id,
                success=False,
                error="Provide an email address you control in action params before filling this form."
            )
        if email_selector:
            await self.type_text(email_selector, str(supplied_email))
            fields_filled.append("Email field filled")

        user_selectors = [
            "input[name*='user' i]", "input[id*='user' i]", "input[name*='login' i]",
            "input[placeholder*='username' i]", "input[name='name']"
        ]
        for sel in user_selectors:
            if await self.page.is_visible(sel):
                await self.type_text(sel, generated_username)
                fields_filled.append("Username field filled")
                break

        password_fields = await self.page.locator("input[type='password']").all()
        for field in password_fields:
            await field.fill(generated_password)
            fields_filled.append("Password field filled")

        current_url = self.page.url
        service_name = urlsplit(current_url).hostname or "unknown"
        agent_memory.store_credential(
            service=service_name,
            username=generated_username,
            secret=generated_password,
            extra={"email": supplied_email, "url": current_url, "status": "draft"}
        )

        shot = await self.take_screenshot("form_filled")
        return StepResult(
            action_id=action.action_id,
            success=True,
            output=f"Registration form filled on {service_name} for review. Terms and submission were left untouched.",
            screenshot_path=shot,
            data={
                "service": service_name,
                "username": generated_username,
                "fields_filled": fields_filled,
                "pending_user_review": True
            }
        )

    async def extract_interactive_elements(self) -> Dict[str, Any]:
        if not self.page:
            return {}

        js_extractor = """
        () => {
            const getVisible = el => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0 && window.getComputedStyle(el).visibility !== 'hidden';
            };

            const inputs = Array.from(document.querySelectorAll('input, textarea, select'))
                .filter(getVisible)
                .map(el => {
                    const rect = el.getBoundingClientRect();
                    return {
                        tag: el.tagName.toLowerCase(),
                        type: el.type || '',
                        name: el.name || '',
                        id: el.id || '',
                        placeholder: el.placeholder || '',
                        value: /password|token|secret|otp|code/i.test([el.type, el.name, el.id, el.autocomplete].join(' '))
                            ? ''
                            : (el.value || ''),
                        x: Math.round(rect.x + rect.width / 2),
                        y: Math.round(rect.y + rect.height / 2)
                    };
                });

            const buttons = Array.from(document.querySelectorAll('button, a[role="button"], input[type="submit"]'))
                .filter(getVisible)
                .map(el => {
                    const rect = el.getBoundingClientRect();
                    return {
                        text: el.innerText.trim(),
                        id: el.id || '',
                        classes: el.className || '',
                        x: Math.round(rect.x + rect.width / 2),
                        y: Math.round(rect.y + rect.height / 2)
                    };
                });

            return {
                title: document.title,
                url: window.location.href,
                inputs: inputs.slice(0, 30),
                buttons: buttons.slice(0, 30)
            };
        }
        """
        try:
            return await self.page.evaluate(js_extractor)
        except Exception:
            return {"title": await self.page.title(), "url": self.page.url}

    async def take_screenshot(self, name: str = "capture") -> str:
        if not self.page:
            return ""
        filename = f"{name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}.png"
        filepath = settings.artifacts_dir / filename
        await self.page.screenshot(path=str(filepath), full_page=False)
        return str(filepath)

    async def close(self):
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self._is_initialized = False
        agent_logger.info("Browser closed.", domain="BROWSER")

browser_controller = BrowserController()
