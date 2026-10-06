"""Persisted settings in %APPDATA%/AnotaVoz/config.json. Tolerant of a
missing, empty or corrupt file: anything unreadable falls back to DEFAULTS."""
import json
import os

_APPDATA = os.environ.get("APPDATA", os.path.expanduser("~"))
DATA_DIR = os.path.join(_APPDATA, "AnotaVoz")  # config, models, log
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")

# The project was called EchoNote up to v0.1.0.
LEGACY_DATA_DIR = os.path.join(_APPDATA, "EchoNote")


def migrate_legacy_dir(old=LEGACY_DATA_DIR, new=DATA_DIR):
    """Carry settings and downloaded models (up to several GB) over from the
    pre-rename folder. Called by each entry point before anything reads the
    data folder. File by file rather than one folder rename: it never
    overwrites what the new folder already has, and it can finish a move that
    was only partly possible before (a file in use, a virtualised AppData).
    Never fatal: at worst the app starts as a fresh install. Returns the
    number of files moved."""
    moved = 0
    if not os.path.isdir(old):
        return moved
    for root, _dirs, files in os.walk(old, topdown=False):
        dest = os.path.join(new, os.path.relpath(root, old))
        for name in files:
            target = os.path.join(dest, name)
            if os.path.exists(target):
                continue
            try:
                os.makedirs(dest, exist_ok=True)
                os.replace(os.path.join(root, name), target)
                moved += 1
            except OSError:
                pass
        try:
            os.rmdir(root)  # only succeeds once the folder is empty
        except OSError:
            pass
    return moved


DEFAULTS = {
    "model": None,
    "vocabulary": "",
    "theme": "system",
    "hotkey": "ctrl+shift+r",
    "pause_hotkey": "ctrl+shift+space",  # "" turns it off
    "mic_device": None,
    "loopback_device": None,
}


def load():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save(cfg):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def _valid(key, value):
    default = DEFAULTS[key]
    if default is None:  # model name or device index: None, str or int
        return value is None or (isinstance(value, (str, int)) and not isinstance(value, bool))
    return isinstance(value, type(default))


def get_settings():
    stored = load()
    return {k: (stored[k] if k in stored and _valid(k, stored[k]) else d) for k, d in DEFAULTS.items()}


def set_settings(patch):
    cfg = load()
    cfg.update({k: v for k, v in patch.items() if k in DEFAULTS})
    save(cfg)
    return get_settings()


def get_model():
    return load().get("model")


def set_model(name):
    return set_settings({"model": name})
