import os
import wave

import pytest

from app import binaries
from app.audio_prep import build_command, prepare


def test_mic_command_has_highpass_and_loudnorm_without_denoise():
    cmd = build_command("ffmpeg.exe", "in.wav", "out.wav", "microphone")
    af = cmd[cmd.index("-af") + 1]
    assert "highpass" in af and "loudnorm" in af and "afftdn" not in af
    assert cmd[-1] == "out.wav" and "-ar" in cmd and "16000" in cmd


def test_system_command_skips_denoise():
    af = build_command("f", "a", "b", "system")
    af = af[af.index("-af") + 1]
    assert "loudnorm" in af and "afftdn" not in af


def test_unknown_kind_rejected():
    with pytest.raises(ValueError):
        build_command("f", "a", "b", "otra")


def _tiny_wav(path, seconds=0.0):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * seconds))


def test_prepare_falls_back_to_source_on_ffmpeg_failure(tmp_path):
    src = str(tmp_path / "in.wav")
    _tiny_wav(src, 0.0)
    out = str(tmp_path / "out.wav")
    result = prepare(binaries.ensure_ffmpeg(), src, out, "microphone")
    assert result in (src, out) and os.path.exists(result)


def test_prepare_missing_ffmpeg_returns_source(tmp_path):
    src = str(tmp_path / "in.wav")
    _tiny_wav(src, 0.5)
    assert prepare(str(tmp_path / "no-ffmpeg.exe"), src, str(tmp_path / "o.wav"), "system") == src
