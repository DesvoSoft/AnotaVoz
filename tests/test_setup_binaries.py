import hashlib
import os
import zipfile

import pytest

from tools import setup_binaries as sb


def _zip(path, files):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return str(path)


def _manifest(files):
    return {os.path.basename(n): {"sha256": hashlib.sha256(d).hexdigest()} for n, d in files.items()}


def test_install_flattens_and_keeps_only_matching_files(tmp_path):
    files = {"Release/whisper-cli.exe": b"cli", "Release/ggml-cpu-x64.dll": b"cpu", "Release/SDL2.dll": b"no"}
    dest = tmp_path / "whisper"
    names = sb.install(_zip(tmp_path / "w.zip", files), sb.WHISPER_PATTERNS,
                       _manifest({"whisper-cli.exe": b"cli"}), str(dest))
    assert sorted(names) == ["ggml-cpu-x64.dll", "whisper-cli.exe"]
    assert sorted(os.listdir(dest)) == ["ggml-cpu-x64.dll", "whisper-cli.exe"]


def test_install_rejects_wrong_hash_without_touching_dest(tmp_path):
    dest = tmp_path / "whisper"
    dest.mkdir()
    (dest / "whisper-cli.exe").write_bytes(b"good")
    with pytest.raises(sb.SetupError):
        sb.install(_zip(tmp_path / "w.zip", {"whisper-cli.exe": b"tampered"}), sb.WHISPER_PATTERNS,
                   _manifest({"whisper-cli.exe": b"good"}), str(dest))
    assert (dest / "whisper-cli.exe").read_bytes() == b"good"


def test_install_rejects_unrelated_zip(tmp_path):
    with pytest.raises(sb.SetupError):
        sb.install(_zip(tmp_path / "w.zip", {"readme.txt": b"x"}), sb.WHISPER_PATTERNS,
                   _manifest({"whisper-cli.exe": b"cli"}), str(tmp_path / "whisper"))


def test_mismatches_reports_missing_and_modified(tmp_path):
    (tmp_path / "a.dll").write_bytes(b"a")
    (tmp_path / "b.dll").write_bytes(b"changed")
    manifest = _manifest({"a.dll": b"a", "b.dll": b"b", "c.dll": b"c"})
    assert sb.mismatches(str(tmp_path), manifest, ["a.dll", "b.dll", "c.dll"]) == ["b.dll", "c.dll"]


def test_gpu_backend_is_opt_in():
    manifest = sb.load_manifest()
    assert sb.VULKAN_FILE in manifest
    assert sb.VULKAN_FILE not in sb.wanted_files(manifest, gpu=False)
    assert sb.VULKAN_FILE in sb.wanted_files(manifest, gpu=True)
