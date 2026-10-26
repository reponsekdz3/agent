from __future__ import annotations

from nexuscam.capture.synthetic import SyntheticWorldCapture
from nexuscam.settings import AppSettings, CaptureCfg
from nexuscam.types import FramePacket
from nexuscam.vision.detect import SceneDetector
from nexuscam.vision.engine import VisionEngine
from nexuscam.vision.kinematics import apply_homography, solve_ground_homography
from nexuscam.vision.overlay import GREEN, draw_analytics


def test_homography_roundtrip():
    img = [(100.0, 400.0), (500.0, 400.0), (560.0, 600.0), (40.0, 600.0)]
    world = [(0.0, 0.0), (10.0, 0.0), (10.0, 6.0), (0.0, 6.0)]
    h = solve_ground_homography(img, world)
    x, y = apply_homography(100.0, 400.0, h)
    assert abs(x) < 0.15
    assert abs(y) < 0.15


def test_taxonomy_covers_people_vehicles_animals():
    from nexuscam.vision.taxonomy import kind_of

    assert kind_of("person") == "person"
    assert kind_of("car") == "vehicle"
    assert kind_of("motorcycle") == "vehicle"
    assert kind_of("dog") == "animal"
    assert kind_of("horse") == "animal"
    assert kind_of("bottle") == "object"


def test_green_rectangle_drawn_on_each_object():
    cap = SyntheticWorldCapture(CaptureCfg(width=960, height=540, fps=30))
    cap.start()
    settings = AppSettings()
    settings.capture = CaptureCfg(width=960, height=540)
    settings.vision.min_track_hits = 1
    engine = VisionEngine(settings)
    engine.detector = SceneDetector(try_dnn=False)
    last = None
    pkt = None
    for i in range(36):
        pkt = cap.read(i)
        last = engine.analyze(pkt, 1.0)
    vis = draw_analytics(pkt.bgr, last)
    assert last.objects
    for obj in last.objects:
        x, y, w, h = obj.box.as_int()
        cx = min(vis.shape[1] - 1, max(0, x + 1))
        cy = min(vis.shape[0] - 1, max(0, y + 1))
        # box stroke is green-dominant
        pixel = vis[cy, cx]
        assert int(pixel[1]) >= int(pixel[0])
        assert obj.lines()
    kinds = {o.kind for o in last.objects}
    assert kinds, "expected at least one kind"
    assert vis[:, :, 1].mean() >= pkt.bgr[:, :, 1].mean()


def test_frame_packet_transport():
    cap = SyntheticWorldCapture(CaptureCfg())
    cap.start()
    pkt = cap.read(0)
    assert isinstance(pkt, FramePacket)
    assert pkt.bgr.shape[2] == 3
