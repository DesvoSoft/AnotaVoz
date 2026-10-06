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
import os
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
        self.paused = False

    def _callback(self, in_data, frame_count, time_info, status):
        # Paused frames are dropped, not buffered: the stream stays open so
        # resuming is instant and both tracks skip the same stretch of time.
        if self.paused:
            if self._on_level:
                self._on_level(0.0)
            return (None, pyaudio.paContinue)
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
    """Owns the mic + system-loopback recorders for one recording.

    Either track may be unavailable (no microphone plugged in, mic access
    blocked by policy, no output device): the other one is still recorded and
    the reason lands in `skipped`. Only having neither is an error."""

    def __init__(self, mic_path, system_path, level_cb=None):
        self._level_cb = level_cb
        self.mic_path = mic_path
        self.system_path = system_path
        self.skipped = {}  # "microphone" / "system" -> why it is not being recorded
        self._pa = None
        self._mic_rec = None
        self._sys_rec = None
        self._keep_alive = None

    def _open_recorder(self, kind, find_device, path):
        """The opened recorder for one track, or None with the reason noted."""
        cb = self._level_cb
        rec = None
        try:
            rec = StreamRecorder(self._pa, find_device(self._pa), path,
                                 on_level=(lambda v: cb(kind, v)) if cb else None)
            rec.open()
            return rec
        except Exception as e:
            self.skipped[kind] = str(e)
            if rec is not None:
                rec.stop()  # closes the WAV that open() created before failing
                try:
                    os.unlink(path)
                except OSError:
                    pass
            return None

    def start(self):
        self._pa = pyaudio.PyAudio()
        self.skipped = {}

        # open() allocates the PortAudio stream but doesn't start callbacks;
        # doing both opens before either start() keeps the gap between the
        # two streams' first callback to a couple of Python statements.
        self._mic_rec = self._open_recorder("microphone", default_mic, self.mic_path)
        self._sys_rec = self._open_recorder("system", default_loopback, self.system_path)
        if self._mic_rec is None and self._sys_rec is None:
            self._pa.terminate()
            self._pa = None
            raise CaptureError("No microphone and no system audio to record — "
                               + "; ".join(f"{k}: {v}" for k, v in self.skipped.items()))

        try:
            # The keep-alive starts first so the render endpoint is already
            # awake before loopback capture begins.
            if self._sys_rec is not None:
                self._keep_alive = _KeepAliveOutput(self._pa, default_output(self._pa))
                self._keep_alive.start()
            for rec in (self._mic_rec, self._sys_rec):
                if rec is not None:
                    rec.start()
        except Exception:
            self.stop()
            raise

    def set_paused(self, paused):
        """Both tracks flip together so they stay aligned across the gap."""
        for rec in (self._mic_rec, self._sys_rec):
            if rec is not None:
                rec.paused = paused

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
        # None for a track that was never recorded: there is no file to read.
        return (self.mic_path if self._mic_rec is not None else None,
                self.system_path if self._sys_rec is not None else None)
