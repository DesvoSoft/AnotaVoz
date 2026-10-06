"""Hotkey-driven state machine for one recording/transcribe cycle at a
time. Shared by main.py (console) and app/tray.py (tray icon) so the
loading/idle/recording/transcribing gate (ADR-005) lives in exactly one
place instead of being reimplemented per front-end.
"""
import threading

import keyboard

from app import binaries
from app import config as config_store
from app.session import MODEL_DIR, RecordingSession
from app.transcriber import MODELS, Transcriber

LOADING, IDLE, RECORDING, TRANSCRIBING = "loading", "idle", "recording", "transcribing"

# Light by default (ADR-014): a new install has to work on a laptop with no
# GPU and without a 1.6GB first-run download. 'small' is the lightest model
# that is still usable on real meeting audio; 'large-v3-turbo' is one click
# away in the UI for machines that can carry it (see ADR-011/012 for why it
# is the accuracy pick).
FALLBACK_MODEL = "small"


class RecordingController:
    def __init__(self, hotkey=None, model_name=None,
                 on_state=None, on_log=None, choose_model=None,
                 on_level=None, on_progress=None):
        self.hotkey = hotkey or config_store.get_settings()["hotkey"]
        self.on_level = on_level or (lambda kind, value: None)
        self.on_progress = on_progress or (lambda pct: None)
        self.on_state = on_state or (lambda state: None)
        self.on_log = on_log or print
        self._choose_model = choose_model  # optional: (MODELS) -> name, asked once on first run
        # With no way to ask (tray, GUI) the default applies from the first
        # moment, so the UI never shows "no model" while the prewarm runs.
        self.model_name = (model_name or config_store.get_model()
                           or (None if choose_model else FALLBACK_MODEL))
        self._state = LOADING
        self._session = None
        self._lock = threading.Lock()
        self._model_locks = {}
        self._locks_guard = threading.Lock()

    @property
    def state(self):
        return self._state

    def has_model(self, name):
        whisper_cli = binaries.get_whisper_cli()
        return bool(whisper_cli) and Transcriber(whisper_cli, None, MODEL_DIR).has_model(name)

    def _model_lock(self, name):
        with self._locks_guard:
            return self._model_locks.setdefault(name, threading.Lock())

    def _ensure_model(self, name, progress_cb=None):
        """Make sure a model is on disk. One download per model at a time: a
        second caller waits on the lock and then finds the file present."""
        whisper_cli = binaries.get_whisper_cli()
        if not whisper_cli:
            raise RuntimeError("whisper-cli.exe not found")
        engine = Transcriber(whisper_cli, binaries.ensure_ffmpeg(), MODEL_DIR)
        with self._model_lock(name):
            if not engine.has_model(name):
                engine.ensure_model(name, progress_cb=progress_cb, status_cb=self.on_log)

    def download_model(self, name, on_progress=None, on_done=None):
        """Download a model on a background thread; never blocks the caller.
        on_done(ok, message) fires exactly once."""
        def run():
            ok, msg = False, ""
            try:
                if name not in MODELS:
                    raise ValueError(f"Unknown model '{name}'")
                self._ensure_model(name, on_progress)
                ok, msg = True, "ok"
            except Exception as e:
                msg = str(e)
            if on_done:
                on_done(ok, msg)
        threading.Thread(target=run, daemon=True).start()

    def set_model(self, name):
        """Switch the active model. Takes effect on the next recording —
        one already in flight keeps the model it was started with."""
        if name not in MODELS:
            self.on_log(f"Unknown model '{name}'.")
            return
        self.model_name = name
        config_store.set_model(name)
        self.on_log(f"Model set to '{name}'.")

    def _set_state(self, state):
        self._state = state
        self.on_state(state)

    def _prewarm_model(self):
        """Resolves which model to use (asking once if nothing is
        configured yet) and downloads it before the hotkey is usable: a
        hotkey fired mid-download would otherwise race the same download
        started again inside RecordingSession.stop_and_transcribe(). Always
        ends in IDLE so a failure here never leaves the app stuck loading."""
        try:
            if not self.model_name:
                self.model_name = self._choose_model(MODELS) if self._choose_model else FALLBACK_MODEL
                config_store.set_model(self.model_name)

            if not binaries.get_whisper_cli():
                self.on_log("whisper-cli.exe not found under core/whisper/ — "
                            "transcription will fail until it's restored.")
                return
            self._ensure_model(self.model_name)
            self.on_log(f"Ready. Press {self.hotkey} to start/stop recording.")
        except Exception as e:
            self.on_log(f"Could not prepare model '{self.model_name}': {e}")
        finally:
            with self._lock:
                self._set_state(IDLE)

    def _stop_and_transcribe(self):
        session = self._session
        try:
            out_path = session.stop_and_transcribe()
            self.on_log(f"Transcript ready: {out_path}")
        except Exception as e:
            self.on_log(f"Error: {e}")
        finally:
            with self._lock:
                self._session = None
                self._set_state(IDLE)

    def toggle(self):
        with self._lock:
            state = self._state
            if state == LOADING:
                self.on_log("Still loading the model, hang on...")
                return
            if state == TRANSCRIBING:
                self.on_log("Still transcribing, please wait...")
                return
            if state == IDLE:
                self._session = RecordingSession(
                    model_name=self.model_name, status_cb=self.on_log,
                    vocabulary=config_store.get_settings()["vocabulary"],
                    level_cb=self.on_level, progress_cb=self.on_progress)
                try:
                    self._session.start_recording()
                except Exception as e:
                    self.on_log(f"Could not start recording: {e}")
                    self._session = None
                    return
                self._set_state(RECORDING)
                self.on_log("Recording... press the hotkey again to stop.")
                return
            # state == RECORDING
            self._set_state(TRANSCRIBING)
        threading.Thread(target=self._stop_and_transcribe, daemon=True).start()

    def start(self):
        """Registers the global hotkey and kicks off model prewarm. Non-blocking."""
        keyboard.add_hotkey(self.hotkey, self.toggle)
        threading.Thread(target=self._prewarm_model, daemon=True).start()

    def shutdown(self):
        try:
            keyboard.unhook_all_hotkeys()
        except AttributeError:
            pass  # nothing was ever hooked (start() not called) — nothing to undo
