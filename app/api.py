"""JS <-> Python bridge. Public methods are what the UI may call; everything
private is underscore-prefixed because pywebview introspects public attributes."""
import os
import queue
import threading
import time

from app import config, history
from app.transcriber import MODEL_LABELS, MODELS, gpu_backend

LEVEL_INTERVAL = 0.05  # seconds, ~20 Hz


class AsyncEmitter:
    """Wraps a possibly-blocking emit (pywebview's evaluate_js waits for the page)
    so callers on audio threads or holding the controller lock never stall."""

    def __init__(self, emit):
        self._emit = emit
        self._q = queue.Queue()
        threading.Thread(target=self._run, daemon=True).start()

    def __call__(self, name, payload=None):
        self._q.put((name, payload))

    def _run(self):
        while True:
            item = self._q.get()
            if isinstance(item, threading.Event):
                item.set()
                continue
            try:
                self._emit(*item)
            except Exception:
                pass

    def flush(self, timeout=2.0):
        done = threading.Event()
        self._q.put(done)
        return done.wait(timeout)


class Api:
    def __init__(self, controller_factory, emit):
        self._emit = emit
        self._lock = threading.Lock()
        self._started = False
        self._close_when_idle = False
        self._on_close_ready = lambda: None
        self._last_level = 0.0
        self._levels = {"microphone": 0.0, "system": 0.0}
        self._controller = controller_factory(
            on_state=self._on_state,
            on_log=self._on_log,
            on_level=self._on_level,
            on_progress=lambda p: self._emit("progress", p),
        )

    # --- controller callbacks (background threads) ---
    def _on_state(self, state):
        self._emit("state", state)
        if state == "idle" and self._close_when_idle:
            self._close_when_idle = False
            self._on_close_ready()

    def _request_close(self):
        """True when the window may close now. While recording, stop and
        transcribe first so the meeting is never lost; while transcribing,
        wait. The window is destroyed through _on_close_ready once idle."""
        state = self._controller.state
        if state in ("idle", "loading"):
            return True
        self._close_when_idle = True
        if state == "recording":
            self._controller.toggle()
        self._emit("log", "Finalizando antes de cerrar...")
        return False

    def _on_log(self, msg):
        self._emit("log", str(msg))
        if str(msg).startswith("Ready:"):
            self._emit("history_changed", None)

    def _on_level(self, kind, value):
        now = time.monotonic()
        with self._lock:
            self._levels[kind] = value
            if now - self._last_level < LEVEL_INTERVAL:
                return
            self._last_level = now
            snapshot = dict(self._levels)
        self._emit("levels", snapshot)

    # --- lifecycle (called by webgui, not by JS) ---
    def _start(self):
        if self._started:
            return
        self._started = True
        self._controller.start()

    def _shutdown(self):
        self._controller.shutdown()

    # --- API for JS ---
    def bootstrap(self):
        gpu = None
        try:
            from app import binaries
            cli = binaries.get_whisper_cli()
            g = gpu_backend(cli) if cli else None
            gpu = (g.get("device") or g["name"]) if g else None
        except Exception:
            gpu = None
        return {
            "state": self._controller.state,
            "model": self._controller.model_name,
            "models": self._models(),
            "gpu": gpu,
            "settings": config.get_settings(),
            "history": history.list_history(),
        }

    def _models(self):
        return [{"name": n, "label": MODEL_LABELS.get(n, {}).get("label", n),
                 "note": MODEL_LABELS.get(n, {}).get("note", ""), "size_mb": spec[2],
                 "installed": self._controller.has_model(n)} for n, spec in MODELS.items()]

    def toggle(self):
        self._controller.toggle()

    def set_model(self, name):
        self._controller.set_model(name)
        return self._models()

    def download_model(self, name):
        def progress(p):
            self._emit("model_download", {"name": name, "pct": p, "done": False, "error": None})

        def done(ok, msg):
            self._emit("model_download", {"name": name, "pct": 100.0 if ok else 0.0, "done": ok,
                                          "error": None if ok else msg})
        self._controller.download_model(name, progress, done)

    def get_settings(self):
        return config.get_settings()

    def set_settings(self, patch):
        return config.set_settings(patch if isinstance(patch, dict) else {})

    def list_devices(self):
        try:
            import pyaudiowpatch as pa
            from app import devices
            p = pa.PyAudio()
            try:
                ins = [{"index": d["index"], "name": d["name"]} for d in devices.list_input_devices(p)]
                outs = [{"index": d["index"], "name": d["name"]} for d in devices.list_loopback_devices(p)]
            finally:
                p.terminate()
            return {"inputs": ins, "loopbacks": outs}
        except Exception as e:
            return {"inputs": [], "loopbacks": [], "error": str(e)}

    def list_history(self):
        return history.list_history()

    def _guard(self, fn, *args):
        try:
            return fn(*args)
        except (ValueError, OSError) as e:
            return {"error": str(e)}

    def load_transcript(self, rid):
        return self._guard(history.load, rid)

    def rename(self, rid, name):
        r = self._guard(history.rename, rid, name)
        self._emit("history_changed", None)
        return r

    def delete(self, rid):
        r = self._guard(history.delete, rid)
        self._emit("history_changed", None)
        return r

    def export(self, rid, fmt):
        return self._guard(history.export, rid, fmt)

    def open_folder(self, rid):
        def go():
            d = history._dir("recordings", rid)
            if os.path.isdir(d):
                os.startfile(os.path.abspath(d))
        return self._guard(go)
