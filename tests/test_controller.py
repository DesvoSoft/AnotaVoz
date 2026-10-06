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
