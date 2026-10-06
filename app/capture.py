"""Simultaneous mic + system-audio capture, kept as two separate WAV files.

Uses PyAudio's callback mode, not the prototype's polling loop
(`stream.record(numframes=...)` in a `while` loop) — a blocking read on one
device before starting the read on the other is what desynced mic vs.
system in the original script. Callback streams both run on PortAudio's own
threads from the moment `start()` returns, so the two capture the same wall
clock instant independent of how long Python takes between statements.

Audio frames are handed off through a queue to a dedicated writer thread
instead of touching the wave file from inside the callback: PortAudio
callbacks are expected to return quickly, and file I/O has no such
guarantee.
"""
import queue
import threading
import time
import wave

import pyaudiowpatch as pyaudio

from app.levels import rms_level
from app.devices import default_loopback, default_mic, default_output

SAMPLE_FORMAT = pyaudio.paInt16
SAMPLE_WIDTH = 2  # bytes, matches paInt16
FRAMES_PER_BUFFER = 1024


class CaptureError(Exception):
    pass


class _KeepAliveOutput:
    """Plays silence to the default output for as long as recording runs.

    WASAPI loopback only delivers callbacks while the render endpoint is
    actively rendering; Windows suspends it after a few seconds of nothing
    to play, which starves the loopback stream of frames even though the
    speaker is the "active" device (confirmed empirically: a loopback
    recording taken during silence comes back with 0 frames, the same
    recording during a tone comes back full-length). Holding a silent
    stream open on the output keeps the endpoint running so loopback
    capture doesn't go dark whenever the room does.
    """

    def __init__(self, pa, device_info):
        self._pa = pa
        self.channels = max(1, int(device_info["maxOutputChannels"]))
        self.rate = int(device_info["defaultSampleRate"])
        self._silence = b"\x00" * (FRAMES_PER_BUFFER * self.channels * SAMPLE_WIDTH)
        self._stream = self._pa.open(
            format=SAMPLE_FORMAT,
            channels=self.channels,
            rate=self.rate,
            output=True,
            output_device_index=device_info["index"],
            frames_per_buffer=FRAMES_PER_BUFFER,
            stream_callback=self._callback,
            start=False,
        )

    def _callback(self, in_data, frame_count, time_info, status):
        return (self._silence, pyaudio.paContinue)

    def start(self):
        self._stream.start_stream()

    def stop(self):
        self._stream.stop_stream()
        self._stream.close()


class StreamRecorder:
    """Records one device to one WAV file, from open() to stop()."""

    def __init__(self, pa, device_info, out_path, on_level=None):
        self._on_level = on_level
        self._pa = pa
        self._device = device_info
        self.out_path = out_path
        self.channels = max(1, int(device_info["maxInputChannels"]))
        self.rate = int(device_info["defaultSampleRate"])
        self._queue = queue.Queue()
        self._stream = None
        self._wav = None
        self._writer_thread = None
        self._stop_writer = threading.Event()
        self.started_at = None

    def _callback(self, in_data, frame_count, time_info, status):
        self._queue.put(in_data)
        if self._on_level:
            self._on_level(rms_level(in_data))
        return (None, pyaudio.paContinue)

    def _drain_queue(self, block):
        """Write whatever is queued right now. `block` waits briefly for the
        first item so the writer doesn't spin at 100% CPU while idle."""
        try:
            item = self._queue.get(timeout=0.1 if block else 0)
        except queue.Empty:
            return
        self._wav.writeframes(item)
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                return
            self._wav.writeframes(item)

    def _writer_loop(self):
        while not self._stop_writer.is_set():
            self._drain_queue(block=True)
        self._drain_queue(block=False)  # final flush after stop() signals

    def open(self):
        self._wav = wave.open(self.out_path, "wb")
        self._wav.setnchannels(self.channels)
        self._wav.setsampwidth(SAMPLE_WIDTH)
        self._wav.setframerate(self.rate)
        self._stream = self._pa.open(
            format=SAMPLE_FORMAT,
            channels=self.channels,
            rate=self.rate,
            input=True,
            input_device_index=self._device["index"],
            frames_per_buffer=FRAMES_PER_BUFFER,
            stream_callback=self._callback,
            start=False,
        )

    def start(self):
        self._writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self._writer_thread.start()
        self._stream.start_stream()
        self.started_at = time.monotonic()

    def stop(self):
        if self._stream is not None:
            self._stream.stop_stream()
            self._stream.close()
        self._stop_writer.set()
        if self._writer_thread is not None:
            self._writer_thread.join(timeout=5)
        if self._wav is not None:
            self._wav.close()


class CaptureSession:
    """Owns the mic + system-loopback recorders for one recording."""

    def __init__(self, mic_path, system_path, level_cb=None):
        self._level_cb = level_cb
        self.mic_path = mic_path
        self.system_path = system_path
        self._pa = None
        self._mic_rec = None
        self._sys_rec = None
        self._keep_alive = None

    def start(self):
        self._pa = pyaudio.PyAudio()
        try:
            mic_device = default_mic(self._pa)
            loopback_device = default_loopback(self._pa)
            output_device = default_output(self._pa)
        except Exception:
            self._pa.terminate()
            self._pa = None
            raise

        self._keep_alive = _KeepAliveOutput(self._pa, output_device)
        cb = self._level_cb
        self._mic_rec = StreamRecorder(self._pa, mic_device, self.mic_path,
                                       on_level=(lambda v: cb("microphone", v)) if cb else None)
        self._sys_rec = StreamRecorder(self._pa, loopback_device, self.system_path,
                                       on_level=(lambda v: cb("system", v)) if cb else None)

        # open() allocates the PortAudio stream but doesn't start callbacks;
        # doing both opens before either start() keeps the gap between the
        # two streams' first callback to a couple of Python statements. The
        # keep-alive starts first so the render endpoint is already awake
        # before loopback capture begins.
        try:
            self._mic_rec.open()
            self._sys_rec.open()
            self._keep_alive.start()
            self._mic_rec.start()
            self._sys_rec.start()
        except Exception:
            self.stop()
            raise

    def stop(self):
        for part in (self._mic_rec, self._sys_rec, self._keep_alive):
            if part is not None:
                try:
                    part.stop()
                except Exception:
                    pass  # a half-opened stream must not block closing the rest
        if self._pa is not None:
            self._pa.terminate()
            self._pa = None
        return self.mic_path, self.system_path
