import json

from app import history

TX = "[00:00:00] YO\nHola equipo\n\n[00:01:05] OTROS\nBuenos días a todos\n"


def make(base, name, tx=TX, meta=None):
    d = base / name
    d.mkdir(parents=True)
    if tx is not None:
        (d / "transcript.txt").write_text(tx, encoding="utf-8")
    if meta is not None:
        (d / "meta.json").write_text(meta, encoding="utf-8")
    return d


def test_parse_transcript():
    t = history.parse_transcript(TX)
    assert t == [{"start_s": 0, "speaker": "YO", "text": "Hola equipo"},
                 {"start_s": 65, "speaker": "OTROS", "text": "Buenos días a todos"}]


def test_list_skips_no_transcript_and_survives_bad_meta(tmp_path):
    make(tmp_path, "2026-01-01_10-00-00", meta="{broken")
    make(tmp_path, "2026-01-02_10-00-00", tx=None)
    items = history.list_history(str(tmp_path))
    assert [i["id"] for i in items] == ["2026-01-01_10-00-00"]
    assert items[0]["preview"].startswith("Hola equipo")


def test_rename_persists(tmp_path):
    make(tmp_path, "r1")
    history.rename("r1", "Reunión semanal", str(tmp_path))
    assert json.loads((tmp_path / "r1" / "meta.json").read_text(encoding="utf-8"))["name"] == "Reunión semanal"


def test_delete_rejects_path_traversal(tmp_path):
    make(tmp_path, "r1")
    for bad in ("../x", "a/b", "..", ""):
        try:
            history.delete(bad, str(tmp_path))
            assert False
        except ValueError:
            pass
    history.delete("r1", str(tmp_path))
    assert not (tmp_path / "r1").exists()


def test_export_srt_and_md(tmp_path):
    make(tmp_path, "r1")
    srt = open(history.export("r1", "srt", str(tmp_path)), encoding="utf-8").read()
    assert "00:00:00,000 --> 00:01:05,000" in srt and "Hola equipo" in srt
    md = open(history.export("r1", "md", str(tmp_path)), encoding="utf-8").read()
    assert "**Tú**" in md and "**Otros**" in md


def test_non_utf8_transcript_does_not_break_listing(tmp_path):
    d = tmp_path / "r_ansi"
    d.mkdir()
    (d / "transcript.txt").write_bytes("[00:00:00] YO\nañejo ñandú\n".encode("cp1252"))
    make(tmp_path, "r_ok")
    ids = [i["id"] for i in history.list_history(str(tmp_path))]
    assert "r_ok" in ids
    assert history.load("r_ansi", str(tmp_path))["turns"][0]["speaker"] == "YO"
