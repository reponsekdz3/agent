from nexuscam.settings import AppSettings, CaptureCfg
from nexuscam.capture.multicam import MultiCameraManager
from nexuscam.bus.frame_bus import FrameBus
from nexuscam.capture.registry import open_source


def test_add_remove_synthetic():
    settings = AppSettings()
    settings.capture = CaptureCfg(backend="demo", auto_open_all_usb=False, include_pc_camera=False)
    bus = FrameBus(depth=2)
    mgr = MultiCameraManager(settings, bus)
    mgr.start()
    src = open_source(settings, override="demo")
    sid = mgr.add_source(src)
    assert sid in mgr.list_ids()
    mgr.remove_source(sid)
    assert sid not in mgr.list_ids()
    mgr.stop()


def test_describe_demo_source():
    settings = AppSettings()
    settings.capture = CaptureCfg(backend="demo", auto_open_all_usb=False, include_pc_camera=False)
    bus = FrameBus(depth=2)
    mgr = MultiCameraManager(settings, bus)
    mgr.start()
    rows = mgr.describe()
    assert rows
    assert any(r["transport"] == "demo" for r in rows)
    mgr.stop()
