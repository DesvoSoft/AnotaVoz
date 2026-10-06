import struct

from app.levels import rms_level


def pcm(vals):
    return struct.pack(f"<{len(vals)}h", *vals)


def test_silence_is_zero():
    assert rms_level(pcm([0] * 100)) == 0.0


def test_full_scale_is_one():
    assert abs(rms_level(pcm([32767, -32768] * 50)) - 1.0) < 0.01


def test_empty_and_odd_length_safe():
    assert rms_level(b"") == 0.0
    assert rms_level(b"\x01") == 0.0
