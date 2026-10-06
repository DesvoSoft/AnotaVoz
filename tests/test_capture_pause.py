from app.capture import CaptureSession, StreamRecorder

DEVICE = {"index": 0, "maxInputChannels": 1, "defaultSampleRate": 16000}


def test_paused_recorder_drops_frames_and_reports_silence(tmp_path):
    levels = []
    rec = StreamRecorder(None, DEVICE, str(tmp_path / "a.wav"), on_level=levels.append)
    rec._callback(b"\x10\x10" * 8, 8, None, None)
    rec.paused = True
    rec._callback(b"\x10\x10" * 8, 8, None, None)
    assert rec._queue.qsize() == 1
    assert levels[0] > 0 and levels[1] == 0.0


def test_session_pauses_both_tracks_together(tmp_path):
    s = CaptureSession("m.wav", "s.wav")
    s._mic_rec = StreamRecorder(None, DEVICE, "m.wav")
    s._sys_rec = StreamRecorder(None, DEVICE, "s.wav")
    s.set_paused(True)
    assert s._mic_rec.paused and s._sys_rec.paused
    s.set_paused(False)
    assert not s._mic_rec.paused and not s._sys_rec.paused
