"""Persisted settings in %APPDATA%/EchoNote/config.json. Tolerant of a
missing, empty or corrupt file: anything unreadable falls back to DEFAULTS."""
import json
import os

CONFIG_PATH = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "EchoNote", "config.json")

DEFAULTS = {
    "model": None,
    "vocabulary": "",
    "theme": "system",
    "hotkey": "ctrl+shift+r",
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
