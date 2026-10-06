from app import config


def _legacy(tmp_path):
    old, new = tmp_path / "EchoNote", tmp_path / "AnotaVoz"
    (old / "models").mkdir(parents=True)
    (old / "config.json").write_text('{"model": "small"}', encoding="utf-8")
    (old / "models" / "ggml-small.bin").write_bytes(b"weights")
    return old, new


def test_legacy_folder_is_moved_once(tmp_path):
    old, new = _legacy(tmp_path)
    assert config.migrate_legacy_dir(str(old), str(new)) == 2
    assert not old.exists()
    assert (new / "config.json").read_text(encoding="utf-8") == '{"model": "small"}'
    assert (new / "models" / "ggml-small.bin").read_bytes() == b"weights"
    assert config.migrate_legacy_dir(str(old), str(new)) == 0


def test_merge_keeps_what_the_new_folder_already_has(tmp_path):
    old, new = _legacy(tmp_path)
    (new / "models").mkdir(parents=True)
    (new / "config.json").write_text('{"model": "large-v3-turbo"}', encoding="utf-8")
    (new / "models" / "ggml-large-v3-turbo.bin").write_bytes(b"big")

    assert config.migrate_legacy_dir(str(old), str(new)) == 1
    assert (new / "config.json").read_text(encoding="utf-8") == '{"model": "large-v3-turbo"}'
    assert sorted(p.name for p in (new / "models").iterdir()) == ["ggml-large-v3-turbo.bin", "ggml-small.bin"]
    # The older config lost to the newer one and stays where it was.
    assert [p.name for p in old.iterdir()] == ["config.json"]


def test_fresh_install_has_nothing_to_migrate(tmp_path):
    assert config.migrate_legacy_dir(str(tmp_path / "EchoNote"), str(tmp_path / "AnotaVoz")) == 0
    assert not (tmp_path / "AnotaVoz").exists()


def test_models_live_in_the_new_data_folder():
    from app import session
    assert session.MODEL_DIR.startswith(config.DATA_DIR) and "AnotaVoz" in config.DATA_DIR
