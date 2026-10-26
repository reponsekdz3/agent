import ctypes
from ctypes import wintypes
from typing import List, Dict, Any, Optional

# Win32 Native Handles
user32 = ctypes.windll.user32 if hasattr(ctypes, "windll") else None
kernel32 = ctypes.windll.kernel32 if hasattr(ctypes, "windll") else None

# Low-level Input Constants
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
INPUT_HARDWARE = 2

KEYEVENTF_KEYDOWN = 0x0000
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_ABSOLUTE = 0x8000

# Ctypes Structures for Win32 SendInput
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_ulonglong)
    ]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_ulonglong)
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD)
    ]

class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT)
    ]

class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", INPUT_UNION)
    ]

class Win32NativeSubsystem:
    """
    Direct low-level Win32 and OS interaction layer:
    - Raw SendInput dispatching hardware scancodes directly to Windows input subsystem
    - Window message pump interaction (SendMessageW/PostMessageW)
    - Low-level device enumeration (drives, volumes, display metrics)
    """

    @staticmethod
    def send_hardware_keystroke(scan_code: int, keyup: bool = False) -> bool:
        """
        Dispatches hardware-level scancode input directly to the Win32 input queue.
        """
        if not user32:
            return False

        flags = KEYEVENTF_SCANCODE
        if keyup:
            flags |= KEYEVENTF_KEYUP

        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.union.ki = KEYBDINPUT(
            wVk=0,
            wScan=scan_code,
            dwFlags=flags,
            time=0,
            dwExtraInfo=0
        )

        sent = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        return sent == 1

    @staticmethod
    def send_hardware_unicode_char(char: str) -> bool:
        """
        Dispatches native Unicode characters directly into the focused window message stream.
        """
        if not user32 or not char:
            return False

        code = ord(char)
        # Key down
        inp_down = INPUT()
        inp_down.type = INPUT_KEYBOARD
        inp_down.union.ki = KEYBDINPUT(
            wVk=0,
            wScan=code,
            dwFlags=KEYEVENTF_UNICODE,
            time=0,
            dwExtraInfo=0
        )

        # Key up
        inp_up = INPUT()
        inp_up.type = INPUT_KEYBOARD
        inp_up.union.ki = KEYBDINPUT(
            wVk=0,
            wScan=code,
            dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
            time=0,
            dwExtraInfo=0
        )

        inputs = (INPUT * 2)(inp_down, inp_up)
        sent = user32.SendInput(2, inputs, ctypes.sizeof(INPUT))
        return sent == 2

    @staticmethod
    def send_direct_window_message(hwnd: int, msg: int, wparam: int = 0, lparam: int = 0) -> int:
        """
        Sends low-level Win32 message (e.g. WM_CLOSE, BM_CLICK, WM_COMMAND) directly to an HWND.
        """
        if not user32:
            return 0
        return user32.SendMessageW(hwnd, msg, wparam, lparam)

    @staticmethod
    def enumerate_system_devices() -> Dict[str, Any]:
        """
        Enumerates hardware-level device details: logical volumes, display monitors, and architecture.
        """
        devices = {
            "monitors": [],
            "logical_drives": []
        }

        # Enumerate display monitors
        if user32:
            def monitor_enum_proc(hMonitor, hdcMonitor, lprcMonitor, dwData):
                rect = lprcMonitor.contents
                devices["monitors"].append({
                    "handle": int(hMonitor),
                    "left": rect.left,
                    "top": rect.top,
                    "right": rect.right,
                    "bottom": rect.bottom,
                    "width": rect.right - rect.left,
                    "height": rect.bottom - rect.top
                })
                return True

            MONITORENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_ulong, ctypes.c_ulong, ctypes.POINTER(wintypes.RECT), ctypes.c_double)
            user32.EnumDisplayMonitors(0, 0, MONITORENUMPROC(monitor_enum_proc), 0)

        # Enumerate logical drives
        if kernel32:
            bitmask = kernel32.GetLogicalDrives()
            for letter in range(26):
                if bitmask & (1 << letter):
                    drive_letter = f"{chr(65 + letter)}:\\"
                    devices["logical_drives"].append(drive_letter)

        return devices

win32_subsystem = Win32NativeSubsystem()
