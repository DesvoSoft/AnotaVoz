"""Orchestrates one hotkey-toggle cycle: record mic+system separately,
transcribe each track on its own (never mixed — see docs/DECISIONS.md
ADR-002), then interleave the two transcripts chronologically tagged by
speaker source.
"""
import json
import os
import shutil
import time
from datetime import datetime

from app import binaries
from app.audio_prep import prepare
from app.capture import CaptureSession
from app.postproc import collapse_repeats, collapse_word_loops, drop_echo
from app.transcriber import (
    DEFAULT_MODEL,
    Transcriber,
    TranscribeError,
    _parse_srt,
    gpu_backend,
    wav_peak_amplitude,
)

# Every recording is Spanish for this app's actual use — "auto" adds a
# per-chunk language-detection roll that can only hurt accuracy on audio
# whose language was never in question. See ADR-011.
LANG = "es"

MODEL_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "EchoNote", "models")
RECORDINGS_DIR = "recordings"

# Below this peak (out of 32767), a track is treated as true digital silence
# and never handed to whisper at all (see wav_peak_amplitude's docstring for
# why — -nth tuning alone doesn't stop the hallucination). Real speech, even
# quiet, sits in the thousands; this only catches "nothing was there".
SILENCE_PEAK = 80

# A secondary safety net for tracks that mix real speech with long silence:
# whisper.cpp's own default (0.60) under-suppresses on our tracks, whose
# silence stretches are much longer than the continuous-speech audio Y2oby
# usually feeds it.
NO_SPEECH_THOLD = 0.4


class SessionError(Exception):
    pass


def _session_dir():
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(RECORDINGS_DIR, stamp)
    os.makedirs(path, exist_ok=True)
    return path


def merge_transcripts(mic_cues, sys_cues):
    """Interleave two cue lists chronologically, tagging each line by
    source. `start`/`end` are milliseconds, same unit both lists already use."""
    mic_cues = collapse_repeats(drop_echo(mic_cues, sys_cues))
    sys_cues = collapse_repeats(sys_cues)
    tagged = [(c["start"], c["end"], "YO", collapse_word_loops(c["text"])) for c in mic_cues if c["text"].strip()]
    tagged += [(c["start"], c["end"], "OTROS", collapse_word_loops(c["text"])) for c in sys_cues if c["text"].strip()]
    tagged.sort(key=lambda t: t[0])
    return tagged


def group_by_turn(tagged):
    """Collapse consecutive same-speaker cues into one turn.

    A cue is a whisper segment, a few seconds of speech at most — one
    timestamp+tag per cue reads like a subtitle file, not a transcript, and
    made back-to-back same-speaker lines look like a chopped-up mess. This
    merges runs of the same speaker into a single paragraph instead, the way
    `stamped_text` in transcriber.py already does for a single track.
    """
    turns = []
    for start, end, speaker, text in tagged:
        if turns and turns[-1]["speaker"] == speaker:
            turns[-1]["text"] += " " + text
            turns[-1]["end"] = end
        else:
            turns.append({"start": start, "end": end, "speaker": speaker, "text": text})
    return turns


def _fmt_stamp(ms):
    total = max(0, int(ms)) // 1000
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"[{h:02d}:{m:02d}:{s:02d}]"


def write_merged_transcript(tagged, out_path):
    """One block per speaker turn: a `[stamp] SPEAKER` header line, then the
    turn's text as a single paragraph, blank line between turns."""
    turns = group_by_turn(tagged)
    with open(out_path, "w", encoding="utf-8") as f:
        for i, turn in enumerate(turns):
            if i:
                f.write("\n")
            f.write(f"{_fmt_stamp(turn['start'])} {turn['speaker']}\n{turn['text']}\n")


