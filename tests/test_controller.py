import threading

from app import controller as ctl


class FakeEngine:
    present = False

    def __init__(self, *a, **k):
        pass

    def has_model(self, n):
        return FakeEngine.present

    def ensure_model(self, name, progress_cb=None, status_cb=None):
        if progress_cb:
            progress_cb(50.0)
            progress_cb(100.0)
        FakeEngine.present = True
        return "x"


def test_download_model_reports_progress_and_done(monkeypatch):
    FakeEngine.present = False
    monkeypatch.setattr(ctl, "Transcriber", FakeEngine)
    monkeypatch.setattr(ctl.binaries, "get_whisper_cli", lambda: "w")
    monkeypatch.setattr(ctl.binaries, "ensure_ffmpeg", lambda *a, **k: "f")
    c = ctl.RecordingController(model_name="small", on_log=lambda m: None)
    seen, done, result = [], threading.Event(), {}
    c.download_model("large-v3-turbo", seen.append, lambda ok, msg: (result.update(ok=ok), done.set()))
    assert done.wait(5) and result["ok"] and seen[-1] == 100.0


def test_download_unknown_model_fails_fast():
    c = ctl.RecordingController(model_name="small", on_log=lambda m: None)
    done, out = threading.Event(), {}
    c.download_model("nope", None, lambda ok, msg: (out.update(ok=ok), done.set()))
    assert done.wait(2) and out["ok"] is False


def test_state_property_starts_loading():
    c = ctl.RecordingController(model_name="small", on_log=lambda m: None)
    assert c.state == ctl.LOADING


def test_prewarm_failure_leaves_idle_and_logs(monkeypatch):
    logs = []
    monkeypatch.setattr(ctl.binaries, "get_whisper_cli", lambda: "w")
    monkeypatch.setattr(ctl.binaries, "ensure_ffmpeg", lambda *a, **k: "f")

    class Boom(FakeEngine):
        def has_model(self, n):
            raise RuntimeError("offline")
    monkeypatch.setattr(ctl, "Transcriber", Boom)
    c = ctl.RecordingController(model_name="small", on_log=logs.append)
    c._prewarm_model()
    assert c.state == ctl.IDLE and any("offline" in m for m in logs)


def test_concurrent_downloads_of_same_model_run_once(monkeypatch):
    calls = []

    class Slow(FakeEngine):
        present = False

        def has_model(self, n):
            return Slow.present

        def ensure_model(self, name, progress_cb=None, status_cb=None):
            import time
            calls.append(name)
            time.sleep(0.2)
            Slow.present = True
            return "x"
    monkeypatch.setattr(ctl, "Transcriber", Slow)
    monkeypatch.setattr(ctl.binaries, "get_whisper_cli", lambda: "w")
    monkeypatch.setattr(ctl.binaries, "ensure_ffmpeg", lambda *a, **k: "f")
    c = ctl.RecordingController(model_name="small", on_log=lambda m: None)
    d1, d2 = threading.Event(), threading.Event()
    c.download_model("small", None, lambda ok, m: d1.set())
    c.download_model("small", None, lambda ok, m: d2.set())
    assert d1.wait(5) and d2.wait(5)
    assert calls == ["small"]


def test_new_install_defaults_to_light_model(monkeypatch):
    monkeypatch.setattr(ctl.config_store, "get_model", lambda: None)
    assert ctl.FALLBACK_MODEL == "small"
    assert ctl.RecordingController(on_log=lambda m: None).model_name == "small"
    # A front-end that can ask (console) still gets to ask.
    assert ctl.RecordingController(on_log=lambda m: None, choose_model=lambda m: "base").model_name is None


class FakeSession:
    def __init__(self, **kw):
        self.calls = []
        self.warnings = []

    def start_recording(self):
        self.calls.append("start")

    def pause(self):
        self.calls.append("pause")

    def resume(self):
        self.calls.append("resume")

    def stop_and_transcribe(self):
        self.calls.append("stop")
        return "transcript.txt"


def _recording_controller(monkeypatch, states):
    monkeypatch.setattr(ctl, "RecordingSession", FakeSession)
    c = ctl.RecordingController(model_name="small", on_log=lambda m: None, on_state=states.append)
    c._state = ctl.IDLE
    c.toggle()
    return c


