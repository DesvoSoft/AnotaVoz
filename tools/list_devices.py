"""Sanity check: can we see the default mic + loopback device via WASAPI?"""
import sys

sys.path.insert(0, ".")

import pyaudiowpatch as pyaudio

from app.devices import default_loopback, default_mic

with pyaudio.PyAudio() as p:
    mic = default_mic(p)
    loop = default_loopback(p)
    print(f"Mic:      [{mic['index']}] {mic['name']} "
          f"({mic['maxInputChannels']}ch @ {int(mic['defaultSampleRate'])}Hz)")
    print(f"Loopback: [{loop['index']}] {loop['name']} "
          f"({loop['maxInputChannels']}ch @ {int(loop['defaultSampleRate'])}Hz)")
