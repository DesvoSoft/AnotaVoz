"""Same as test_capture.py but also plays a tone through the default output
so the render engine isn't idle — checks whether loopback needs something
actively playing to produce callbacks."""
import math
import struct
import sys
import time
import wave

sys.path.insert(0, ".")

import pyaudiowpatch as pyaudio

from app.capture import CaptureSession

DURATION_S = 4
TONE_HZ = 440
RATE = 48000


def play_tone(pa, seconds):
    n = int(RATE * seconds)
    samples = [int(3000 * math.sin(2 * math.pi * TONE_HZ * i / RATE)) for i in range(n)]
    data = struct.pack("<" + "h" * n, *samples)
    stream = pa.open(format=pyaudio.paInt16, channels=1, rate=RATE, output=True)
    stream.write(data)
    stream.stop_stream()
    stream.close()


if __name__ == "__main__":
    pa = pyaudio.PyAudio()
    session = CaptureSession("tools/_mic_test2.wav", "tools/_sys_test2.wav")
    print(f"Recording {DURATION_S}s while playing a {TONE_HZ}Hz tone...")
    session.start()
    play_tone(pa, DURATION_S)
    mic_path, sys_path = session.stop()
    pa.terminate()

    for label, path in (("mic", mic_path), ("system", sys_path)):
        with wave.open(path, "rb") as w:
            dur = w.getnframes() / float(w.getframerate())
            print(f"{label}: {path} -> {dur:.3f}s, {w.getnchannels()}ch, "
                  f"{w.getframerate()}Hz, {w.getnframes()} frames")