class RecordingSession:
    """One hotkey-toggle cycle. Call start_recording(), then later
    stop_and_transcribe(). Not reusable across cycles — make a new instance
    each time (mirrors one instance per task in Transcriber)."""

    def __init__(self, model_name=DEFAULT_MODEL, status_cb=None, vocabulary="",
                 level_cb=None, progress_cb=None):
        self.model_name = model_name
        self.status_cb = status_cb or (lambda _m: None)
        self.vocabulary = vocabulary or ""
        self.level_cb = level_cb
        self.progress_cb = progress_cb or (lambda _p: None)
        self._capture = None
        self._dir = None
        self._started = None

    def start_recording(self):
        self._dir = _session_dir()
        mic_path = os.path.join(self._dir, "microphone.wav")
        sys_path = os.path.join(self._dir, "system.wav")
        self._capture = CaptureSession(mic_path, sys_path, level_cb=self.level_cb)
        self.status_cb("Grabando...")
        try:
            self._capture.start()
        except Exception:
            self._capture = None
            shutil.rmtree(self._dir, ignore_errors=True)
            raise
        self._started = time.time()

    def _transcribe_track(self, engine, ffmpeg_path, wav_path, model_path, label, idx,
                          vad_model_path, use_gpu, gpu_index):
        peak = wav_peak_amplitude(wav_path)
        if peak is not None and peak < SILENCE_PEAK:
            self.status_cb(f"({label}: audio en silencio, se omite)")
            return []

        prefix = os.path.join(self._dir, label)
        clean = os.path.join(self._dir, f"{label}.clean.wav")
        self.status_cb(f"Transcribiendo {label}...")
        prepared = prepare(ffmpeg_path, wav_path, clean, label)
        try:
            engine.transcribe(prepared, model_path, prefix, lang=LANG, prompt=self.vocabulary or None,
                              no_speech_thold=NO_SPEECH_THOLD, vad_model_path=vad_model_path,
                              use_gpu=use_gpu, gpu_index=gpu_index,
                              progress_cb=lambda p: self.progress_cb((idx + p / 100.0) / 2 * 100.0))
        except TranscribeError as e:
            if "No speech detected" in str(e):
                self.status_cb(f"({label}: sin voz detectada)")
                return []
            raise
        finally:
            if prepared != wav_path and os.path.isfile(prepared):
                try:
                    os.unlink(prepared)
                except OSError:
                    pass
        return _parse_srt(prefix + ".srt")

    def stop_and_transcribe(self):
        if self._capture is None:
            raise SessionError("No recording in progress")
        mic_path, sys_path = self._capture.stop()
        self._capture = None
        duration = max(0.0, time.time() - self._started) if self._started else 0.0

        whisper_cli = binaries.get_whisper_cli()
        if not whisper_cli:
            raise SessionError("whisper-cli.exe not found under core/whisper/ — run: python tools/setup_binaries.py")
        ffmpeg_path = binaries.ensure_ffmpeg(self.status_cb)

        engine = Transcriber(whisper_cli, ffmpeg_path, MODEL_DIR)
        self.status_cb(f"Checking model {self.model_name}...")
        model_path = engine.ensure_model(self.model_name, status_cb=self.status_cb)

        # VAD is wired end to end (ensure_vad_model, --vad/-vm) but not used
        # here by default — see ADR-011 (and ADR-012 for the retest).
        vad_model_path = None

        gpu = gpu_backend(whisper_cli)
        use_gpu, gpu_index = (True, gpu["devices"][0]["index"]) if gpu and gpu.get("devices") else (bool(gpu), 0)
        if gpu:
            self.status_cb(f"Using GPU: {gpu.get('device', gpu['name'])}")

        mic_cues = self._transcribe_track(engine, ffmpeg_path, mic_path, model_path, "microphone", 0,
                                          vad_model_path, use_gpu, gpu_index)
        sys_cues = self._transcribe_track(engine, ffmpeg_path, sys_path, model_path, "system", 1,
                                          vad_model_path, use_gpu, gpu_index)

        tagged = merge_transcripts(mic_cues, sys_cues)
        out_path = os.path.join(self._dir, "transcript.txt")
        write_merged_transcript(tagged, out_path)
        stamp = os.path.basename(self._dir)
        with open(os.path.join(self._dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump({"name": stamp, "created": stamp, "duration_s": round(duration, 1),
                       "model": self.model_name}, f, ensure_ascii=False)
        self.progress_cb(100.0)
        self.status_cb(f"Ready: {out_path}")
        return out_path
