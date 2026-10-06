"""Fetch the pinned whisper.cpp binaries into core/whisper/ and check them
against core/whisper/MANIFEST.json. The binaries are too big for the repo, so a
fresh clone runs this once (the run*.bat launchers do it on their own).

    python tools/setup_binaries.py                 # CPU only: the light default
    python tools/setup_binaries.py --gpu           # plus the Vulkan GPU backend
    python tools/setup_binaries.py --whisper-zip whisper-bin-x64.zip

--whisper-zip / --vulkan-zip install from an already downloaded release zip,
for machines that cannot reach GitHub. Standard library only.
"""
import argparse
import fnmatch
import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from app import binaries  # noqa: E402

WHISPER_DIR = os.path.join(ROOT, "core", "whisper")
MANIFEST_PATH = os.path.join(WHISPER_DIR, "MANIFEST.json")

# Must match the "source" of each file in MANIFEST.json — the hashes there are
# what actually pin the versions; a wrong URL here fails verification.
WHISPER_ZIP_URL = "https://github.com/ggml-org/whisper.cpp/releases/download/v1.9.2/whisper-bin-x64.zip"
VULKAN_ZIP_URL = "https://github.com/ggml-org/llama.cpp/releases/download/b10472/llama-b10472-bin-win-vulkan-x64.zip"

# ggml picks the best ggml-cpu-*.dll for the CPU it runs on, so take them all.
WHISPER_PATTERNS = ("whisper-cli.exe", "whisper.dll", "ggml*.dll")
VULKAN_FILE = "ggml-vulkan.dll"


class SetupError(Exception):
    pass


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for buf in iter(lambda: f.read(1 << 20), b""):
            h.update(buf)
    return h.hexdigest()


def load_manifest(path=MANIFEST_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)["files"]


def wanted_files(manifest, gpu):
    return [n for n in manifest if gpu or n != VULKAN_FILE]


def mismatches(dest_dir, manifest, names):
    """Names that are missing from dest_dir or whose hash is not the pinned one."""
    bad = []
    for name in names:
        path = os.path.join(dest_dir, name)
        if not os.path.isfile(path) or sha256(path) != manifest[name]["sha256"]:
            bad.append(name)
    return bad


def extract(zip_path, dest_dir, patterns):
    """Copy every member whose file name matches one of `patterns` flat into
    dest_dir, wherever the release zip keeps it. Returns the names written."""
    os.makedirs(dest_dir, exist_ok=True)
    written = []
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            name = os.path.basename(member)
            if not name or not any(fnmatch.fnmatch(name, p) for p in patterns):
                continue
            with zf.open(member) as src, open(os.path.join(dest_dir, name), "wb") as dst:
                shutil.copyfileobj(src, dst)
            written.append(name)
    return written


def install(zip_path, patterns, manifest, dest_dir=WHISPER_DIR):
    """Extract to a staging folder, verify, then move into place — a zip that
    fails verification never touches a working install."""
    with tempfile.TemporaryDirectory() as stage:
        names = extract(zip_path, stage, patterns)
        pinned = [n for n in names if n in manifest]
        if not pinned:
            raise SetupError(f"{os.path.basename(zip_path)} has none of the expected files")
        bad = mismatches(stage, manifest, pinned)
        if bad:
            raise SetupError("Hash mismatch against MANIFEST.json: " + ", ".join(bad))
        os.makedirs(dest_dir, exist_ok=True)
        for name in names:
            shutil.copyfile(os.path.join(stage, name), os.path.join(dest_dir, name))
    return names


def _obtain(local_zip, url, label, tmp_dir):
    if local_zip:
        return local_zip
    path = os.path.join(tmp_dir, os.path.basename(url))
    binaries._fetch(url, path, progress_cb=_progress, label=label)
    print()
    return path


def _progress(msg):
    print("\r" + msg.ljust(60), end="", flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Install the pinned whisper.cpp binaries into core/whisper/.")
    ap.add_argument("--gpu", action="store_true", help="also install the Vulkan GPU backend (~35 MB download)")
    ap.add_argument("--whisper-zip", help="use this whisper-bin-x64.zip instead of downloading")
    ap.add_argument("--vulkan-zip", help="use this llama.cpp Vulkan zip instead of downloading (implies --gpu)")
    ap.add_argument("--skip-ffmpeg", action="store_true", help="do not fetch ffmpeg now (it is fetched on first use)")
    args = ap.parse_args(argv)
    gpu = args.gpu or bool(args.vulkan_zip)

    manifest = load_manifest()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            cpu_names = wanted_files(manifest, gpu=False)
            if args.whisper_zip or mismatches(WHISPER_DIR, manifest, cpu_names):
                zip_path = _obtain(args.whisper_zip, WHISPER_ZIP_URL, "whisper.cpp", tmp)
                install(zip_path, WHISPER_PATTERNS, manifest)
            if gpu and (args.vulkan_zip or mismatches(WHISPER_DIR, manifest, [VULKAN_FILE])):
                zip_path = _obtain(args.vulkan_zip, VULKAN_ZIP_URL, "Vulkan backend", tmp)
                install(zip_path, (VULKAN_FILE,), manifest)
        bad = mismatches(WHISPER_DIR, manifest, wanted_files(manifest, gpu))
        if bad:
            raise SetupError("Still missing or modified after install: " + ", ".join(bad))
        print(f"whisper.cpp ready in {WHISPER_DIR} ({'CPU + Vulkan' if gpu else 'CPU'})")

        if not args.skip_ffmpeg:
            print(f"ffmpeg ready: {binaries.ensure_ffmpeg(_progress)}")
    except (SetupError, OSError, zipfile.BadZipFile) as e:
        print(f"\nSetup failed: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
