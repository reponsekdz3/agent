import os
import sys
import time
import subprocess
import ctypes
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from PIL import ImageGrab, Image, ImageDraw, ImageFont
import pyautogui
from nova_apex.config.settings import settings
from nova_apex.core.logger import agent_logger
from nova_apex.core.schemas import StepResult, ActionRequest
from nova_apex.core.memory import agent_memory

# Win32 API handles for deep OS window control
user32 = ctypes.windll.user32 if hasattr(ctypes, "windll") else None

# Configure PyAutoGUI failsafe
pyautogui.FAILSAFE = settings.desktop_safety_failsafe
pyautogui.PAUSE = settings.desktop_action_pause

class DesktopController:
    """
    Deep OS and Windows Native Controller:
    - Mouse & keyboard automation with PyAutoGUI (clicks, drags, scrolls, typing)
    - Native Win32 API window manager (enumerate, focus, restore, title inspection)
    - Clipboard manager (read/write system clipboard)
    - Multimodal screen perception with coordinate grid overlay (Set-of-Marks)
    - Complete file system manipulation (create, read, write, folder hierarchy)
    """

    def __init__(self):
        try:
            self.screen_width, self.screen_height = pyautogui.size()
        except Exception:
            self.screen_width, self.screen_height = 1920, 1080
        agent_logger.info(f"Desktop GUI controller initialized. Screen size: {self.screen_width}x{self.screen_height}", domain="DESKTOP")

    # --- Win32 Native Window Management ---
    def list_open_windows(self) -> List[Dict[str, Any]]:
        if not user32:
            return []
        windows = []

        def enum_windows_proc(hwnd, lParam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    title = buff.value.strip()
                    if title and title not in ["Program Manager", "Default IME", "MSCTFIME UI"]:
                        windows.append({"hwnd": hwnd, "title": title})
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
        user32.EnumWindows(WNDENUMPROC(enum_windows_proc), 0)
        return windows

    def focus_window_by_title(self, target_title: str) -> bool:
        if not user32:
            return False
        windows = self.list_open_windows()
        target_lower = target_title.lower()
        for w in windows:
            if target_lower in w["title"].lower():
                hwnd = w["hwnd"]
                user32.ShowWindow(hwnd, 9) # SW_RESTORE
                user32.SetForegroundWindow(hwnd)
                agent_logger.success(f"Focused active window: '{w['title']}' (HWND: {hwnd})", domain="DESKTOP")
                return True
        return False

    def get_foreground_window_title(self) -> str:
        if not user32:
            return ""
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            return buff.value.strip()
        return ""

    # --- Clipboard Automation ---
    def read_clipboard(self) -> str:
        try:
            import pyperclip
            return pyperclip.paste()
        except Exception:
            return ""

    def write_clipboard(self, text: str):
        try:
            import pyperclip
            pyperclip.copy(text)
            agent_logger.info("Updated system clipboard", domain="DESKTOP")
        except Exception:
            pass

    # --- Action Dispatcher ---
    def execute_action(self, action: ActionRequest) -> StepResult:
        action_type = action.action_type.value
        try:
            # --- GUI Mouse & Keyboard Operations ---
            if action_type == "desktop_click":
                x, y = self._parse_coordinates(action.target)
                agent_logger.action(f"Desktop click at ({x}, {y})", domain="DESKTOP")
                pyautogui.moveTo(x, y, duration=0.25)
                pyautogui.click()
                shot = self.take_screenshot("click")
                return StepResult(action_id=action.action_id, success=True, output=f"Clicked at ({x}, {y})", screenshot_path=shot)

            elif action_type == "desktop_double_click":
                x, y = self._parse_coordinates(action.target)
                agent_logger.action(f"Desktop double-click at ({x}, {y})", domain="DESKTOP")
                pyautogui.moveTo(x, y, duration=0.25)
                pyautogui.doubleClick()
                shot = self.take_screenshot("double_click")
                return StepResult(action_id=action.action_id, success=True, output=f"Double clicked at ({x}, {y})", screenshot_path=shot)

            elif action_type == "desktop_drag":
                p = action.params
                x1, y1 = p.get("x1", 500), p.get("y1", 500)
                x2, y2 = p.get("x2", 800), p.get("y2", 500)
                agent_logger.action(f"Desktop dragging ({x1},{y1}) -> ({x2},{y2})", domain="DESKTOP")
                pyautogui.moveTo(x1, y1)
                pyautogui.dragTo(x2, y2, duration=0.5, button='left')
                shot = self.take_screenshot("drag")
                return StepResult(action_id=action.action_id, success=True, output=f"Dragged to ({x2}, {y2})", screenshot_path=shot)

            elif action_type == "desktop_scroll":
                clicks = int(action.value or action.target or "-3")
                agent_logger.action(f"Desktop scroll {clicks} units", domain="DESKTOP")
                pyautogui.scroll(clicks * 100)
                return StepResult(action_id=action.action_id, success=True, output=f"Scrolled {clicks} units")

            elif action_type == "desktop_type":
                text = agent_memory.resolve_placeholders(action.value or action.target or "")
                agent_logger.action(f"Typing {len(text)} character(s) into the active desktop field.", domain="DESKTOP")
                pyautogui.write(text, interval=0.04)
                shot = self.take_screenshot("typed")
                return StepResult(action_id=action.action_id, success=True, output="Typed text into active window", screenshot_path=shot)

            elif action_type == "desktop_hotkey":
                keys = [k.strip() for k in (action.value or action.target or "").split("+")]
                agent_logger.action(f"Pressing hotkey combination: {keys}", domain="DESKTOP")
                pyautogui.hotkey(*keys)
                return StepResult(action_id=action.action_id, success=True, output=f"Hotkey {'+'.join(keys)} pressed")

            elif action_type == "focus_window":
                window_query = action.target or action.value
                found = self.focus_window_by_title(window_query)
                if found:
                    return StepResult(action_id=action.action_id, success=True, output=f"Focused window matching '{window_query}'")
                return StepResult(action_id=action.action_id, success=False, error=f"No window found matching '{window_query}'")

            elif action_type == "desktop_screenshot":
                shot = self.take_screenshot("manual", overlay_grid=action.params.get("overlay_grid", False))
                return StepResult(
                    action_id=action.action_id,
                    success=True,
                    output=f"Desktop screenshot captured: {shot}",
                    screenshot_path=shot,
                    data={"active_window": self.get_foreground_window_title()}
                )

            elif action_type == "clipboard_read":
                clip_text = self.read_clipboard()
                agent_memory.set_working("clipboard", clip_text)
                return StepResult(action_id=action.action_id, success=True, output=f"Read {len(clip_text)} chars from clipboard", data={"text": clip_text})

            elif action_type == "clipboard_write":
                text = agent_memory.resolve_placeholders(action.value or action.target or "")
                self.write_clipboard(text)
                return StepResult(action_id=action.action_id, success=True, output=f"Wrote text to clipboard: '{text[:25]}...'")

            elif action_type == "raw_keystroke":
                from nova_apex.controllers.win32_native import win32_subsystem
                raw_text = agent_memory.resolve_placeholders(action.value or action.target or "")
                agent_logger.action(f"Dispatching {len(raw_text)} low-level keystroke character(s).", domain="DESKTOP")
                count = 0
                for ch in raw_text:
                    if win32_subsystem.send_hardware_unicode_char(ch):
                        count += 1
                return StepResult(action_id=action.action_id, success=True, output=f"Injected {count} raw keystrokes via Win32 SendInput")

            elif action_type == "direct_window_message":
                from nova_apex.controllers.win32_native import win32_subsystem
                hwnd = int(action.params.get("hwnd", 0))
                msg = int(action.params.get("msg", 0))
                wparam = int(action.params.get("wparam", 0))
                lparam = int(action.params.get("lparam", 0))
                agent_logger.action(f"Sending direct Win32 message 0x{msg:X} to HWND {hwnd}", domain="DESKTOP")
                res = win32_subsystem.send_direct_window_message(hwnd, msg, wparam, lparam)
                return StepResult(action_id=action.action_id, success=True, output=f"Win32 SendMessageW returned {res}", data={"result": res})

            elif action_type == "enumerate_hardware":
                from nova_apex.controllers.win32_native import win32_subsystem
                devices = win32_subsystem.enumerate_system_devices()
                agent_logger.info(f"Hardware enumerated: {len(devices['monitors'])} display(s), {len(devices['logical_drives'])} drive(s)", domain="DESKTOP")
                return StepResult(action_id=action.action_id, success=True, output=f"Found {len(devices['monitors'])} displays and drives {devices['logical_drives']}", data=devices)

            elif action_type == "launch_app":
                app_path = action.target or action.value
                agent_logger.action(f"Launching desktop application: {app_path}", domain="DESKTOP")
                proc = subprocess.Popen(app_path, shell=True)
                return StepResult(action_id=action.action_id, success=True, output=f"Launched process with PID {proc.pid}", data={"pid": proc.pid})

            # --- File System Operations ---
            elif action_type == "create_folder":
                folder_path = self._resolve_path(action.target or action.value)
                folder_path.mkdir(parents=True, exist_ok=True)
                agent_logger.success(f"Created directory: {folder_path}", domain="FILESYSTEM")
                return StepResult(action_id=action.action_id, success=True, output=f"Folder created: {folder_path}")

            elif action_type in ["create_file", "write_file"]:
                file_path = self._resolve_path(action.target)
                file_path.parent.mkdir(parents=True, exist_ok=True)
                content = agent_memory.resolve_placeholders(action.value or "")
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                agent_logger.success(f"Wrote {len(content)} characters to {file_path}", domain="FILESYSTEM")
                return StepResult(action_id=action.action_id, success=True, output=f"Successfully written to {file_path}", data={"path": str(file_path), "bytes": len(content)})

            elif action_type == "read_file":
                file_path = self._resolve_path(action.target)
                if not file_path.exists():
                    return StepResult(action_id=action.action_id, success=False, error=f"File not found: {file_path}")
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                return StepResult(action_id=action.action_id, success=True, output=content, data={"size": len(content)})

            elif action_type == "delete_file":
                file_path = self._resolve_path(action.target)
                if file_path.resolve() == settings.workspace_dir.resolve():
                    return StepResult(action_id=action.action_id, success=False, error="Refusing to delete the workspace root.")
                if file_path.exists():
                    if file_path.is_file():
                        file_path.unlink()
                    elif file_path.is_dir():
                        import shutil
                        shutil.rmtree(file_path)
                    return StepResult(action_id=action.action_id, success=True, output=f"Deleted {file_path}")
                return StepResult(action_id=action.action_id, success=False, error=f"Target path does not exist: {file_path}")

            elif action_type == "list_directory":
                dir_path = self._resolve_path(action.target or ".")
                if not dir_path.exists():
                    return StepResult(action_id=action.action_id, success=False, error=f"Directory does not exist: {dir_path}")
                items = [str(p.name) + ("/" if p.is_dir() else "") for p in dir_path.iterdir()]
                return StepResult(action_id=action.action_id, success=True, output="\n".join(items), data={"items": items})

            else:
                return StepResult(action_id=action.action_id, success=False, error=f"Unknown desktop/filesystem action: {action_type}")

        except Exception as e:
            agent_logger.error(f"Desktop/Filesystem action failed: {e}", domain="DESKTOP")
            return StepResult(action_id=action.action_id, success=False, error=str(e))

    def _parse_coordinates(self, target: Optional[str]) -> tuple:
        if not target:
            return self.screen_width // 2, self.screen_height // 2
        try:
            parts = target.replace("(", "").replace(")", "").split(",")
            return int(parts[0].strip()), int(parts[1].strip())
        except Exception:
            return self.screen_width // 2, self.screen_height // 2

    def _resolve_path(self, path_str: str) -> Path:
        p = Path(path_str)
        if not p.is_absolute():
            p = settings.workspace_dir / p
        return p

    def take_screenshot(self, name: str = "desktop", overlay_grid: bool = False) -> str:
        filename = f"{name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}.png"
        filepath = settings.artifacts_dir / filename
        img = None
        try:
            img = ImageGrab.grab()
        except Exception:
            # Fallback for headless environments or Windows Session 0
            w = self.screen_width or 1920
            h = self.screen_height or 1080
            img = Image.new("RGB", (w, h), color=(15, 18, 25))
            draw = ImageDraw.Draw(img)
            draw.rectangle([20, 20, w - 20, h - 20], outline=(0, 240, 255), width=2)
            draw.text((50, 50), "NOVA-APEX DESKTOP OS BUFFER // HEADLESS DC CAPTURE", fill=(0, 240, 255))
            draw.text((50, 80), f"Active Window: {self.get_foreground_window_title() or 'None'}", fill=(200, 200, 200))
            draw.text((50, 110), f"Timestamp: {datetime.utcnow().isoformat()}", fill=(150, 150, 150))

        # Optional Coordinate Grid Overlay (Set-of-Marks) for visual AI models
        if overlay_grid and img:
            draw = ImageDraw.Draw(img)
            w, h = img.size
            step_x = w // 10
            step_y = h // 10
            for gx in range(0, w, step_x):
                draw.line([(gx, 0), (gx, h)], fill=(0, 240, 255, 60), width=1)
            for gy in range(0, h, step_y):
                draw.line([(0, gy), (w, gy)], fill=(0, 240, 255, 60), width=1)
                for gx in range(0, w, step_x):
                    draw.text((gx + 4, gy + 4), f"{gx},{gy}", fill=(0, 240, 255))

        img.save(str(filepath))
        return str(filepath)

desktop_controller = DesktopController()
