"""Fase 1 acceptance check: record N seconds from mic + system loopback in
parallel, confirm both files come out roughly the same duration (sync
sanity, not a hard latency measurement)."""
import sys
import time
import wave

sys.path.insert(0, ".")

from app.capture import CaptureSession

DURATION_S = 4

if __name__ == "__main__":
    session = CaptureSession("tools/_mic_test.wav", "tools/_sys_test.wav")
    print(f"Recording {DURATION_S}s from mic + system loopback...")
    session.start()
    time.sleep(DURATION_S)
    mic_path, sys_path = session.stop()

    for label, path in (("mic", mic_path), ("system", sys_path)):
        with wave.open(path, "rb") as w:
            dur = w.getnframes() / float(w.getframerate())
            print(f"{label}: {path} -> {dur:.3f}s, {w.getnchannels()}ch, "
                  f"{w.getframerate()}Hz, {w.getnframes()} frames")
