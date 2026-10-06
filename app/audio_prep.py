"""Per-track clean-up before whisper: high-pass the mic, loudness-
normalise both. Falls back to the untouched source on any ffmpeg failure so a
bad filter run can never abort a recording's transcription."""
import os
import subprocess

_LOUDNORM = "loudnorm=I=-16:TP=-1.5:LRA=11"
FILTERS = {
    "microphone": f"highpass=f=80,{_LOUDNORM}",
    "system": _LOUDNORM,
}


def _no_window():
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def build_command(ffmpeg, src, dst, kind):
    if kind not in FILTERS:
        raise ValueError(f"unknown track kind: {kind}")
    return [ffmpeg, "-y", "-i", src, "-vn", "-af", FILTERS[kind],
            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", dst]


def prepare(ffmpeg, src, dst, kind, timeout=600):
    try:
        p = subprocess.run(build_command(ffmpeg, src, dst, kind), stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                           timeout=timeout, creationflags=_no_window())
    except (OSError, subprocess.SubprocessError):
        return src
    if p.returncode != 0 or not os.path.isfile(dst) or os.path.getsize(dst) <= 44:
        return src
    return dst
