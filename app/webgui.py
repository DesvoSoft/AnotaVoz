"""pywebview front-end. The window is created first; the controller starts
after the page is loaded so early events are not lost. If the web view cannot
start (no WebView2 runtime), falls back to the tray front-end."""
import ctypes
import json
import os
import sys
import threading

from app import config, single_instance
from app.api import Api, AsyncEmitter
from app.controller import RecordingController

UI_INDEX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui", "index.html")


def _headless():
    """True under pythonw (run_gui.bat): no console, so prints and tracebacks
    go to a log file beside the config instead of nowhere."""
    if sys.stdout is not None and sys.stderr is not None:
        return False
    log_path = os.path.join(config.DATA_DIR, "anotavoz.log")
    os.makedirs(config.DATA_DIR, exist_ok=True)
    sys.stdout = sys.stderr = open(log_path, "w", encoding="utf-8", buffering=1)
    return True


def main():
    config.migrate_legacy_dir()
    headless = _headless()
    if not single_instance.acquire():
        print("AnotaVoz is already running.")
        if headless:  # nothing else would tell the user why no window appeared
            ctypes.windll.user32.MessageBoxW(None, "AnotaVoz ya está abierto.", "AnotaVoz", 0x40)
        return
    try:
        import webview
    except ImportError as e:
        print(f"pywebview not installed ({e}); falling back to tray.")
        from app.tray import TrayApp
        TrayApp().run()
        return

    holder = {}

    def raw_emit(name, payload=None):
        w = holder.get("window")
        if w is None:
            return
        try:
            w.evaluate_js(f"window.echo && window.echo.emit({json.dumps(name)}, {json.dumps(payload)})")
        except Exception:
            pass  # window closing

    api = Api(controller_factory=lambda **kw: RecordingController(**kw), emit=AsyncEmitter(raw_emit))
    window = webview.create_window("AnotaVoz", UI_INDEX, js_api=api, width=1120, height=740,
                                   min_size=(760, 540), background_color="#0b0d12")
    holder["window"] = window
    window.events.loaded += lambda: api._start()
    api._on_close_ready = lambda: threading.Thread(target=window.destroy, daemon=True).start()

    def on_closing():
        ok = api._request_close()
        if ok:
            api._shutdown()
        return ok

    window.events.closing += on_closing
    try:
        webview.start()
    except Exception as e:
        print(f"Web view failed ({e}); falling back to tray.")
        api._shutdown()
        from app.tray import TrayApp
        TrayApp().run()


if __name__ == "__main__":
    main()
