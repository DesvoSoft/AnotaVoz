"""Pure text/cue clean-up applied after whisper. No I/O."""
import re
from difflib import SequenceMatcher


def _norm(text):
    return re.sub(r"[^\w\s]", "", text.lower()).strip()


def _overlap_ratio(a, b):
    inter = min(a["end"], b["end"]) - max(a["start"], b["start"])
    if inter <= 0:
        return 0.0
    return inter / max(1.0, a["end"] - a["start"])


def drop_echo(mic_cues, sys_cues, min_overlap=0.6, min_similarity=0.75):
    """Drop mic cues that are the speakers' audio re-captured by the mic.

    A mic cue is an echo when a system cue covers >= min_overlap of its time
    span and the normalised texts are >= min_similarity alike.
    """
    kept = []
    for m in mic_cues:
        mt = _norm(m["text"])
        echo = False
        for s in sys_cues:
            if s["start"] >= m["end"]:
                break
            if _overlap_ratio(m, s) < min_overlap:
                continue
            if SequenceMatcher(None, mt, _norm(s["text"])).ratio() >= min_similarity:
                echo = True
                break
        if not echo:
            kept.append(m)
    return kept


def collapse_repeats(cues, max_run=2):
    """Keep at most max_run consecutive identical cues (hallucination loops)."""
    out, prev, run = [], None, 0
    for c in cues:
        key = _norm(c["text"])
        if key and key == prev:
            run += 1
            if run > max_run:
                continue
        else:
            prev, run = key, 1
        out.append(c)
    return out


def tidy_text(text):
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"([.!?]\s+)([a-záéíóúñ])", lambda m: m.group(1) + m.group(2).upper(), text)


def collapse_word_loops(text, max_run=3, max_ngram=4):
    """Cut a word/phrase repeated back-to-back more than max_run times inside
    one cue ("no, no, no, ..." x50) — the hallucination loop whisper can emit
    within a single segment, which the per-cue collapse cannot see."""
    tokens = text.split()
    keys = [_norm(t) for t in tokens]
    for n in range(1, max_ngram + 1):
        out_t, out_k, i = [], [], 0
        while i < len(tokens):
            run = 1
            while i + (run + 1) * n <= len(tokens) and keys[i + run * n:i + (run + 1) * n] == keys[i:i + n]:
                run += 1
            keep = min(run, max_run) if keys[i:i + n] != [""] * n else run
            out_t += tokens[i:i + keep * n]
            out_k += keys[i:i + keep * n]
            i += run * n
        tokens, keys = out_t, out_k
    return " ".join(tokens)
