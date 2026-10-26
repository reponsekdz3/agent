import os
import random
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from nova_apex.config.settings import settings
from nova_apex.core.logger import agent_logger
from nova_apex.core.schemas import StepResult, ActionRequest
from nova_apex.core.memory import agent_memory
from nova_apex.controllers.stealth_profile import STEALTH_EVASION_SCRIPT, generate_bezier_curve

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

        # Standard standalone launch with advanced bot-evasion flags
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-infobars",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-accelerated-2d-canvas",
            "--no-first-run",
            "--no-zygote",
            "--window-size=1440,900"
        ]

        # Select browser driver
        if browser_type.lower() == "firefox":
            self.browser = await self.playwright.firefox.launch(headless=settings.browser_headless)
        elif browser_type.lower() == "webkit":
            self.browser = await self.playwright.webkit.launch(headless=settings.browser_headless)
        else:
            self.browser = await self.playwright.chromium.launch(
                headless=settings.browser_headless,
                args=launch_args
            )

        storage_path = str(self.state_file) if self.state_file.exists() else None

        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        )

        self.context = await self.browser.new_context(
            user_agent=user_agent,
            viewport={"width": settings.browser_viewport_width, "height": settings.browser_viewport_height},
            device_scale_factor=1.0,
            locale="en-US",
            timezone_id="America/New_York",
            has_touch=False,
            is_mobile=False,
            storage_state=storage_path
        )

        # Inject comprehensive stealth evasion scripts
        await self.context.add_init_script(STEALTH_EVASION_SCRIPT)

        self.page = await self.context.new_page()
        self._is_initialized = True
        agent_logger.success("Ultra-Stealth browser subsystem online & hardened against bot-detection.", domain="BROWSER")

    async def human_mouse_move(self, target_x: float, target_y: float):
        """
        Executes human-like mouse movement along a randomized Bézier curve trajectory.
        """
        curve = generate_bezier_curve(self._cursor_pos, (target_x, target_y), num_points=18)
        for pt in curve:
            await self.page.mouse.move(pt[0], pt[1])
            await asyncio.sleep(random.uniform(0.005, 0.015))
        self._cursor_pos = (target_x, target_y)

    async def human_type(self, selector: str, text: str):
        """
        Types text with realistic Gaussian latency and occasional human cadence pauses.
        """
        await self.page.focus(selector)
        for char in text:
            await self.page.keyboard.type(char)
            # Gaussian delay around 65ms, occasionally slower
            delay = max(0.02, random.gauss(0.065, 0.025))
            if char in " .,@_#-":
                delay += random.uniform(0.05, 0.12)  # Pause naturally on punctuation
            await asyncio.sleep(delay)

    async def execute_action(self, action: ActionRequest) -> StepResult:
        await self.initialize()
        action_type = action.action_type.value

        try:
            if action_type == "navigate":
                url = agent_memory.resolve_placeholders(action.target or action.value)
                if not url.startswith("http://") and not url.startswith("https://"):
                    url = f"https://{url}"
                agent_logger.action(f"Stealth navigating to {url}", domain="BROWSER")
                await self.page.goto(url, wait_until="domcontentloaded", timeout=action.timeout_seconds * 1000)
                await asyncio.sleep(random.uniform(1.0, 1.8))  # Human settling delay
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
                selector = action.target
                agent_logger.action(f"Locating & human-clicking element: {selector}", domain="BROWSER")
                
                # Check if target is coordinate "x,y"
                if "," in selector and all(p.strip().isdigit() for p in selector.replace("(", "").replace(")", "").split(",")):
                    coords = [int(p.strip()) for p in selector.replace("(", "").replace(")", "").split(",")]
                    await self.human_mouse_move(coords[0], coords[1])
                    await self.page.mouse.click(coords[0], coords[1], delay=random.randint(40, 90))
                else:
                    el = await self.page.wait_for_selector(selector, state="visible", timeout=action.timeout_seconds * 1000)
                    box = await el.bounding_box()
                    if box:
                        target_x = box["x"] + box["width"] / 2 + random.uniform(-4, 4)
                        target_y = box["y"] + box["height"] / 2 + random.uniform(-4, 4)
                        await self.human_mouse_move(target_x, target_y)
                        await self.page.mouse.click(target_x, target_y, delay=random.randint(40, 90))
                    else:
                        await el.click(delay=random.randint(40, 90))

                await asyncio.sleep(random.uniform(0.4, 0.8))
                shot = await self.take_screenshot("click_result")
                return StepResult(action_id=action.action_id, success=True, output=f"Human-clicked {selector}", screenshot_path=shot)

            elif action_type == "type_element":
                selector = action.target
                raw_text = action.value or ""
                text_to_type = agent_memory.resolve_placeholders(raw_text)
                masked_repr = '*' * len(text_to_type) if any(s in selector.lower() for s in ['pass', 'pwd', 'secret']) else text_to_type
                agent_logger.action(f"Human-typing into {selector}: {masked_repr}", domain="BROWSER")
                
                el = await self.page.wait_for_selector(selector, state="visible", timeout=action.timeout_seconds * 1000)
                box = await el.bounding_box()
                if box:
                    await self.human_mouse_move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                    await self.page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                else:
                    await el.click()
                
                await self.page.fill(selector, "")
                await self.human_type(selector, text_to_type)
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
        """
        Autonomous Multi-Stage Registration Engine:
        Analyzes form fields, generates secure realistic credentials, fills with human cadence,
        and saves credentials to the secure vault.
        """
        agent_logger.info("Scanning page for registration fields...", domain="BROWSER")
        import string

        rand_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        generated_username = f"nova_agent_{rand_id}"
        generated_email = f"nova_agent_{rand_id}@inboxnova.org"
        generated_password = f"NovaApex#2026_{''.join(random.choices(string.ascii_letters + string.digits, k=8))}"

        fields_filled = []

        # Find email field
        email_selectors = [
            "input[type='email']", "input[name*='email' i]", "input[id*='email' i]",
            "input[placeholder*='email' i]", "input[autocomplete='email']"
        ]
        for sel in email_selectors:
            if await self.page.is_visible(sel):
                await self.human_type(sel, generated_email)
                fields_filled.append(f"Email ({sel}) -> {generated_email}")
                break

        # Find username / name field
        user_selectors = [
            "input[name*='user' i]", "input[id*='user' i]", "input[name*='login' i]",
            "input[placeholder*='username' i]", "input[name='name']"
        ]
        for sel in user_selectors:
            if await self.page.is_visible(sel):
                await self.human_type(sel, generated_username)
                fields_filled.append(f"Username ({sel}) -> {generated_username}")
                break

        # Find password fields
        pass_selectors = [
            "input[type='password']", "input[name*='pass' i]", "input[id*='pass' i]"
        ]
        pass_inputs = await self.page.query_selector_all("input[type='password']")
        if pass_inputs:
            for p in pass_inputs:
                try:
                    box = await p.bounding_box()
                    if box:
                        await self.human_mouse_move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                        await p.click()
                        await self.page.keyboard.type(generated_password)
                        fields_filled.append("Password input filled")
                except Exception:
                    pass
        else:
            for sel in pass_selectors:
                if await self.page.is_visible(sel):
                    await self.human_type(sel, generated_password)
                    fields_filled.append(f"Password ({sel})")
                    break

        # Accept terms checkbox if present
        checkboxes = await self.page.query_selector_all("input[type='checkbox']")
        for cb in checkboxes:
            try:
                if not await cb.is_checked():
                    await cb.check()
                    fields_filled.append("Agreed to terms checkbox")
            except Exception:
                pass

        # Save to memory vault
        current_url = self.page.url
        service_name = current_url.split("//")[-1].split("/")[0]
        agent_memory.store_credential(
            service=service_name,
            username=generated_username,
            secret=generated_password,
            extra={"email": generated_email, "url": current_url, "fields": fields_filled}
        )

        shot = await self.take_screenshot("form_filled")

        # Submit button detection
        submit_btn = await self.page.query_selector(
            "button[type='submit'], input[type='submit'], button:has-text('Sign up'), button:has-text('Register'), button:has-text('Continue')"
        )
        if submit_btn:
            try:
                box = await submit_btn.bounding_box()
                if box:
                    await self.human_mouse_move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                await submit_btn.click()
                await asyncio.sleep(2)
                agent_logger.success("Clicked registration submit button.", domain="BROWSER")
            except Exception as e:
                agent_logger.warning(f"Could not auto-click submit: {e}", domain="BROWSER")

        return StepResult(
            action_id=action.action_id,
            success=True,
            output=f"Auto-filled account registration fields on {service_name}. Credentials persisted to vault.",
            screenshot_path=shot,
            data={
                "service": service_name,
                "username": generated_username,
                "email": generated_email,
                "fields_filled": fields_filled
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
