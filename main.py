"""Console entry point: global hotkey -> record mic+system -> hotkey ->
transcribe -> transcript.txt. For the tray version see app/tray.py.
"""
import sys

import keyboard

from app import config, single_instance
from app.controller import FALLBACK_MODEL, RecordingController


def choose_model_console(models):
    """Asked once, only when no model is configured yet (see app/config.py)."""
    print("Choose a Whisper model (saved for next time, change later from app/tray.py):")
    names = list(models)
    for i, name in enumerate(names, 1):
        size_mb = models[name][2]
        print(f"  {i}. {name} (~{size_mb}MB)")
    default = FALLBACK_MODEL
    choice = input(f"Model number or name [{default}]: ").strip()
    if not choice:
        return default
    if choice.isdigit() and 1 <= int(choice) <= len(names):
        return names[int(choice) - 1]
    if choice in models:
        return choice
    print(f"Didn't recognize '{choice}', using '{default}'.")
    return default


def main():
    config.migrate_legacy_dir()
    if not single_instance.acquire():
        print("AnotaVoz is already running (check your system tray / other console).")
        sys.exit(1)

    print("AnotaVoz starting...", flush=True)
    controller = RecordingController(on_log=print, choose_model=choose_model_console)
    controller.start()
    try:
        keyboard.wait()
    except KeyboardInterrupt:
        pass
    finally:
        controller.shutdown()
        print("Bye.", flush=True)


if __name__ == "__main__":
    main()
