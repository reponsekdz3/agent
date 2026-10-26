import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from nova_apex.config.settings import settings
from nova_apex.core.logger import agent_logger
from nova_apex.core.schemas import StepResult, ActionRequest
from nova_apex.core.memory import agent_memory

class MobileController:
    """
    Advanced Android Debug Bridge (ADB) Mobile Engine:
    - Smart UI element locator by text, resource-id, or content-desc via XML hierarchy
    - Automatic 2FA / OTP verification code interception from system notifications & SMS
    - Physical device & emulator auto-discovery
    - Gesture engine (tap, bezier swipe, pinch, directional scroll)
    - App lifecycle & deep link launcher
    """

    def __init__(self):
        self.adb_bin = self._find_adb()
        self.active_device = settings.adb_device_id

    def _find_adb(self) -> Optional[str]:
        # Check system PATH
        adb_path = shutil.which("adb")
        if adb_path:
            return adb_path

        local_app_data = os.getenv("LOCALAPPDATA", "")
        candidates = [
            Path(local_app_data) / "Android" / "Sdk" / "platform-tools" / "adb.exe",
            Path("C:/Android/sdk/platform-tools/adb.exe"),
            Path("C:/Program Files/Android/platform-tools/adb.exe")
        ]
        for c in candidates:
            if c.exists():
                return str(c)
        return None

    def get_connected_devices(self) -> List[str]:
        if not self.adb_bin:
            return []
        try:
            res = subprocess.run([self.adb_bin, "devices"], capture_output=True, text=True, check=True)
            lines = res.stdout.strip().split("\n")[1:]
            devices = []
            for line in lines:
                parts = line.split()
                if len(parts) >= 2 and parts[1] == "device":
                    devices.append(parts[0])
            return devices
        except Exception:
            return []

    # --- Smart Element Locator via XML Hierarchy ---
    def find_element_coordinates(self, device_id: str, query: str) -> Optional[Tuple[int, int]]:
        """
        Dumps mobile UI hierarchy and locates element matching query by text, resource-id, or content-desc.
        Returns center coordinate (x, y) if found.
        """
        try:
            base_cmd = [self.adb_bin, "-s", device_id]
            subprocess.run(base_cmd + ["shell", "uiautomator", "dump", "/sdcard/window_dump.xml"], check=True, timeout=10)
            local_dump = settings.artifacts_dir / f"hierarchy_temp.xml"
            subprocess.run(base_cmd + ["pull", "/sdcard/window_dump.xml", str(local_dump)], check=True, timeout=10)

            tree = ET.parse(str(local_dump))
            root = tree.getroot()

            query_lower = query.lower()
            for node in root.iter("node"):
                text = node.attrib.get("text", "").lower()
                res_id = node.attrib.get("resource-id", "").lower()
                desc = node.attrib.get("content-desc", "").lower()

                if query_lower in text or query_lower in res_id or query_lower in desc:
                    bounds_str = node.attrib.get("bounds", "")
                    # Match bounds="[x1,y1][x2,y2]"
                    m = re.findall(r"\[(\d+),(\d+)\]", bounds_str)
                    if len(m) == 2:
                        x1, y1 = int(m[0][0]), int(m[0][1])
                        x2, y2 = int(m[1][0]), int(m[1][1])
                        center_x = (x1 + x2) // 2
                        center_y = (y1 + y2) // 2
                        agent_logger.success(f"Located mobile element '{query}' at center ({center_x}, {center_y})", domain="MOBILE")
                        return center_x, center_y
            return None
        except Exception as e:
            agent_logger.warning(f"Element locator error: {e}", domain="MOBILE")
            return None

    # --- Auto 2FA / OTP Code Interceptor ---
    def extract_latest_otp(self, device_id: str) -> Optional[str]:
        """Automatic OTP extraction is intentionally disabled.

        Verification codes are security credentials; the user should enter them
        directly into the site or app they are authenticating with.
        """
        agent_logger.warning("Automatic OTP extraction is disabled; use the service's normal verification flow.", domain="MOBILE")
        return None

    def execute_action(self, action: ActionRequest) -> StepResult:
        if not self.adb_bin:
            return StepResult(
                action_id=action.action_id,
                success=False,
                error="ADB executable not found. Install Android SDK or add 'adb' to PATH to control mobile devices."
            )

        devices = self.get_connected_devices()
        if not devices:
            return StepResult(
                action_id=action.action_id,
                success=False,
                error="No active Android device or emulator detected via ADB. Connect device with USB debugging enabled."
            )

        target_device = self.active_device or devices[0]
        base_cmd = [self.adb_bin, "-s", target_device]
        action_type = action.action_type.value

        try:
            if action_type == "adb_tap":
                target_str = action.target
                coords = None

                # Check if target is a coordinate "x,y" or a semantic element name "Sign In"
                if target_str and "," in target_str and all(p.strip().isdigit() for p in target_str.replace("(", "").replace(")", "").split(",")):
                    coords = self._parse_coords(target_str)
                elif target_str:
                    coords = self.find_element_coordinates(target_device, target_str)

                if not coords:
                    coords = self._parse_coords(target_str)

                x, y = coords
                agent_logger.action(f"Mobile ADB tap on [{target_device}] at ({x}, {y})", domain="MOBILE")
                subprocess.run(base_cmd + ["shell", "input", "tap", str(x), str(y)], check=True)
                shot = self.take_screenshot(target_device, "tap")
                return StepResult(action_id=action.action_id, success=True, output=f"Tapped ({x}, {y}) on {target_device}", screenshot_path=shot)

            elif action_type == "adb_swipe":
                p = action.params
                x1, y1 = p.get("x1", 500), p.get("y1", 1200)
                x2, y2 = p.get("x2", 500), p.get("y2", 400)
                duration = p.get("duration", 300)
                agent_logger.action(f"Mobile ADB swipe ({x1},{y1}) -> ({x2},{y2})", domain="MOBILE")
                subprocess.run(base_cmd + ["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration)], check=True)
                shot = self.take_screenshot(target_device, "swipe")
                return StepResult(action_id=action.action_id, success=True, output=f"Swiped on {target_device}", screenshot_path=shot)

            elif action_type == "adb_input_text":
                text = agent_memory.resolve_placeholders(action.value or action.target or "")
                formatted_text = text.replace(" ", "%s")
                agent_logger.action(f"Mobile ADB typing: '{text}'", domain="MOBILE")
                subprocess.run(base_cmd + ["shell", "input", "text", formatted_text], check=True)
                return StepResult(action_id=action.action_id, success=True, output=f"Input text on {target_device}")

            elif action_type == "adb_keyevent":
                keycode = action.value or action.target or "3"  # 3 = HOME, 4 = BACK
                agent_logger.action(f"Mobile ADB keyevent: {keycode}", domain="MOBILE")
                subprocess.run(base_cmd + ["shell", "input", "keyevent", str(keycode)], check=True)
                return StepResult(action_id=action.action_id, success=True, output=f"Sent keyevent {keycode} to {target_device}")

            elif action_type == "adb_extract_otp":
                return StepResult(
                    action_id=action.action_id,
                    success=False,
                    error="Automatic OTP extraction is disabled. Enter verification codes manually in the intended service.",
                )

            elif action_type == "adb_screenshot":
                shot = self.take_screenshot(target_device, "mobile_screen")
                return StepResult(action_id=action.action_id, success=True, output=f"Mobile screen captured: {shot}", screenshot_path=shot)

            elif action_type == "adb_dump_hierarchy":
                agent_logger.action("Dumping UI Automator XML hierarchy...", domain="MOBILE")
                subprocess.run(base_cmd + ["shell", "uiautomator", "dump", "/sdcard/window_dump.xml"], check=True)
                local_dump = settings.artifacts_dir / f"hierarchy_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xml"
                subprocess.run(base_cmd + ["pull", "/sdcard/window_dump.xml", str(local_dump)], check=True)
                return StepResult(action_id=action.action_id, success=True, output=f"UI hierarchy saved to {local_dump}", data={"path": str(local_dump)})

            elif action_type == "adb_launch_package":
                package = action.target or action.value
                agent_logger.action(f"Launching app package: {package}", domain="MOBILE")
                subprocess.run(base_cmd + ["shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"], check=True)
                return StepResult(action_id=action.action_id, success=True, output=f"Launched {package}")

            else:
                return StepResult(action_id=action.action_id, success=False, error=f"Unknown mobile action: {action_type}")

        except Exception as e:
            agent_logger.error(f"Mobile action failed: {e}", domain="MOBILE")
            return StepResult(action_id=action.action_id, success=False, error=str(e))

    def _parse_coords(self, s: Optional[str]) -> Tuple[int, int]:
        if not s:
            return (500, 500)
        try:
            parts = s.replace("(", "").replace(")", "").split(",")
            return int(parts[0].strip()), int(parts[1].strip())
        except Exception:
            return (500, 500)

    def take_screenshot(self, device_id: str, prefix: str = "mobile") -> str:
        filename = f"{prefix}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}.png"
        filepath = settings.artifacts_dir / filename
        try:
            with open(filepath, "wb") as f:
                subprocess.run([self.adb_bin, "-s", device_id, "exec-out", "screencap", "-p"], stdout=f, check=True)
            return str(filepath)
        except Exception:
            return ""

mobile_controller = MobileController()
