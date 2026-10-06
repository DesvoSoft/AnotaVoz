import json

from app import config


def use_tmp(tmp_path, monkeypatch):
    p = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_PATH", str(p))
    return p


def test_defaults_when_missing(tmp_path, monkeypatch):
    use_tmp(tmp_path, monkeypatch)
    s = config.get_settings()
    assert s["theme"] == "system" and s["vocabulary"] == "" and s["hotkey"] == "ctrl+shift+r"
    assert s["pause_hotkey"] == "ctrl+shift+space"


def test_corrupt_file_gives_defaults(tmp_path, monkeypatch):
    p = use_tmp(tmp_path, monkeypatch)
    p.write_text("{not json", encoding="utf-8")
    assert config.get_settings()["theme"] == "system"
    assert config.get_model() is None


def test_non_dict_json_ignored(tmp_path, monkeypatch):
    p = use_tmp(tmp_path, monkeypatch)
    p.write_text("[1,2]", encoding="utf-8")
    assert config.get_settings()["theme"] == "system"


def test_set_settings_merges_and_ignores_unknown(tmp_path, monkeypatch):
    p = use_tmp(tmp_path, monkeypatch)
    config.set_model("small")
    s = config.set_settings({"vocabulary": "SIGEC", "evil": 1})
    assert s["vocabulary"] == "SIGEC" and "evil" not in s and s["model"] == "small"
    assert json.loads(p.read_text(encoding="utf-8"))["model"] == "small"


def test_wrong_types_fall_back_to_defaults(tmp_path, monkeypatch):
    p = use_tmp(tmp_path, monkeypatch)
    p.write_text(json.dumps({"hotkey": None, "vocabulary": 5, "theme": ["x"], "model": "small"}), encoding="utf-8")
    s = config.get_settings()
    assert s["hotkey"] == "ctrl+shift+r" and s["vocabulary"] == "" and s["theme"] == "system"
    assert s["model"] == "small"
