import os

import pytest

from app import capture
from app.devices import DeviceError

DEVICE = {"index": 0, "maxInputChannels": 1, "maxOutputChannels": 2, "defaultSampleRate": 16000}


class FakeStream:
    def start_stream(self):
        pass

    def stop_stream(self):
        pass

    def close(self):
        pass


class FakePA:
    fail_input = False

    def open(self, **kw):
        if kw.get("input") and FakePA.fail_input:
            raise OSError("access denied")
        return FakeStream()

    def terminate(self):
        pass


def _missing(msg):
    def find(p):
        raise DeviceError(msg)
    return find


@pytest.fixture
def session(tmp_path, monkeypatch):
    FakePA.fail_input = False
    monkeypatch.setattr(capture.pyaudio, "PyAudio", FakePA)
    for name in ("default_mic", "default_loopback", "default_output"):
        monkeypatch.setattr(capture, name, lambda p: DEVICE)
    return capture.CaptureSession(str(tmp_path / "microphone.wav"), str(tmp_path / "system.wav"))


def test_both_tracks_when_everything_is_there(session):
    session.start()
    mic, system = session.stop()
    assert session.skipped == {}
    assert os.path.isfile(mic) and os.path.isfile(system)


def test_no_microphone_still_records_system(session, monkeypatch):
    monkeypatch.setattr(capture, "default_mic", _missing("no mic"))
    session.start()
    mic, system = session.stop()
    assert mic is None and os.path.isfile(system)
    assert session.skipped == {"microphone": "no mic"}
    assert not os.path.exists(session.mic_path)


def test_no_output_device_still_records_microphone(session, monkeypatch):
    monkeypatch.setattr(capture, "default_loopback", _missing("no output"))
    session.start()
    mic, system = session.stop()
    assert system is None and os.path.isfile(mic)
    assert session._keep_alive is None


def test_blocked_microphone_leaves_no_empty_wav(session, monkeypatch):
    FakePA.fail_input = True
    monkeypatch.setattr(capture, "default_loopback", _missing("no output"))
    with pytest.raises(capture.CaptureError):
        session.start()
    assert not os.path.exists(session.mic_path)


def test_nothing_to_record_is_an_error(session, monkeypatch):
    monkeypatch.setattr(capture, "default_mic", _missing("no mic"))
    monkeypatch.setattr(capture, "default_loopback", _missing("no output"))
    with pytest.raises(capture.CaptureError, match="no mic"):
        session.start()
