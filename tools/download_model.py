"""Download (or resume) a whisper model: python tools/download_model.py [name]."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import binaries
from app.session import MODEL_DIR
from app.transcriber import DEFAULT_MODEL, Transcriber

name = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL
last = [-1]


def progress(p):
    if int(p) // 5 != last[0]:
        last[0] = int(p) // 5
        print(f"{p:.0f}%", flush=True)


engine = Transcriber(binaries.get_whisper_cli(), binaries.ensure_ffmpeg(), MODEL_DIR)
print(engine.ensure_model(name, progress_cb=progress, status_cb=print))
