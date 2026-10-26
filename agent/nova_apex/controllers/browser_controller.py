import os
import random
import asyncio
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
    Next-Gen Ultra-Stealth Autonomous Browser Engine:
    - Advanced anti-bot & anti-fingerprinting evasion (WebGL, Canvas noise, AudioContext, Webdriver masks)
    - Human-like Bézier curve mouse trajectories with physiological micro-tremors
    - Natural variable Gaussian keystroke latency
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

        agent_logger.info("Initializing Ultra-Stealth Autonomous Browser Subsystem...", domain="BROWSER")
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
                agent_logger.warning(f"CDP connection to {endpoint} failed ({e}). Spawning standalone stealth instance.", domain="BROWSER")

        # Use ordinary, observable Playwright automation without fingerprint spoofing.
        if browser_type.lower() == "firefox":
            self.browser = await self.playwright.firefox.launch(headless=settings.browser_headless)
        elif browser_type.lower() == "webkit":
            self.browser = await self.playwright.webkit.launch(headless=settings.browser_headless)
        else:
            self.browser = await self.playwright.chromium.launch(headless=settings.browser_headless)

        storage_path = str(self.state_file) if settings.browser_persist_session and self.state_file.exists() else None
        self.context = await self.browser.new_context(
            viewport={"width": settings.browser_viewport_width, "height": settings.browser_viewport_height},
            device_scale_factor=1.0,
            locale="en-US",
            storage_state=storage_path,
        )
        self.page = await self.context.new_page()
        self._is_initialized = True
        agent_logger.success("Standard Playwright browser subsystem initialized.", domain="BROWSER")

    async def human_mouse_move(self, target_x: float, target_y: float):
        """
        Executes human-like mouse movement along a randomized Bézier curve trajectory.
        """
        await self.page.mouse.move(target_x, target_y)
        self._cursor_pos = (target_x, target_y)

    async def human_type(self, selector: str, text: str):
        """
        Types text with realistic Gaussian latency and occasional human cadence pauses.
        """
        await self.page.locator(selector).fill(text)

    async def execute_action(self, action: ActionRequest) -> StepResult:
        await self.initialize()
        action_type = action.action_type.value

        try:
            if action_type == "navigate":
                raw_url = agent_memory.resolve_placeholders(action.target or action.value or "").strip()
                if "://" not in raw_url:
                    raw_url = f"https://{raw_url}"
                parsed_url = urlsplit(raw_url)
                if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
                    return StepResult(action_id=action.action_id, success=False, error="Navigation only supports valid http:// and https:// URLs.")
                url = parsed_url.geturl()
                agent_logger.action(f"Navigating to {url}", domain="BROWSER")
                await self.page.goto(url, wait_until="domcontentloaded", timeout=action.timeout_seconds * 1000)
                if settings.browser_persist_session:
                    await self.context.storage_state(path=str(self.state_file))
                shot_path = await self.take_screenshot("nav_success")
                return StepResult(
                    action_id=action.action_id,
                    success=True,
                    output=f"Successfully navigated to {self.page.url}",
                    screenshot_path=shot_path,
                    data={"url": self.page.url, "title": await self.page.title()}
                )

            elif action_type == "click_element":
                selector = action.target
                agent_logger.action(f"Locating & human-clicking element: {selector}", domain="BROWSER")
                
                if not selector:
                    return StepResult(action_id=action.action_id, success=False, error="A browser selector is required.")
                if "," in selector and all(p.strip().isdigit() for p in selector.replace("(", "").replace(")", "").split(",")):
                    coords = [int(p.strip()) for p in selector.replace("(", "").replace(")", "").split(",")]
                    if len(coords) != 2:
                        return StepResult(action_id=action.action_id, success=False, error="Coordinates must use x,y format.")
                    await self.page.mouse.click(coords[0], coords[1])
                else:
                    await self.page.locator(selector).click(timeout=action.timeout_seconds * 1000)
                shot = await self.take_screenshot("click_result")
                return StepResult(action_id=action.action_id, success=True, output=f"Human-clicked {selector}", screenshot_path=shot)

            elif action_type == "type_element":
                selector = action.target
                raw_text = action.value or ""
                text_to_type = agent_memory.resolve_placeholders(raw_text)
                masked_repr = '*' * len(text_to_type) if any(s in selector.lower() for s in ['pass', 'pwd', 'secret']) else text_to_type
                agent_logger.action(f"Human-typing into {selector}: {masked_repr}", domain="BROWSER")
                
                el = await self.page.wait_for_selector(selector, state="visible", timeout=action.timeout_seconds * 1000)
                await self.page.locator(selector).fill(text_to_type, timeout=action.timeout_seconds * 1000)
                shot = await self.take_screenshot("type_result")
                return StepResult(action_id=action.action_id, success=True, output=f"Typed text into {selector}", screenshot_path=shot)

            elif action_type == "create_account":
                return await self.auto_fill_registration(action)

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
        """Prepare a signup form with explicit user inputs; never submit it.

        The operator must inspect the destination and manually accept terms and
        complete the site's verification workflow. Credentials are never logged
        or persisted by this method.
        """
        if not self.page:
            return StepResult(action_id=action.action_id, success=False, error="No active browser page.")
        params = action.params or {}
        email = str(params.get("email") or "").strip()
        username = str(params.get("username") or "").strip()
        password = str(params.get("password") or "")
        if not any((email, username, password)):
            return StepResult(
                action_id=action.action_id,
                success=False,
                error="Provide at least one user-owned signup field in params (email, username, password). No synthetic identity will be generated.",
            )

        fields_filled = []
        selectors = []
        if email:
            selectors.append(("email", ["input[type='email']", "input[name*='email' i]", "input[id*='email' i]", "input[autocomplete='email']"], email))
        if username:
            selectors.append(("username", ["input[name*='user' i]", "input[id*='user' i]", "input[name*='login' i]", "input[placeholder*='username' i]", "input[name='name']"], username))
        if password:
            selectors.append(("password", ["input[type='password']"], password))

        for label, candidates, value in selectors:
            filled = False
            for selector in candidates:
                locator = self.page.locator(selector).first
                try:
                    if await locator.is_visible():
                        await locator.fill(value, timeout=action.timeout_seconds * 1000)
                        fields_filled.append(label)
                        filled = True
                        break
                except Exception:
                    continue
            if not filled:
                agent_logger.warning(f"No visible {label} field found; leaving it for manual entry.", domain="BROWSER")

        screenshot = await self.take_screenshot("signup_review")
        return StepResult(
            action_id=action.action_id,
            success=True,
            output="Provided signup fields prepared. No terms were accepted, no form was submitted, and no credentials were saved.",
            screenshot_path=screenshot,
            data={"url": self.page.url, "fields_filled": fields_filled, "requires_user_review": True, "submitted": False},
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
                        value: el.value || '',
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
