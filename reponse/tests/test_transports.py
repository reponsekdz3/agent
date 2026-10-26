from __future__ import annotations

from nexuscam.capture.bluetooth_link import decode_advertisement
from nexuscam.capture.wifi_scan import local_ipv4s
from nexuscam.vision.mosaic import mosaic
import numpy as np


def test_ble_apv1_payload():
    payload = b"APV1" + bytes([192, 168, 1, 20]) + bytes([0x1F, 0x90])
    decoded = decode_advertisement(payload)
    assert decoded["ip"] == "192.168.1.20"
    assert decoded["port"] == 8080
    assert decoded["stream_url"] == "http://192.168.1.20:8080/video"


def test_ble_json_payload():
    decoded = decode_advertisement(b'{"stream_url":"http://10.0.0.8:4747/video"}')
    assert "4747" in decoded["stream_url"]


def test_mosaic_empty_and_one():
    empty = mosaic({})
    assert empty.shape[2] == 3
    frame = np.zeros((80, 120, 3), dtype=np.uint8)
    grid = mosaic({"cam": frame}, cell=(64, 48))
    assert grid.shape == (48, 64, 3)


def test_local_ipv4s_type():
    ips = local_ipv4s()
    assert isinstance(ips, list)
