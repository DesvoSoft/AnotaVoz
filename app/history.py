"""Read/modify the recordings/ folders the UI lists. Pure filesystem; every id
is validated so a crafted id can never leave the recordings folder."""
import json
import os
import re
import shutil

_HEADER = re.compile(r"^\[(\d{2}):(\d{2}):(\d{2})\] (YO|OTROS)$")


def _dir(base, rid):
    if not rid or rid in (".", "..") or any(c in rid for c in ("/", "\\", ":")):
        raise ValueError(f"invalid recording id: {rid!r}")
    return os.path.join(base, rid)


def parse_transcript(text):
    turns, cur = [], None
    for line in text.splitlines():
        m = _HEADER.match(line.strip())
        if m:
            h, mi, s, who = m.groups()
            cur = {"start_s": int(h) * 3600 + int(mi) * 60 + int(s), "speaker": who, "text": ""}
            turns.append(cur)
        elif line.strip() and cur is not None:
            cur["text"] = (cur["text"] + " " + line.strip()).strip()
    return turns


def _meta(d, rid):
    meta = {"name": rid, "created": rid, "duration_s": 0, "model": ""}
    try:
        with open(os.path.join(d, "meta.json"), encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            meta.update({k: data[k] for k in meta if k in data})
    except (OSError, ValueError):
        pass
    return meta


def list_history(base="recordings"):
    if not os.path.isdir(base):
        return []
    items = []
    for rid in sorted(os.listdir(base), reverse=True):
        d = os.path.join(base, rid)
        tx = os.path.join(d, "transcript.txt")
        if not os.path.isfile(tx):
            continue
        try:
            with open(tx, encoding="utf-8", errors="replace") as f:
                turns = parse_transcript(f.read())
        except (OSError, ValueError):
            continue
        item = {"id": rid, **_meta(d, rid)}
        item["preview"] = " ".join(t["text"] for t in turns)[:140]
        items.append(item)
    return items


def load(rid, base="recordings"):
    d = _dir(base, rid)
    with open(os.path.join(d, "transcript.txt"), encoding="utf-8", errors="replace") as f:
        return {"id": rid, "meta": _meta(d, rid), "turns": parse_transcript(f.read())}


def rename(rid, name, base="recordings"):
    d = _dir(base, rid)
    meta = _meta(d, rid)
    meta["name"] = name.strip()[:120] or rid
    with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)


def delete(rid, base="recordings"):
    d = _dir(base, rid)
    try:
        from send2trash import send2trash
        send2trash(os.path.abspath(d))
    except ImportError:
        shutil.rmtree(d)


def _stamp(sec, comma=False):
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" + (",000" if comma else "")


def export(rid, fmt, base="recordings"):
    data = load(rid, base)
    d = _dir(base, rid)
    turns = data["turns"]
    if fmt == "txt":
        return os.path.join(d, "transcript.txt")
    if fmt == "md":
        out = os.path.join(d, "transcript.md")
        with open(out, "w", encoding="utf-8") as f:
            f.write(f"# {data['meta']['name']}\n\n")
            for t in turns:
                who = "Tú" if t["speaker"] == "YO" else "Otros"
                f.write(f"**{who}** `{_stamp(t['start_s'])}`\n\n{t['text']}\n\n")
        return out
    if fmt == "srt":
        out = os.path.join(d, "transcript.srt")
        with open(out, "w", encoding="utf-8") as f:
            for i, t in enumerate(turns, 1):
                end = turns[i]["start_s"] if i < len(turns) else t["start_s"] + 5
                f.write(f"{i}\n{_stamp(t['start_s'], True)} --> {_stamp(end, True)}\n{t['text']}\n\n")
        return out
    raise ValueError(f"unsupported format: {fmt}")
