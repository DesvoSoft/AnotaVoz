"""Fase 2 smoke test: binaries resolve, tiny model downloads, whisper-cli
actually runs against a real captured WAV. Uses 'tiny' (not the app
default) so the smoke test doesn't wait on a ~1.6GB download.
"""
import subprocess
import sys
import time

sys.path.insert(0, ".")

from app import binaries
from app.capture import CaptureSession
from app.transcriber import Transcriber, TranscribeError

SPEAK_PS = (
    "Add-Type -AssemblyName System.Speech; "
    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
    "$s.Speak('Hola, esto es una prueba de eco note, sistema de transcripcion.')"
)

if __name__ == "__main__":
    whisper_cli = binaries.get_whisper_cli()
    ffmpeg_path = binaries.ensure_ffmpeg()
    print(f"whisper-cli: {whisper_cli}")
    print(f"ffmpeg:      {ffmpeg_path}")
    assert whisper_cli, "whisper-cli.exe not found"

    print("Recording 5s (playing TTS through speakers to exercise the system track)...")
    session = CaptureSession("tools/_smoke_mic.wav", "tools/_smoke_sys.wav")
    session.start()
    subprocess.Popen(["powershell", "-Command", SPEAK_PS])
    time.sleep(5)
    mic_path, sys_path = session.stop()

    engine = Transcriber(whisper_cli, ffmpeg_path, "tools/_smoke_models")
    print("Ensuring 'tiny' model (downloads ~75MB once)...")
    model_path = engine.ensure_model("tiny", status_cb=print)

    for label, path in (("mic", mic_path), ("system", sys_path)):
        print(f"Transcribing {label}...")
        try:
            paths = engine.transcribe(path, model_path, f"tools/_smoke_{label}")
            with open(paths[0], encoding="utf-8") as f:
                print(f"  {label} text: {f.read().strip()!r}")
        except TranscribeError as e:
            print(f"  {label}: {e}")
