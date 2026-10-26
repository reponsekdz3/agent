import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from nova_apex.controllers.win32_native import win32_subsystem
from nova_apex.controllers.desktop_controller import desktop_controller
from nova_apex.core.schemas import ActionDomain, ActionType, ActionRequest

def run_low_level_tests():
    print("=======================================================")
    print("🔬 TESTING LOW-LEVEL WIN32 & DEVICE AUTOMATION LAYER")
    print("=======================================================\n")

    # 1. Enumerate low-level hardware devices
    print("[1/3] Testing hardware device and monitor enumeration...")
    hw_req = ActionRequest(
        domain=ActionDomain.DESKTOP,
        action_type=ActionType.ENUMERATE_HARDWARE,
        description="Enumerate hardware displays and storage drives"
    )
    hw_res = desktop_controller.execute_action(hw_req)
    assert hw_res.success, f"Hardware enumeration failed: {hw_res.error}"
    print(f"  ✓ Found {len(hw_res.data['monitors'])} display monitor(s): {hw_res.data['monitors']}")
    print(f"  ✓ Found logical drives: {hw_res.data['logical_drives']}")

    # 2. Test Low-Level Win32 SendInput Unicode Character Injection
    print("\n[2/3] Testing Win32 SendInput direct keystroke injection...")
    raw_req = ActionRequest(
        domain=ActionDomain.DESKTOP,
        action_type=ActionType.RAW_KEYSTROKE,
        description="Inject raw keystrokes via Win32 SendInput",
        value="NovaApex"
    )
    raw_res = desktop_controller.execute_action(raw_req)
    assert raw_res.success, f"Raw keystroke failed: {raw_res.error}"
    print(f"  ✓ Direct Win32 SendInput dispatch successful: {raw_res.output}")

    # 3. Test Window Enumeration and Direct HWND Query
    print("\n[3/3] Testing Win32 HWND enumeration...")
    windows = desktop_controller.list_open_windows()
    print(f"  ✓ Enumerated {len(windows)} visible top-level window(s) via Win32 EnumWindows.")
    for w in windows[:3]:
        print(f"    - HWND {w['hwnd']}: '{w['title'][:50]}'")

    print("\n=======================================================")
    print("🎉 LOW-LEVEL WIN32 SUBSYSTEM OPERATIONAL AND VERIFIED!")
    print("=======================================================\n")

if __name__ == "__main__":
    run_low_level_tests()
