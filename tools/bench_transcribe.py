"""Compare transcription configs on one WAV.

    python tools/bench_transcribe.py <audio.wav> [ref.txt] [--model small|large-v3-turbo] [--kind microphone|system]

With a hand-corrected reference the table shows WER per config; without one it
shows word counts and the path of each output so they can be read side by side.
"""
import argparse
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import binaries, config
from app.audio_prep import prepare
from app.session import LANG, MODEL_DIR, NO_SPEECH_THOLD
from app.transcriber import Transcriber, gpu_backend
from app.wer import wer


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("ref", nargs="?")
    ap.add_argument("--model", default="large-v3-turbo")
    ap.add_argument("--kind", default="microphone")
    a = ap.parse_args()

    cli, ffmpeg = binaries.get_whisper_cli(), binaries.ensure_ffmpeg()
    engine = Transcriber(cli, ffmpeg, MODEL_DIR)
    model = engine.ensure_model(a.model)
    gpu = gpu_backend(cli)
    use_gpu = bool(gpu)
    idx = gpu["devices"][0]["index"] if gpu and gpu.get("devices") else 0
    vocab = config.get_settings()["vocabulary"] or None
    ref = open(a.ref, encoding="utf-8").read() if a.ref else None

    tmp = tempfile.mkdtemp(prefix="echonote_bench_")
    clean = prepare(ffmpeg, a.audio, os.path.join(tmp, "clean.wav"), a.kind)
    configs = [
        ("raw, beam1", a.audio, {"beam_size": 1, "best_of": 1}, None),
        ("raw, beam5", a.audio, {}, None),
        ("prep, beam5", clean, {}, None),
        ("prep, beam5, vocab", clean, {}, vocab),
    ]
    print(f"model={a.model} gpu={use_gpu} prepared={'yes' if clean != a.audio else 'FALLBACK'}")
    print(f"{'config':24} {'WER':>7} {'words':>6} {'secs':>6}")
    for name, wav, decode, prompt in configs:
        prefix = os.path.join(tmp, name.replace(" ", "_").replace(",", ""))
        t0 = time.time()
        engine.transcribe(wav, model, prefix, lang=LANG, prompt=prompt, no_speech_thold=NO_SPEECH_THOLD,
                          use_gpu=use_gpu, gpu_index=idx, decode=decode)
        secs = time.time() - t0
        text = open(prefix + ".txt", encoding="utf-8").read()
        w = f"{wer(ref, text) * 100:6.1f}%" if ref else "   n/a"
        print(f"{name:24} {w:>7} {len(text.split()):>6} {secs:6.1f}   {prefix}.txt")


if __name__ == "__main__":
    main()
