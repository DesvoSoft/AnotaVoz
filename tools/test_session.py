"""Fase 2 end-to-end: RecordingSession start -> stop_and_transcribe ->
merged transcript.txt, using 'tiny' to keep the smoke test fast. Reuses the
model cached by test_transcribe.py under tools/_smoke_models."""
import subprocess
import sys
import time

sys.path.insert(0, ".")

import app.session as session_mod
from app.session import RecordingSession

session_mod.MODEL_DIR = "tools/_smoke_models"
session_mod.RECORDINGS_DIR = "tools/_smoke_recordings"

SPEAK_PS = (
    "Add-Type -AssemblyName System.Speech; "
    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
    "$s.Speak('Hola, esto es una prueba de eco note, sistema de transcripcion.')"
)

if __name__ == "__main__":
    s = RecordingSession(model_name="tiny", status_cb=print)
    s.start_recording()
    subprocess.Popen(["powershell", "-Command", SPEAK_PS])
    time.sleep(5)
    out_path = s.stop_and_transcribe()

    print("\n--- transcript.txt ---")
    with open(out_path, encoding="utf-8") as f:
        print(f.read())