def test_pause_and_resume_do_not_transcribe(monkeypatch):
    states = []
    c = _recording_controller(monkeypatch, states)
    session = c._session
    c.pause()
    assert c.state == ctl.PAUSED
    c.pause()
    assert c.state == ctl.RECORDING
    assert session.calls == ["start", "pause", "resume"]
    assert states == [ctl.RECORDING, ctl.PAUSED, ctl.RECORDING]


def test_stop_while_paused_transcribes(monkeypatch):
    states, idle = [], threading.Event()
    c = _recording_controller(monkeypatch, states)
    c.on_state = lambda s: (states.append(s), idle.set() if s == ctl.IDLE else None)
    session = c._session
    c.pause()
    c.toggle()
    assert idle.wait(5)
    assert session.calls == ["start", "pause", "stop"]
    assert states[-2:] == [ctl.TRANSCRIBING, ctl.IDLE]


def test_pause_is_ignored_when_not_recording():
    states = []
    c = ctl.RecordingController(model_name="small", on_log=lambda m: None, on_state=states.append)
    c._state = ctl.IDLE
    c.pause()
    assert c.state == ctl.IDLE and states == []


def test_start_logs_what_could_not_be_recorded(monkeypatch):
    class NoMic(FakeSession):
        def start_recording(self):
            self.warnings = ["Sin micrófono (x): se graba solo el audio del sistema."]
    monkeypatch.setattr(ctl, "RecordingSession", NoMic)
    logs = []
    c = ctl.RecordingController(model_name="small", on_log=logs.append)
    c._state = ctl.IDLE
    c.toggle()
    assert c.state == ctl.RECORDING and "Sin micrófono" in logs[-1]


def test_start_registers_both_hotkeys_and_survives_a_bad_pause_combo(monkeypatch):
    hooked, logs = [], []

    def add_hotkey(combo, fn):
        if combo == "not a key":
            raise ValueError("bad combo")
        hooked.append((combo, fn.__name__))
    monkeypatch.setattr(ctl.keyboard, "add_hotkey", add_hotkey)
    monkeypatch.setattr(ctl.RecordingController, "_prewarm_model", lambda self: None)

    c = ctl.RecordingController(hotkey="ctrl+shift+r", model_name="small", on_log=logs.append)
    c.pause_hotkey = "ctrl+shift+space"
    c.start()
    assert hooked == [("ctrl+shift+r", "toggle"), ("ctrl+shift+space", "pause")]

    hooked.clear()
    c.pause_hotkey = "not a key"
    c.start()
    assert hooked == [("ctrl+shift+r", "toggle")] and "ignored" in logs[-1]


def test_first_run_fetches_engine_ffmpeg_and_model_with_visible_progress(monkeypatch):
    import sys
    import types
    FakeEngine.present = False
    steps, logs, cli = [], [], [None]

    def ensure_whisper(progress_cb=None):
        steps.append("engine")
        progress_cb("Downloading whisper.cpp... 50%")
        cli[0] = "w"
    monkeypatch.setitem(sys.modules, "tools.setup_binaries", types.SimpleNamespace(ensure_whisper=ensure_whisper))
    monkeypatch.setattr(ctl, "Transcriber", FakeEngine)
    monkeypatch.setattr(ctl.binaries, "get_whisper_cli", lambda: cli[0])
    monkeypatch.setattr(ctl.binaries, "ensure_ffmpeg", lambda cb=None: steps.append("ffmpeg") or "f")

    c = ctl.RecordingController(model_name="small", on_log=logs.append)
    c._prewarm_model()

    assert steps[:2] == ["engine", "ffmpeg"] and FakeEngine.present
    assert c.state == ctl.IDLE and logs[-1].startswith("Ready.")
    assert "Primer arranque · Downloading whisper.cpp... 50%" in logs
    assert "Primer arranque · Descargando modelo small (488 MB)... 100%" in logs


def test_later_runs_download_nothing(monkeypatch):
    FakeEngine.present = True
    logs = []
    monkeypatch.setattr(ctl, "Transcriber", FakeEngine)
    monkeypatch.setattr(ctl.binaries, "get_whisper_cli", lambda: "w")
    monkeypatch.setattr(ctl.binaries, "ensure_ffmpeg", lambda cb=None: "f")
    c = ctl.RecordingController(model_name="small", on_log=logs.append)
    c._prewarm_model()
    assert len(logs) == 1 and logs[0].startswith("Ready.")
