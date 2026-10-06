# AnotaVoz: transcripción + GUI web, plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transcripción en español más fiel (sin eco duplicado, audio preprocesado, mejor decodificación, modelo grande) y una GUI web moderna sobre pywebview.

**Architecture:** Módulos puros y testeables (`postproc`, `audio_prep`, `levels`, `wer`, `history`) alimentan `session.py`. `controller.py` suma eventos de nivel/progreso. `app/api.py` es un puente fino hacia `ui/` (HTML/CSS/JS sin build) abierto por `app/webgui.py`. Consola y bandeja siguen sobre el mismo controller.

**Tech Stack:** Python 3.14 (.venv), whisper.cpp (`core/whisper/whisper-cli.exe`), ffmpeg (`core/ffmpeg.exe`), PyAudioWPatch, pywebview, pytest, HTML/CSS/JS vanilla (módulos ES).

**Spec:** `docs/superpowers/specs/2026-10-01-transcripcion-y-gui-design.md`

## Global Constraints

- Idioma de transcripción fijo `es` (`app/session.py::LANG`).
- Pistas mic y sistema nunca se mezclan antes de whisper (ADR-002).
- Pista con pico < `SILENCE_PEAK = 80` no se transcribe (ADR-009); el chequeo se hace sobre el WAV crudo, antes del preprocesado.
- 100 % local/offline; sin llamadas a APIs externas de transcripción.
- Los callbacks del controller llegan desde hilos de fondo: la UI nunca se toca desde ellos directamente.
- Comandos externos se lanzan como lista de argumentos, nunca como string de shell.
- El proyecto **no es repo git**: cada tarea termina con un checkpoint (`pytest` completo en verde) en lugar de commit. Recomendado: `git init` antes de empezar.
- Ejecutar siempre con `.venv\Scripts\python.exe` desde la raíz del proyecto.

## Review Focus

- Mic idéntico al sistema (eco total): el mic queda vacío, sin excepción, y el transcript sigue escribiéndose.
- WAV de ~0 frames o < 1 s: el preprocesado falla o loudnorm no converge; se cae al WAV crudo sin abortar la sesión.
- Vocabulario con comillas, saltos de línea, unicode o > 300 caracteres: se normaliza y trunca; llega a whisper como un solo argumento.
- `config.json` corrupto o vacío: se usan los defaults sin crashear.
- Carpeta de historial sin `transcript.txt` o con `meta.json` corrupto: se lista o se omite, nunca rompe la lista.
- Cierre de ventana en estado `recording`/`transcribing`: cierre ordenado sin hilos colgados.

## File Structure

| Archivo | Responsabilidad |
|---|---|
| `app/postproc.py` (nuevo) | `drop_echo`, `collapse_repeats`, `tidy_text` (puros) |
| `app/audio_prep.py` (nuevo) | comando ffmpeg de limpieza y `prepare()` |
| `app/levels.py` (nuevo) | `rms_level(bytes)` normalizado 0..1 |
| `app/wer.py` (nuevo) | `wer(ref, hyp)` |
| `app/history.py` (nuevo) | listar/cargar/renombrar/borrar/exportar grabaciones |
| `app/api.py` (nuevo) | puente JS ⇄ controller |
| `app/webgui.py` (nuevo) | ventana pywebview |
| `ui/**` (nuevo) | interfaz web |
| `tools/bench_transcribe.py` (nuevo) | banco WER |
| `tests/**` (nuevo) | pytest |
| `app/transcriber.py` | `build_whisper_args`, flags de decodificación |
| `app/session.py` | integra prep + eco + vocabulario + meta.json + callbacks |
| `app/capture.py` | callback de nivel por pista |
| `app/controller.py` | eventos nivel/progreso, descarga de modelo asíncrona |
| `app/config.py` | ajustes completos con defaults y tolerancia a corrupción |
| `run_gui.bat`, `requirements*.txt` | arranque web, dependencias |

---

### Task 1: Infraestructura de pruebas y `postproc` (eco, repeticiones)

**Files:**
- Create: `requirements-dev.txt`, `tests/__init__.py`, `tests/test_postproc.py`, `app/postproc.py`

**Interfaces:**
- Produces: `drop_echo(mic_cues, sys_cues, min_overlap=0.6, min_similarity=0.75) -> list[dict]`, `collapse_repeats(cues, max_run=2) -> list[dict]`, `tidy_text(text) -> str`. Cue = `{"start": ms, "end": ms, "text": str}`.

- [ ] **Step 1: Instalar pytest**

Create `requirements-dev.txt`:
```text
-r requirements.txt
pytest>=8.0
```
Run: `.venv\Scripts\python.exe -m pip install -r requirements-dev.txt`
Expected: pytest instalado. Crear `tests/__init__.py` vacío.

- [ ] **Step 2: Escribir tests que fallan**

`tests/test_postproc.py`:
```python
from app.postproc import collapse_repeats, drop_echo, tidy_text


def cue(s, e, t):
    return {"start": s, "end": e, "text": t}


def test_drop_echo_removes_matching_mic_cue():
    mic = [cue(1000, 3000, "Hola, ¿cómo están todos?"), cue(5000, 7000, "Yo voy a comentar algo")]
    sys = [cue(1100, 3100, "hola cómo están todos")]
    kept = drop_echo(mic, sys)
    assert [c["text"] for c in kept] == ["Yo voy a comentar algo"]


def test_drop_echo_keeps_overlapping_but_different_text():
    mic = [cue(1000, 3000, "Estoy de acuerdo")]
    sys = [cue(1000, 3000, "Entonces cerramos la reunión")]
    assert drop_echo(mic, sys) == mic


def test_drop_echo_full_echo_leaves_empty_not_error():
    mic = [cue(0, 2000, "buenos días")]
    sys = [cue(0, 2000, "Buenos días.")]
    assert drop_echo(mic, sys) == []


def test_drop_echo_handles_empty_inputs():
    assert drop_echo([], [cue(0, 1, "x")]) == []
    assert drop_echo([cue(0, 1000, "x")], []) == [cue(0, 1000, "x")]


def test_collapse_repeats_limits_runs():
    cues = [cue(i, i + 1, "you") for i in range(6)] + [cue(10, 11, "otra cosa")]
    out = collapse_repeats(cues, max_run=2)
    assert [c["text"] for c in out] == ["you", "you", "otra cosa"]


def test_tidy_text_spaces_and_capitals():
    assert tidy_text("hola  mundo. esto  es   una prueba. ¿sí? claro") == "hola mundo. Esto es una prueba. ¿sí? Claro"
```

- [ ] **Step 3: Verificar que fallan**

Run: `.venv\Scripts\python.exe -m pytest tests/test_postproc.py -v`
Expected: FAIL `ModuleNotFoundError: app.postproc`.

- [ ] **Step 4: Implementar**

`app/postproc.py`:
```python
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
```
Nota: el último test espera `"¿sí? claro"` → `"¿sí? Claro"`; la regex lo cubre. `"¿sí?"` queda en minúscula porque el prefijo `¿` no está tras `[.!?]\s+`.

- [ ] **Step 5: Verificar que pasan**

Run: `.venv\Scripts\python.exe -m pytest tests/test_postproc.py -v`
Expected: 6 PASS.

- [ ] **Step 6: Checkpoint**

Run: `.venv\Scripts\python.exe -m pytest -q` → todo verde.

---

### Task 2: Preprocesado de audio (`audio_prep`)

**Files:**
- Create: `app/audio_prep.py`, `tests/test_audio_prep.py`

**Interfaces:**
- Produces: `build_command(ffmpeg, src, dst, kind) -> list[str]`, `prepare(ffmpeg, src, dst, kind) -> str` (devuelve `dst` si salió bien, `src` si ffmpeg falló: nunca lanza por fallo de filtro).

- [ ] **Step 1: Tests que fallan**

`tests/test_audio_prep.py`:
```python
import os
import wave

import pytest

from app import binaries
from app.audio_prep import build_command, prepare


def test_mic_command_has_denoise_and_loudnorm():
    cmd = build_command("ffmpeg.exe", "in.wav", "out.wav", "microphone")
    af = cmd[cmd.index("-af") + 1]
    assert "highpass" in af and "afftdn" in af and "loudnorm" in af
    assert cmd[-1] == "out.wav" and "-ar" in cmd and "16000" in cmd


def test_system_command_skips_denoise():
    af = build_command("f", "a", "b", "system")
    af = af[af.index("-af") + 1]
    assert "loudnorm" in af and "afftdn" not in af


def test_unknown_kind_rejected():
    with pytest.raises(ValueError):
        build_command("f", "a", "b", "otra")


def _tiny_wav(path, seconds=0.0):
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * seconds))


def test_prepare_falls_back_to_source_on_ffmpeg_failure(tmp_path):
    src = str(tmp_path / "in.wav")
    _tiny_wav(src, 0.0)  # 0 frames
    out = str(tmp_path / "out.wav")
    result = prepare(binaries.ensure_ffmpeg(), src, out, "microphone")
    assert result in (src, out) and os.path.exists(result)


def test_prepare_missing_ffmpeg_returns_source(tmp_path):
    src = str(tmp_path / "in.wav")
    _tiny_wav(src, 0.5)
    assert prepare(str(tmp_path / "no-ffmpeg.exe"), src, str(tmp_path / "o.wav"), "system") == src
```

- [ ] **Step 2:** `pytest tests/test_audio_prep.py -v` → FAIL (módulo inexistente).

- [ ] **Step 3: Implementar**

`app/audio_prep.py`:
```python
"""Per-track clean-up before whisper: band-limit/denoise the mic, loudness-
normalise both. Falls back to the untouched source on any ffmpeg failure so a
bad filter run can never abort a recording's transcription."""
import os
import subprocess

_LOUDNORM = "loudnorm=I=-16:TP=-1.5:LRA=11"
FILTERS = {
    "microphone": f"highpass=f=80,afftdn=nf=-25,{_LOUDNORM}",
    "system": _LOUDNORM,
}


def _no_window():
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def build_command(ffmpeg, src, dst, kind):
    if kind not in FILTERS:
        raise ValueError(f"unknown track kind: {kind}")
    return [ffmpeg, "-y", "-i", src, "-vn", "-af", FILTERS[kind],
            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", dst]


def prepare(ffmpeg, src, dst, kind, timeout=600):
    try:
        p = subprocess.run(build_command(ffmpeg, src, dst, kind), stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                           timeout=timeout, creationflags=_no_window())
    except (OSError, subprocess.SubprocessError):
        return src
    if p.returncode != 0 or not os.path.isfile(dst) or os.path.getsize(dst) <= 44:
        return src
    return dst
```

- [ ] **Step 4:** `pytest tests/test_audio_prep.py -v` → PASS.
- [ ] **Step 5: Checkpoint** `pytest -q` verde.

---

### Task 3: Argumentos de whisper (beam, best-of, contexto) como función pura

**Files:**
- Modify: `app/transcriber.py` (`_run_chunk`, líneas ~524-541)
- Create: `tests/test_whisper_args.py`

**Interfaces:**
- Produces: `build_whisper_args(whisper_cli, model_path, wav, prefix, lang, threads, prompt=None, use_gpu=False, gpu_index=0, no_speech_thold=None, vad_model_path=None, beam_size=5, best_of=5, max_context=64) -> list[str]`; `normalize_prompt(text, limit=CARRY_CHARS) -> str|None`.

- [ ] **Step 1: Verificar flags reales**

Run: `core\whisper\whisper-cli.exe --help` y confirmar que existen `-bs`, `-bo`, `-mc`. Si alguno no existe, quitarlo de la función y del test.

- [ ] **Step 2: Tests que fallan**

`tests/test_whisper_args.py`:
```python
from app.transcriber import build_whisper_args, normalize_prompt


def args(**kw):
    base = dict(whisper_cli="w.exe", model_path="m.bin", wav="a.wav", prefix="p", lang="es", threads=4)
    base.update(kw)
    return build_whisper_args(**base)


def test_decoding_flags_present():
    a = args()
    assert a[a.index("-bs") + 1] == "5" and a[a.index("-bo") + 1] == "5"
    assert a[a.index("-mc") + 1] == "64"


def test_cpu_vs_gpu():
    assert "-ng" in args()
    g = args(use_gpu=True, gpu_index=1)
    assert "-ng" not in g and g[g.index("-dev") + 1] == "1"


def test_prompt_is_single_argument():
    a = args(prompt='Daniel "Dani" Pérez\nSIGEC')
    assert a[a.index("--prompt") + 1] == 'Daniel "Dani" Pérez SIGEC'


def test_normalize_prompt_truncates_and_empties():
    assert normalize_prompt("   ") is None
    assert len(normalize_prompt("x" * 1000)) <= 300
    assert normalize_prompt(None) is None
```

- [ ] **Step 3:** `pytest tests/test_whisper_args.py -v` → FAIL.

- [ ] **Step 4: Implementar.** En `app/transcriber.py`, tras `_PROGRESS_RE`, agregar:
```python
def normalize_prompt(text, limit=CARRY_CHARS):
    """One line, whitespace-collapsed, tail-truncated (whisper keeps the end
    of an over-long prompt). None when nothing is left."""
    if not text:
        return None
    text = re.sub(r"\s+", " ", text).strip()
    return text[-limit:] or None


def build_whisper_args(whisper_cli, model_path, wav, prefix, lang, threads, prompt=None,
                       use_gpu=False, gpu_index=0, no_speech_thold=None, vad_model_path=None,
                       beam_size=5, best_of=5, max_context=64):
    args = [whisper_cli, "-m", model_path, "-f", wav, "-l", lang, "-t", str(threads),
            "-pp", "-sns", "-osrt", "-of", prefix,
            "-bs", str(beam_size), "-bo", str(best_of), "-mc", str(max_context)]
    if no_speech_thold is not None:
        args += ["-nth", str(no_speech_thold)]
    if vad_model_path:
        args += ["--vad", "-vm", vad_model_path]
    if use_gpu:
        args += ["-dev", str(gpu_index)]
    else:
        args.append("-ng")
    prompt = normalize_prompt(prompt)
    if prompt:
        args += ["--prompt", prompt]
    return args
```
Y en `_run_chunk` reemplazar la construcción de `args` (de `args = [self.whisper_cli, ...` hasta `args += ["--prompt", prompt]`) por:
```python
        args = build_whisper_args(self.whisper_cli, model_path, wav, prefix, lang, threads,
                                  prompt, use_gpu, gpu_index, no_speech_thold, vad_model_path)
```
El `prompt` de chunk ya combina vocabulario + cola: `normalize_prompt` lo trunca por la cola.

- [ ] **Step 5:** `pytest tests/test_whisper_args.py -v` → PASS.
- [ ] **Step 6: Humo real:** transcribir `recordings/2026-09-21_15-16-55/microphone.wav` con `tools/test_transcribe.py` (o el script equivalente) y confirmar que whisper acepta los flags (exit 0, srt generado).
- [ ] **Step 7: Checkpoint** `pytest -q` verde.

---

### Task 4: Ajustes persistentes (`config.py`)

**Files:**
- Modify: `app/config.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Produces: `DEFAULTS` dict, `get_settings() -> dict` (defaults + guardado), `set_settings(patch: dict) -> dict`. Mantiene `get_model()`/`set_model()`. Claves: `model, vocabulary, theme ("system"|"dark"|"light"), hotkey, mic_device (int|None), loopback_device (int|None)`.

- [ ] **Step 1: Tests**

`tests/test_config.py`:
```python
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
```

- [ ] **Step 2:** FAIL.
- [ ] **Step 3: Implementar** (reemplazar contenido de `app/config.py`):
```python
"""Persisted settings in %APPDATA%/AnotaVoz/config.json. Tolerant of a
missing, empty or corrupt file: anything unreadable falls back to DEFAULTS."""
import json
import os

CONFIG_PATH = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "AnotaVoz", "config.json")

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


def get_settings():
    return {**DEFAULTS, **{k: v for k, v in load().items() if k in DEFAULTS}}


def set_settings(patch):
    cfg = load()
    cfg.update({k: v for k, v in patch.items() if k in DEFAULTS})
    save(cfg)
    return get_settings()


def get_model():
    return load().get("model")


def set_model(name):
    return set_settings({"model": name})
```
- [ ] **Step 4:** PASS. **Step 5: Checkpoint** verde.

---

### Task 5: Integrar en `session.py` (prep + eco + vocabulario + meta.json + callbacks)

**Files:**
- Modify: `app/session.py`
- Create: `tests/test_session_merge.py`

**Interfaces:**
- Consumes: `drop_echo`, `collapse_repeats`, `prepare`, `config.get_settings`.
- Produces: `RecordingSession(model_name, status_cb=None, vocabulary="", level_cb=None, progress_cb=None)`; `merge_transcripts(mic_cues, sys_cues)` ahora aplica `drop_echo` y `collapse_repeats`; escribe `meta.json` `{"name", "created", "duration_s", "model", "tracks": [..]}` en la carpeta de sesión. `level_cb(kind: "microphone"|"system", value: float)`, `progress_cb(pct: float)`.

- [ ] **Step 1: Test**

`tests/test_session_merge.py`:
```python
from app.session import merge_transcripts, group_by_turn


def cue(s, e, t):
    return {"start": s, "end": e, "text": t}


def test_merge_drops_echo_and_orders():
    mic = [cue(1000, 3000, "hola a todos"), cue(8000, 9000, "yo sigo")]
    sys = [cue(1000, 3000, "Hola a todos."), cue(4000, 6000, "gracias por venir")]
    tagged = merge_transcripts(mic, sys)
    assert [(t[2], t[3]) for t in tagged] == [("OTROS", "Hola a todos."), ("OTROS", "gracias por venir"), ("YO", "yo sigo")]


def test_merge_total_echo_mic_empty_ok():
    mic = [cue(0, 2000, "buenos días")]
    sys = [cue(0, 2000, "buenos días")]
    tagged = merge_transcripts(mic, sys)
    assert [t[2] for t in tagged] == ["OTROS"]
    assert group_by_turn(tagged)[0]["speaker"] == "OTROS"


def test_merge_collapses_whisper_loop():
    sys = [cue(i * 1000, i * 1000 + 900, "you") for i in range(8)]
    assert len(merge_transcripts([], sys)) == 2
```
- [ ] **Step 2:** FAIL (eco no aplicado aún).
- [ ] **Step 3: Implementar** en `app/session.py`:
  1. Imports: `import json, time`, `from app.audio_prep import prepare`, `from app.postproc import collapse_repeats, drop_echo`, `from app import config as config_store`.
  2. `merge_transcripts`:
```python
def merge_transcripts(mic_cues, sys_cues):
    mic_cues = collapse_repeats(drop_echo(mic_cues, sys_cues))
    sys_cues = collapse_repeats(sys_cues)
    tagged = [(c["start"], c["end"], "YO", c["text"].strip()) for c in mic_cues if c["text"].strip()]
    tagged += [(c["start"], c["end"], "OTROS", c["text"].strip()) for c in sys_cues if c["text"].strip()]
    tagged.sort(key=lambda t: t[0])
    return tagged
```
  3. `RecordingSession.__init__` agrega `vocabulary=""`, `level_cb=None`, `progress_cb=None` (guardarlos; `self._started = None`).
  4. `start_recording`: `self._capture = CaptureSession(mic_path, sys_path, level_cb=self.level_cb)` (la firma se agrega en Task 7) y `self._started = time.time()`.
  5. `_transcribe_track(self, engine, ffmpeg_path, wav_path, model_path, label, ...)`: tras el chequeo de pico, `prepared = prepare(ffmpeg_path, wav_path, os.path.join(self._dir, f"{label}.clean.wav"), label)`; transcribir `prepared`; en `finally` borrar `*.clean.wav` si existe y es distinto de `wav_path`. Pasar `prompt=self.vocabulary or None` y `progress_cb=self._track_progress(idx)` (progreso global = (idx + p/100)/2*100).
  6. `stop_and_transcribe`: al final de transcribir, escribir `meta.json`:
```python
        duration = max(0.0, time.time() - self._started) if self._started else 0.0
        with open(os.path.join(self._dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump({"name": os.path.basename(self._dir), "created": os.path.basename(self._dir),
                       "duration_s": round(duration, 1), "model": self.model_name}, f, ensure_ascii=False)
```
  7. Vocabulario por defecto: en `controller` (Task 8) se pasa `config_store.get_settings()["vocabulary"]`.
- [ ] **Step 4:** PASS. **Step 5: Checkpoint** verde.

---

### Task 6: WER y banco de pruebas

**Files:**
- Create: `app/wer.py`, `tests/test_wer.py`, `tools/bench_transcribe.py`, `tests/fixtures/` (referencia aportada por el usuario)

**Interfaces:**
- Produces: `wer(ref: str, hyp: str) -> float` (palabras, normalizado: minúsculas, sin puntuación). CLI `python tools/bench_transcribe.py <audio.wav> <ref.txt>` imprime tabla `config | WER | segundos`.

- [ ] **Step 1: Test**

`tests/test_wer.py`:
```python
from app.wer import wer


def test_identical_is_zero():
    assert wer("Hola, mundo.", "hola mundo") == 0.0


def test_one_substitution_in_four():
    assert wer("uno dos tres cuatro", "uno dos tres cinco") == 0.25


def test_empty_reference():
    assert wer("", "") == 0.0
    assert wer("", "algo") == 1.0
```
- [ ] **Step 2:** FAIL. **Step 3: Implementar** `app/wer.py`:
```python
import re


def _words(t):
    return re.sub(r"[^\w\s]", " ", t.lower()).split()


def wer(ref, hyp):
    r, h = _words(ref), _words(hyp)
    if not r:
        return 0.0 if not h else 1.0
    prev = list(range(len(h) + 1))
    for i, rw in enumerate(r, 1):
        cur = [i]
        for j, hw in enumerate(h, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rw != hw)))
        prev = cur
    return prev[-1] / len(r)
```
- [ ] **Step 4:** PASS.
- [ ] **Step 5: `tools/bench_transcribe.py`:** carga el WAV, para cada configuración de `CONFIGS` (`baseline`: sin prep, `-bs 1 -bo 1`; `beam`: beam 5; `prep+beam`: prepare + beam 5; `prep+beam+vocab`: + vocabulario de `config`) ejecuta `Transcriber.transcribe` con `use_gpu` auto, lee el `.txt` y imprime `wer` y tiempo. Parámetros de decodificación se pasan vía un nuevo kwarg `decode={"beam_size":..,"best_of":..}` en `Transcriber.transcribe/_run_chunk` (default `{}` = `build_whisper_args` defaults). Añadir ese kwarg en este paso.
- [ ] **Step 6: Pedir referencia al usuario** (2-3 min corregidos a mano) en `tests/fixtures/ref.txt` + audio `tests/fixtures/ref.wav`. Sin ella el banco corre pero marca "sin referencia" y las mejoras A2-A5 quedan sin validar por WER.
- [ ] **Step 7:** Ejecutar el banco; guardar resultados en `docs/DECISIONS.md` (ADR-012) tras Task 12.
- [ ] **Step 8: Checkpoint** `pytest -q` verde.

---

### Task 7: Niveles de audio por pista (`levels` + `capture`)

**Files:**
- Create: `app/levels.py`, `tests/test_levels.py`
- Modify: `app/capture.py`

**Interfaces:**
- Produces: `rms_level(data: bytes, channels: int = 1) -> float` en 0..1 (int16 little-endian). `StreamRecorder(pa, device_info, out_path, on_level=None)`, `CaptureSession(mic_path, system_path, level_cb=None)` donde `level_cb("microphone"|"system", float)`.

- [ ] **Step 1: Test**

`tests/test_levels.py`:
```python
import struct

from app.levels import rms_level


def pcm(vals):
    return struct.pack(f"<{len(vals)}h", *vals)


def test_silence_is_zero():
    assert rms_level(pcm([0] * 100)) == 0.0


def test_full_scale_is_one():
    assert abs(rms_level(pcm([32767, -32768] * 50)) - 1.0) < 0.01


def test_empty_and_odd_length_safe():
    assert rms_level(b"") == 0.0
    assert rms_level(b"\x01") == 0.0
```
- [ ] **Step 2:** FAIL. **Step 3:** `app/levels.py`:
```python
import array
import math
import sys


def rms_level(data, channels=1):
    n = len(data) // 2
    if n == 0:
        return 0.0
    samples = array.array("h")
    samples.frombytes(data[: n * 2])
    if sys.byteorder == "big":
        samples.byteswap()
    total = sum(s * s for s in samples)
    return min(1.0, math.sqrt(total / n) / 32768.0 * 1.0)
```
(`channels` queda reservado; no se usa.)
- [ ] **Step 4:** PASS.
- [ ] **Step 5: `capture.py`:** en `StreamRecorder.__init__` aceptar `on_level=None`; en `_callback` tras `self._queue.put(in_data)`: `if self._on_level: self._on_level(rms_level(in_data))`. En `CaptureSession.__init__` aceptar `level_cb=None`; al crear los recorders: `on_level=(lambda v: self._level_cb("microphone", v)) if self._level_cb else None` y análogo `"system"`. Mantener el callback rápido: `rms_level` sobre 1024 frames es trivial; si el perfilado muestra costo, decimar a 1 de cada 2 callbacks.
- [ ] **Step 6: Humo real:** `tools/test_capture.py` sigue grabando 2 WAV completos.
- [ ] **Step 7: Checkpoint** verde.

---

### Task 8: Controller: eventos, descarga de modelo, vocabulario

**Files:**
- Modify: `app/controller.py`
- Create: `tests/test_controller.py`

**Interfaces:**
- Produces: `RecordingController(..., on_level=None, on_progress=None)`; `controller.download_model(name, on_progress, on_done)` (hilo, no bloquea; `on_done(ok: bool, message: str)`); `controller.state` (property); `controller.has_model(name) -> bool`; `controller.settings()`. Pasa `vocabulary` de `config_store.get_settings()` a `RecordingSession`, y `level_cb`/`progress_cb`.

- [ ] **Step 1: Test** (con `RecordingSession` y `Transcriber` falsos vía monkeypatch):

`tests/test_controller.py`:
```python
import threading

from app import controller as ctl


class FakeEngine:
    def __init__(self, *a, **k): pass
    def has_model(self, n): return getattr(FakeEngine, "present", False)
    def ensure_model(self, name, progress_cb=None, status_cb=None):
        if progress_cb: progress_cb(50.0); progress_cb(100.0)
        FakeEngine.present = True
        return "x"


def test_download_model_reports_progress_and_done(monkeypatch):
    monkeypatch.setattr(ctl, "Transcriber", FakeEngine)
    monkeypatch.setattr(ctl.binaries, "get_whisper_cli", lambda: "w")
    monkeypatch.setattr(ctl.binaries, "ensure_ffmpeg", lambda *a, **k: "f")
    c = ctl.RecordingController(model_name="small", on_log=lambda m: None)
    seen, done = [], threading.Event()
    result = {}
    c.download_model("large-v3-turbo", seen.append, lambda ok, msg: (result.update(ok=ok), done.set()))
    assert done.wait(5) and result["ok"] and seen[-1] == 100.0


def test_download_unknown_model_fails_fast():
    c = ctl.RecordingController(model_name="small", on_log=lambda m: None)
    done = threading.Event(); out = {}
    c.download_model("nope", None, lambda ok, msg: (out.update(ok=ok), done.set()))
    assert done.wait(2) and out["ok"] is False
```
- [ ] **Step 2:** FAIL. **Step 3: Implementar:**
```python
    @property
    def state(self):
        return self._state

    def has_model(self, name):
        whisper_cli = binaries.get_whisper_cli()
        return bool(whisper_cli) and Transcriber(whisper_cli, None, MODEL_DIR).has_model(name)

    def download_model(self, name, on_progress=None, on_done=None):
        def run():
            ok, msg = False, ""
            try:
                if name not in MODELS:
                    raise ValueError(f"Unknown model '{name}'")
                whisper_cli = binaries.get_whisper_cli()
                if not whisper_cli:
                    raise RuntimeError("whisper-cli.exe not found")
                engine = Transcriber(whisper_cli, binaries.ensure_ffmpeg(), MODEL_DIR)
                engine.ensure_model(name, progress_cb=on_progress, status_cb=self.on_log)
                ok, msg = True, "ok"
            except Exception as e:
                msg = str(e)
            if on_done:
                on_done(ok, msg)
        threading.Thread(target=run, daemon=True).start()
```
En `__init__` agregar `self.on_level = on_level or (lambda k, v: None)` y `self.on_progress = on_progress or (lambda p: None)`. En `toggle()` crear `RecordingSession(model_name=..., status_cb=self.on_log, vocabulary=config_store.get_settings()["vocabulary"], level_cb=self.on_level, progress_cb=self.on_progress)`. El hotkey usa `config_store.get_settings()["hotkey"]` si no se pasa uno. Añadir `import` de `MODEL_DIR` ya existente.
- [ ] **Step 4:** PASS. **Step 5: Checkpoint** verde (incluye que `main.py` y `tray.py` siguen importando sin cambios).

---

### Task 9: Historial (`history.py`)

**Files:**
- Create: `app/history.py`, `tests/test_history.py`

**Interfaces:**
- Produces:
  - `list_history(base="recordings") -> list[{"id","name","created","duration_s","model","preview"}]` (más reciente primero; omite carpetas sin `transcript.txt`; `meta.json` corrupto → usa defaults).
  - `parse_transcript(text) -> list[{"start_s":int,"speaker":"YO"|"OTROS","text":str}]`.
  - `load(id, base) -> {"meta":..., "turns":[...]}`, `rename(id, name, base)`, `delete(id, base)` (mueve a papelera si existe `send2trash`, si no, `shutil.rmtree` tras validar que `id` no contiene separadores), `export(id, fmt: "txt"|"md"|"srt", base) -> str` (ruta escrita).

- [ ] **Step 1: Tests**

`tests/test_history.py`:
```python
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
            history.delete(bad, str(tmp_path)); assert False
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
```
- [ ] **Step 2:** FAIL. **Step 3: Implementar `app/history.py`:**
```python
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
            with open(tx, encoding="utf-8") as f:
                turns = parse_transcript(f.read())
        except OSError:
            continue
        item = {"id": rid, **_meta(d, rid)}
        item["preview"] = " ".join(t["text"] for t in turns)[:140]
        items.append(item)
    return items


def load(rid, base="recordings"):
    d = _dir(base, rid)
    with open(os.path.join(d, "transcript.txt"), encoding="utf-8") as f:
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
        send2trash(d)
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
```
- [ ] **Step 4:** PASS. **Step 5: Checkpoint** verde.

---

### Task 10: Puente `Api` y ventana `webgui`

**Files:**
- Create: `app/api.py`, `app/webgui.py`, `tests/test_api.py`
- Modify: `requirements.txt` (agregar `pywebview>=5.0`, `send2trash>=1.8`), `run_gui.bat` (`python -m app.webgui`)

**Interfaces:**
- Consumes: `RecordingController`, `history`, `config`, `MODELS`, `MODEL_LABELS`, `gpu_backend`, `devices`.
- Produces (todos JSON-serializables, expuestos a JS vía `pywebview.api.<name>`):
  `bootstrap() -> {state, model, models:[{name,label,note,size_mb,installed}], gpu, settings, history}`, `toggle()`, `set_model(name)`, `download_model(name)`, `get_settings()`, `set_settings(patch)`, `list_devices() -> {inputs:[{index,name}], loopbacks:[...]}`, `list_history()`, `load_transcript(id)`, `rename(id,name)`, `delete(id)`, `export(id,fmt)`, `open_folder(id)`.
- Eventos hacia JS vía `window.echo.emit(name, payload)`: `state` (str), `log` (str), `levels` ({microphone, system}, ≤ 20 Hz), `progress` (float), `model_download` ({name, pct, done, error}), `history_changed` ().

- [ ] **Step 1: Test con controller y emisor falsos**

`tests/test_api.py`:
```python
from app.api import Api


class FakeController:
    def __init__(self):
        self.state = "idle"; self.model_name = "small"; self.toggled = 0; self.set = None
    def toggle(self): self.toggled += 1
    def set_model(self, n): self.set = n
    def has_model(self, n): return n == "small"
    def download_model(self, n, p, d): p(10.0); d(True, "ok")


def make():
    events = []
    api = Api(controller_factory=lambda **kw: FakeController(), emit=lambda n, p=None: events.append((n, p)))
    return api, events


def test_bootstrap_shape():
    api, _ = make()
    b = api.bootstrap()
    assert {"state", "model", "models", "gpu", "settings", "history"} <= set(b)
    assert any(m["name"] == "small" and m["installed"] for m in b["models"])


def test_toggle_delegates():
    api, _ = make(); api.toggle()
    assert api._controller.toggled == 1


def test_levels_are_throttled():
    api, events = make()
    for _ in range(200):
        api._on_level("microphone", 0.5)
    assert 0 < sum(1 for n, _ in events if n == "levels") < 200


def test_download_emits_progress_and_done():
    api, events = make(); api.download_model("large-v3-turbo")
    kinds = [p for n, p in events if n == "model_download"]
    assert kinds[0]["pct"] == 10.0 and kinds[-1]["done"] is True


def test_bad_history_id_returns_error_not_exception():
    api, _ = make()
    assert api.load_transcript("../etc")["error"]
```
- [ ] **Step 2:** FAIL. **Step 3: Implementar `app/api.py`:**
```python
"""JS <-> Python bridge. Public methods are what the UI may call; everything
private is underscore-prefixed because pywebview introspects public attributes."""
import json
import os
import threading
import time

from app import config, history
from app.transcriber import MODEL_LABELS, MODELS, gpu_backend

LEVEL_INTERVAL = 0.05  # seconds, ~20 Hz


class Api:
    def __init__(self, controller_factory, emit):
        self._emit = emit
        self._lock = threading.Lock()
        self._last_level = 0.0
        self._levels = {"microphone": 0.0, "system": 0.0}
        self._controller = controller_factory(
            on_state=lambda s: self._emit("state", s),
            on_log=self._on_log,
            on_level=self._on_level,
            on_progress=lambda p: self._emit("progress", p),
        )

    # --- controller callbacks (background threads) ---
    def _on_log(self, msg):
        self._emit("log", str(msg))
        if str(msg).startswith("Ready:"):
            self._emit("history_changed", None)

    def _on_level(self, kind, value):
        now = time.monotonic()
        with self._lock:
            self._levels[kind] = value
            if now - self._last_level < LEVEL_INTERVAL:
                return
            self._last_level = now
            snapshot = dict(self._levels)
        self._emit("levels", snapshot)

    # --- lifecycle ---
    def _start(self):
        self._controller.start()

    def _shutdown(self):
        self._controller.shutdown()

    # --- API for JS ---
    def bootstrap(self):
        gpu = None
        try:
            from app import binaries
            cli = binaries.get_whisper_cli()
            g = gpu_backend(cli) if cli else None
            gpu = (g.get("device") or g["name"]) if g else None
        except Exception:
            gpu = None
        return {
            "state": self._controller.state,
            "model": self._controller.model_name,
            "models": self._models(),
            "gpu": gpu,
            "settings": config.get_settings(),
            "history": history.list_history(),
        }

    def _models(self):
        return [{"name": n, "label": MODEL_LABELS.get(n, {}).get("label", n),
                 "note": MODEL_LABELS.get(n, {}).get("note", ""), "size_mb": spec[2],
                 "installed": self._controller.has_model(n)} for n, spec in MODELS.items()]

    def toggle(self):
        self._controller.toggle()

    def set_model(self, name):
        self._controller.set_model(name)
        return self.bootstrap()["models"]

    def download_model(self, name):
        def progress(p):
            self._emit("model_download", {"name": name, "pct": p, "done": False, "error": None})

        def done(ok, msg):
            self._emit("model_download", {"name": name, "pct": 100.0 if ok else 0.0, "done": ok,
                                          "error": None if ok else msg})
        self._controller.download_model(name, progress, done)

    def get_settings(self):
        return config.get_settings()

    def set_settings(self, patch):
        return config.set_settings(patch if isinstance(patch, dict) else {})

    def list_devices(self):
        try:
            import pyaudiowpatch as pa
            from app import devices
            p = pa.PyAudio()
            try:
                ins = [{"index": d["index"], "name": d["name"]} for d in devices.list_input_devices(p)]
                outs = [{"index": d["index"], "name": d["name"]} for d in devices.list_loopback_devices(p)]
            finally:
                p.terminate()
            return {"inputs": ins, "loopbacks": outs}
        except Exception as e:
            return {"inputs": [], "loopbacks": [], "error": str(e)}

    def list_history(self):
        return history.list_history()

    def _guard(self, fn, *args):
        try:
            return fn(*args)
        except (ValueError, OSError) as e:
            return {"error": str(e)}

    def load_transcript(self, rid):
        return self._guard(history.load, rid)

    def rename(self, rid, name):
        r = self._guard(history.rename, rid, name)
        self._emit("history_changed", None)
        return r

    def delete(self, rid):
        r = self._guard(history.delete, rid)
        self._emit("history_changed", None)
        return r

    def export(self, rid, fmt):
        return self._guard(history.export, rid, fmt)

    def open_folder(self, rid):
        def go():
            d = os.path.join("recordings", rid)
            if os.path.isdir(d) and not any(c in rid for c in ("/", "\\")):
                os.startfile(os.path.abspath(d))
        return self._guard(go)
```
`controller_factory` real: `lambda **kw: RecordingController(**kw)`.
- [ ] **Step 4: `app/webgui.py`:**
```python
"""pywebview front-end. The window is created first; the controller starts
after the page is loaded so early events are not lost."""
import json
import os

import webview

from app import single_instance
from app.api import Api
from app.controller import RecordingController

UI_INDEX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui", "index.html")


def main():
    if not single_instance.acquire():
        print("AnotaVoz is already running.")
        return
    holder = {}

    def emit(name, payload=None):
        w = holder.get("window")
        if w is None:
            return
        try:
            w.evaluate_js(f"window.echo && window.echo.emit({json.dumps(name)}, {json.dumps(payload)})")
        except Exception:
            pass  # window closing

    api = Api(controller_factory=lambda **kw: RecordingController(**kw), emit=emit)
    window = webview.create_window("AnotaVoz", UI_INDEX, js_api=api, width=1120, height=740,
                                   min_size=(760, 540), background_color="#0b0d12")
    holder["window"] = window
    window.events.loaded += lambda: api._start()
    window.events.closing += lambda: api._shutdown()
    webview.start()


if __name__ == "__main__":
    main()
```
Nota: `loaded` se dispara en cada recarga; `_start` debe ser idempotente → en `Api._start` usar un flag `self._started`.
- [ ] **Step 5:** `pip install -r requirements.txt`; `pytest tests/test_api.py -v` → PASS.
- [ ] **Step 6: Checkpoint** verde.

---

### Task 11: Interfaz web (`ui/`)

**Files:**
- Create: `ui/index.html`, `ui/css/app.css`, `ui/js/bridge.js`, `ui/js/waveform.js`, `ui/js/app.js`

**Interfaces:**
- Consumes: `pywebview.api.*` y `window.echo.emit` de Task 10. `bridge.js` provee un **mock** cuando `window.pywebview` no existe, para verificar en el navegador integrado.
- Produces: `window.echo = { on(name, fn), emit(name, payload) }`.

- [ ] **Step 1: `ui/js/bridge.js`**
```js
// Event bus + API access. Falls back to an in-memory mock when opened in a
// plain browser so the UI can be developed and screenshotted without Python.
const handlers = {};
window.echo = {
  on(name, fn) { (handlers[name] ||= []).push(fn); },
  emit(name, payload) { (handlers[name] || []).forEach(fn => fn(payload)); },
};

const mock = (() => {
  let state = 'idle', timer = null;
  const history = [
    { id: '2026-09-21_14-27-54', name: 'Reunión de seguimiento', duration_s: 181, model: 'small', preview: 'Me dudaba que tenía con los organismos colegiados…' },
    { id: '2026-09-21_15-16-55', name: '2026-09-21_15-16-55', duration_s: 12, model: 'small', preview: 'Hola…' },
  ];
  const turns = [
    { start_s: 0, speaker: 'YO', text: 'Buenos días, arrancamos con el punto de vacaciones.' },
    { start_s: 14, speaker: 'OTROS', text: 'Perfecto, yo tengo dos comentarios sobre el plan de acción.' },
    { start_s: 41, speaker: 'YO', text: 'Adelante, los anotamos.' },
  ];
  const models = ['tiny', 'base', 'small', 'medium', 'large-v3-turbo', 'large-v3'].map((n, i) => ({
    name: n, label: n, note: '', size_mb: [75, 148, 488, 1500, 1620, 3100][i], installed: n === 'small' }));
  return {
    async bootstrap() { return { state, model: 'small', models, gpu: 'NVIDIA GeForce RTX 5060 Ti', settings: { theme: 'system', vocabulary: '', hotkey: 'ctrl+shift+r', model: 'small' }, history }; },
    async toggle() {
      if (state === 'idle') {
        state = 'recording'; echo.emit('state', state);
        timer = setInterval(() => echo.emit('levels', { microphone: Math.random() * .6, system: Math.random() * .4 }), 50);
      } else if (state === 'recording') {
        clearInterval(timer); state = 'transcribing'; echo.emit('state', state);
        let p = 0; const t = setInterval(() => { p += 12; echo.emit('progress', Math.min(p, 100)); if (p >= 100) { clearInterval(t); state = 'idle'; echo.emit('state', state); echo.emit('history_changed'); } }, 300);
      }
    },
    async set_model(n) { models.forEach(m => m.installed = m.installed || m.name === n); return models; },
    async download_model(name) { let p = 0; const t = setInterval(() => { p += 20; echo.emit('model_download', { name, pct: p, done: p >= 100, error: null }); if (p >= 100) { clearInterval(t); models.find(m => m.name === name).installed = true; } }, 250); },
    async get_settings() { return {}; },
    async set_settings(p) { return p; },
    async list_devices() { return { inputs: [{ index: 1, name: 'Micrófono (Realtek)' }], loopbacks: [{ index: 5, name: 'Altavoces (Realtek) [Loopback]' }] }; },
    async list_history() { return history; },
    async load_transcript(id) { return { id, meta: history.find(h => h.id === id) || history[0], turns }; },
    async rename() {}, async delete() {}, async export() { return 'ok'; }, async open_folder() {},
  };
})();

export async function api() {
  if (window.pywebview?.api) return window.pywebview.api;
  await new Promise(r => { let n = 0; const t = setInterval(() => { if (window.pywebview?.api || ++n > 20) { clearInterval(t); r(); } }, 50); });
  return window.pywebview?.api || mock;
}
```
- [ ] **Step 2: `ui/js/waveform.js`**
```js
// Rolling bar waveform on a <canvas>; push(level 0..1) per level event.
export class Waveform {
  constructor(canvas, color) {
    this.c = canvas; this.ctx = canvas.getContext('2d'); this.color = color;
    this.bars = new Array(64).fill(0); this.target = 0; this.raf = null;
    this.resize(); new ResizeObserver(() => this.resize()).observe(canvas);
  }
  resize() {
    const r = devicePixelRatio || 1, w = this.c.clientWidth, h = this.c.clientHeight;
    this.c.width = w * r; this.c.height = h * r; this.ctx.setTransform(r, 0, 0, r, 0, 0);
  }
  push(v) { this.target = Math.min(1, Math.sqrt(v) * 1.6); }
  start() { if (!this.raf) { const loop = () => { this.step(); this.raf = requestAnimationFrame(loop); }; loop(); } }
  stop() { cancelAnimationFrame(this.raf); this.raf = null; this.bars.fill(0); this.target = 0; this.draw(); }
  step() { this.bars.shift(); this.bars.push(this.target); this.target *= 0.85; this.draw(); }
  draw() {
    const { ctx, bars } = this, w = this.c.clientWidth, h = this.c.clientHeight;
    ctx.clearRect(0, 0, w, h);
    const gap = 3, bw = (w - gap * (bars.length - 1)) / bars.length;
    ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue(this.color).trim() || '#5b8def';
    bars.forEach((b, i) => {
      const bh = Math.max(3, b * h); const x = i * (bw + gap), y = (h - bh) / 2;
      ctx.beginPath(); ctx.roundRect(x, y, bw, bh, bw / 2); ctx.fill();
    });
  }
}
```
- [ ] **Step 3: `ui/index.html`**
```html
<!doctype html>
<html lang="es" data-theme="system">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AnotaVoz</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="css/app.css">
</head>
<body>
<div class="app">
  <aside class="sidebar">
    <div class="brand"><div class="logo">🎙</div><div><b>AnotaVoz</b><small>Transcripción local</small></div></div>
    <nav>
      <button class="nav active" data-view="record">Grabar</button>
      <button class="nav" data-view="history">Historial</button>
      <button class="nav" data-view="settings">Ajustes</button>
    </nav>
    <div class="chip" id="gpuChip">…</div>
  </aside>
  <main>
    <section id="view-record" class="view active">
      <div class="status"><span class="dot" id="dot"></span><span id="statusText">Cargando…</span><span id="timer"></span></div>
      <div class="hero">
        <button id="recBtn" class="rec" disabled><span class="ring"></span><span class="icon"></span></button>
        <p class="hint">Ctrl+Shift+R también inicia o detiene</p>
      </div>
      <div class="waves">
        <div class="wave"><label>Tú</label><canvas id="waveMic"></canvas></div>
        <div class="wave"><label>Otros</label><canvas id="waveSys"></canvas></div>
      </div>
      <div class="progress" id="progress" hidden><div id="progressBar"></div></div>
      <div id="log" class="log"></div>
      <div id="upgradeBanner" class="banner" hidden>Estás usando un modelo menos preciso. <button id="upgradeBtn" class="btn">Cambiar a “Best” (1.6 GB)</button></div>
    </section>
    <section id="view-history" class="view">
      <header class="bar"><h2>Historial</h2><input id="search" placeholder="Buscar…" type="search"></header>
      <div class="split"><div id="historyList" class="list"></div><div id="transcript" class="transcript"><p class="empty">Elige una grabación</p></div></div>
    </section>
    <section id="view-settings" class="view">
      <header class="bar"><h2>Ajustes</h2></header>
      <div class="card"><h3>Modelo</h3><div id="modelList" class="models"></div></div>
      <div class="card"><h3>Vocabulario</h3><p class="muted">Nombres y siglas que debe reconocer (uno por línea o separados por coma).</p><textarea id="vocab" rows="4"></textarea></div>
      <div class="card"><h3>Tema</h3><select id="theme"><option value="system">Sistema</option><option value="dark">Oscuro</option><option value="light">Claro</option></select></div>
    </section>
  </main>
</div>
<script type="module" src="js/app.js"></script>
</body></html>
```
- [ ] **Step 4: `ui/css/app.css`** (tokens en `:root`, oscuro por defecto, claro por `prefers-color-scheme`/`data-theme`):
```css
:root{--bg:#0b0d12;--panel:#12151c;--panel2:#181c26;--line:#262b38;--text:#e8eaf0;--dim:#8a91a5;--accent:#6c8cff;--accent2:#8b6cff;--rec:#ff4d5a;--ok:#3ecf6e;--warn:#f2a65a;--yo:#6c8cff;--otros:#f2a65a;--r:16px;color-scheme:dark}
:root[data-theme=light]{--bg:#f4f6fb;--panel:#fff;--panel2:#eef1f8;--line:#dfe4ef;--text:#161a24;--dim:#667087;--accent:#4f6dff;--accent2:#7a5cff;color-scheme:light}
@media(prefers-color-scheme:light){:root[data-theme=system]{--bg:#f4f6fb;--panel:#fff;--panel2:#eef1f8;--line:#dfe4ef;--text:#161a24;--dim:#667087;--accent:#4f6dff;--accent2:#7a5cff;color-scheme:light}}
*{box-sizing:border-box}html,body{height:100%;margin:0}
body{font:14px/1.5 Inter,system-ui,sans-serif;background:radial-gradient(1200px 600px at 80% -10%,color-mix(in srgb,var(--accent) 18%,transparent),transparent),var(--bg);color:var(--text)}
.app{display:grid;grid-template-columns:230px 1fr;height:100vh}
.sidebar{background:color-mix(in srgb,var(--panel) 80%,transparent);backdrop-filter:blur(14px);border-right:1px solid var(--line);padding:20px 14px;display:flex;flex-direction:column;gap:18px}
.brand{display:flex;gap:10px;align-items:center}.brand small{display:block;color:var(--dim);font-size:11px}
.logo{width:38px;height:38px;border-radius:11px;display:grid;place-items:center;background:linear-gradient(135deg,var(--accent),var(--accent2));font-size:18px}
nav{display:flex;flex-direction:column;gap:4px}
.nav{background:none;border:0;color:var(--dim);text-align:left;padding:10px 12px;border-radius:10px;font:inherit;font-weight:500;cursor:pointer;transition:.15s}
.nav:hover{background:var(--panel2);color:var(--text)}.nav.active{background:var(--panel2);color:var(--text)}
.chip{margin-top:auto;font-size:12px;color:var(--dim);padding:8px 10px;border:1px solid var(--line);border-radius:10px}
main{overflow:auto;padding:28px 34px}
.view{display:none;animation:in .25s ease}.view.active{display:block}@keyframes in{from{opacity:0;transform:translateY(6px)}}
.status{display:flex;align-items:center;gap:8px;font-weight:600}.dot{width:10px;height:10px;border-radius:50%;background:#e6b800}
.dot.idle{background:var(--ok)}.dot.recording{background:var(--rec);animation:pulse 1.2s infinite}.dot.transcribing{background:var(--warn)}
#timer{color:var(--dim);font-weight:500;font-variant-numeric:tabular-nums;margin-left:6px}
.hero{display:grid;place-items:center;padding:42px 0 18px}
.rec{position:relative;width:132px;height:132px;border-radius:50%;border:0;cursor:pointer;color:#fff;background:linear-gradient(135deg,var(--accent),var(--accent2));box-shadow:0 14px 40px color-mix(in srgb,var(--accent) 45%,transparent);transition:.2s}
.rec:hover:not(:disabled){transform:scale(1.04)}.rec:disabled{opacity:.45;cursor:not-allowed}
.rec .icon{position:absolute;inset:0;margin:auto;width:34px;height:34px;border-radius:50%;background:#fff;transition:.2s}
.rec.recording{background:linear-gradient(135deg,var(--rec),#ff7a59);box-shadow:0 14px 40px color-mix(in srgb,var(--rec) 50%,transparent)}
.rec.recording .icon{border-radius:8px;width:30px;height:30px}
.rec.recording .ring{position:absolute;inset:-10px;border-radius:50%;border:2px solid var(--rec);animation:ring 1.6s infinite}
@keyframes ring{from{opacity:.8;transform:scale(.95)}to{opacity:0;transform:scale(1.25)}}@keyframes pulse{50%{opacity:.4}}
.hint{color:var(--dim);font-size:12px;margin:14px 0 0}
.waves{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:10px}
.wave{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);padding:12px 14px}.wave label{font-size:11px;color:var(--dim);font-weight:600;text-transform:uppercase;letter-spacing:.06em}
.wave canvas{width:100%;height:64px;display:block;margin-top:6px}
#waveMic{--c:var(--yo)}#waveSys{--c:var(--otros)}
.progress{height:6px;background:var(--panel2);border-radius:99px;margin-top:18px;overflow:hidden}.progress div{height:100%;width:0;background:linear-gradient(90deg,var(--accent),var(--accent2));transition:width .3s}
.log{color:var(--dim);font-size:12px;margin-top:12px;min-height:18px}
.banner{margin-top:16px;padding:12px 14px;border-radius:12px;background:color-mix(in srgb,var(--warn) 14%,var(--panel));border:1px solid color-mix(in srgb,var(--warn) 40%,var(--line))}
.btn{background:var(--accent);color:#fff;border:0;border-radius:9px;padding:6px 12px;font:inherit;font-weight:600;cursor:pointer;margin-left:8px}
.bar{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}.bar h2{margin:0}
input,textarea,select{background:var(--panel);border:1px solid var(--line);color:var(--text);border-radius:10px;padding:9px 12px;font:inherit}
textarea{width:100%;resize:vertical}
.split{display:grid;grid-template-columns:300px 1fr;gap:16px;height:calc(100vh - 150px)}
.list,.transcript{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);overflow:auto}
.item{padding:12px 14px;border-bottom:1px solid var(--line);cursor:pointer;transition:.12s}.item:hover,.item.active{background:var(--panel2)}
.item b{display:block}.item small{color:var(--dim)}.item p{margin:4px 0 0;color:var(--dim);font-size:12px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.transcript{padding:18px}.empty{color:var(--dim);text-align:center;margin-top:30%}
.turn{display:flex;margin:0 0 14px}.turn.YO{justify-content:flex-end}
.bubble{max-width:78%;padding:10px 14px;border-radius:16px;background:var(--panel2);border:1px solid var(--line)}
.turn.YO .bubble{background:color-mix(in srgb,var(--yo) 16%,var(--panel));border-color:color-mix(in srgb,var(--yo) 40%,var(--line))}
.turn.OTROS .bubble{background:color-mix(in srgb,var(--otros) 12%,var(--panel))}
.bubble small{display:block;color:var(--dim);font-size:11px;margin-bottom:2px;font-weight:600}
mark{background:color-mix(in srgb,var(--warn) 55%,transparent);color:inherit;border-radius:3px}
.tools{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap}.tools button{background:var(--panel2);border:1px solid var(--line);color:var(--text);border-radius:9px;padding:6px 10px;cursor:pointer;font:inherit}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);padding:16px 18px;margin-bottom:14px}.card h3{margin:0 0 10px}.muted{color:var(--dim);margin:0 0 8px}
.models{display:grid;gap:8px}.model{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:10px 12px;border:1px solid var(--line);border-radius:12px}
.model.sel{border-color:var(--accent);background:color-mix(in srgb,var(--accent) 10%,transparent)}
.model .bar2{height:4px;background:var(--panel2);border-radius:9px;margin-top:6px;overflow:hidden}.model .bar2 i{display:block;height:100%;background:var(--accent);width:0}
@media(max-width:820px){.app{grid-template-columns:1fr}.sidebar{flex-direction:row;align-items:center;padding:10px}nav{flex-direction:row}.chip{display:none}.waves,.split{grid-template-columns:1fr}main{padding:18px}}
```
La waveform lee `--c` vía el color: en `waveform.js` pasar `'--yo'`/`'--otros'` (ya contemplado en el constructor).
- [ ] **Step 5: `ui/js/app.js`**
```js
import { api } from './bridge.js';
import { Waveform } from './waveform.js';

const $ = s => document.querySelector(s);
const STATE = { loading: 'Cargando modelo…', idle: 'Listo', recording: 'Grabando', transcribing: 'Transcribiendo…' };
let A, state = 'loading', startedAt = null, current = null, models = [], selected = '';

const mic = new Waveform($('#waveMic'), '--yo');
const sys = new Waveform($('#waveSys'), '--otros');

function setState(s) {
  state = s;
  $('#statusText').textContent = STATE[s] || s;
  $('#dot').className = 'dot ' + s;
  const btn = $('#recBtn');
  btn.disabled = s === 'loading' || s === 'transcribing';
  btn.classList.toggle('recording', s === 'recording');
  $('#progress').hidden = s !== 'transcribing';
  if (s === 'recording') { startedAt = Date.now(); mic.start(); sys.start(); }
  else { startedAt = null; $('#timer').textContent = ''; mic.stop(); sys.stop(); }
  if (s === 'transcribing') $('#progressBar').style.width = '0%';
}

setInterval(() => {
  if (!startedAt) return;
  const s = Math.floor((Date.now() - startedAt) / 1000);
  $('#timer').textContent = `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
}, 500);

const fmt = s => `${String(Math.floor(s / 3600)).padStart(2, '0')}:${String(Math.floor(s % 3600 / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
const esc = t => t.replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function showView(name) {
  document.querySelectorAll('.view').forEach(v => v.classList.toggle('active', v.id === 'view-' + name));
  document.querySelectorAll('.nav').forEach(n => n.classList.toggle('active', n.dataset.view === name));
  if (name === 'history') loadHistory();
  if (name === 'settings') renderModels();
}
document.querySelectorAll('.nav').forEach(n => n.onclick = () => showView(n.dataset.view));

async function loadHistory() {
  const items = await A.list_history();
  const q = $('#search').value.trim().toLowerCase();
  const shown = items.filter(i => !q || (i.name + ' ' + i.preview).toLowerCase().includes(q));
  $('#historyList').innerHTML = shown.map(i => `
    <div class="item ${i.id === current ? 'active' : ''}" data-id="${esc(i.id)}">
      <b>${esc(i.name)}</b><small>${esc(i.id.replace('_', ' ').replace(/-/g, (m, o) => o > 10 ? ':' : '-'))} · ${Math.round(i.duration_s / 60) || '<1'} min</small>
      <p>${esc(i.preview || '')}</p></div>`).join('') || '<p class="empty">Sin grabaciones</p>';
  document.querySelectorAll('.item').forEach(el => el.onclick = () => openTranscript(el.dataset.id));
}

async function openTranscript(id) {
  current = id;
  const d = await A.load_transcript(id);
  if (d.error) { $('#transcript').innerHTML = `<p class="empty">${esc(d.error)}</p>`; return; }
  const q = $('#search').value.trim();
  const hl = t => q ? esc(t).replace(new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi'), m => `<mark>${m}</mark>`) : esc(t);
  $('#transcript').innerHTML = `
    <div class="tools">
      <button data-a="copy">Copiar</button><button data-a="txt">TXT</button><button data-a="md">MD</button>
      <button data-a="srt">SRT</button><button data-a="folder">Abrir carpeta</button>
      <button data-a="rename">Renombrar</button><button data-a="delete">Borrar</button></div>` +
    d.turns.map(t => `<div class="turn ${t.speaker}"><div class="bubble"><small>${t.speaker === 'YO' ? 'Tú' : 'Otros'} · ${fmt(t.start_s)}</small>${hl(t.text)}</div></div>`).join('');
  $('#transcript').querySelectorAll('.tools button').forEach(b => b.onclick = () => toolAction(b.dataset.a, d));
  loadHistory();
}

async function toolAction(a, d) {
  if (a === 'copy') await navigator.clipboard.writeText(d.turns.map(t => `[${fmt(t.start_s)}] ${t.speaker === 'YO' ? 'Tú' : 'Otros'}: ${t.text}`).join('\n'));
  else if (a === 'folder') A.open_folder(d.id);
  else if (a === 'rename') { const n = prompt('Nombre', d.meta.name); if (n) { await A.rename(d.id, n); loadHistory(); } }
  else if (a === 'delete') { if (confirm('¿Borrar esta grabación?')) { await A.delete(d.id); current = null; $('#transcript').innerHTML = '<p class="empty">Elige una grabación</p>'; loadHistory(); } }
  else { const p = await A.export(d.id, a); $('#log').textContent = p.error || `Exportado: ${p}`; }
}
$('#search').oninput = () => { loadHistory(); if (current) openTranscript(current); };

function renderModels() {
  $('#modelList').innerHTML = models.map(m => `
    <div class="model ${m.name === selected ? 'sel' : ''}" data-n="${m.name}">
      <div><b>${m.label}</b> <small class="muted">${m.name} · ${m.size_mb} MB ${m.note ? '· ' + m.note : ''}</small>
      <div class="bar2" ${m.installed ? 'hidden' : ''}><i id="dl-${m.name}"></i></div></div>
      <button class="btn">${m.name === selected ? 'En uso' : m.installed ? 'Usar' : 'Descargar'}</button></div>`).join('');
  document.querySelectorAll('.model').forEach(el => el.querySelector('button').onclick = async () => {
    const n = el.dataset.n, m = models.find(x => x.name === n);
    if (m.installed) { models = await A.set_model(n); selected = n; renderModels(); checkUpgrade(); }
    else A.download_model(n);
  });
}

function checkUpgrade() {
  const weak = ['tiny', 'base', 'small'].includes(selected);
  $('#upgradeBanner').hidden = !weak;
}
$('#upgradeBtn').onclick = async () => {
  const best = models.find(m => m.name === 'large-v3-turbo');
  if (best.installed) { models = await A.set_model(best.name); selected = best.name; checkUpgrade(); }
  else { A.download_model(best.name); $('#log').textContent = 'Descargando modelo…'; }
};

window.echo.on('state', setState);
window.echo.on('log', m => $('#log').textContent = m);
window.echo.on('levels', l => { mic.push(l.microphone); sys.push(l.system); });
window.echo.on('progress', p => $('#progressBar').style.width = p + '%');
window.echo.on('history_changed', () => { if ($('#view-history').classList.contains('active')) loadHistory(); });
window.echo.on('model_download', e => {
  const bar = $('#dl-' + e.name); if (bar) bar.style.width = e.pct + '%';
  $('#log').textContent = e.error ? `Error de descarga: ${e.error}` : e.done ? 'Modelo descargado' : `Descargando ${e.name}… ${Math.round(e.pct)}%`;
  if (e.done) { const m = models.find(x => x.name === e.name); if (m) m.installed = true; renderModels(); }
});

$('#recBtn').onclick = () => A.toggle();
$('#theme').onchange = e => { document.documentElement.dataset.theme = e.target.value; A.set_settings({ theme: e.target.value }); };
$('#vocab').onchange = e => A.set_settings({ vocabulary: e.target.value });

(async () => {
  A = await api();
  const b = await A.bootstrap();
  models = b.models; selected = b.model;
  $('#gpuChip').textContent = b.gpu ? `⚡ ${b.gpu}` : 'CPU (sin GPU)';
  $('#vocab').value = b.settings.vocabulary || '';
  $('#theme').value = b.settings.theme || 'system';
  document.documentElement.dataset.theme = b.settings.theme || 'system';
  setState(b.state);
  checkUpgrade();
})();
```
- [ ] **Step 6: Verificación visual:** abrir `ui/index.html` en el navegador integrado (`file://`), recorrer Grabar (mock: nivel, estados), Historial, Ajustes en oscuro/claro y a 700 px de ancho; capturar pantallas; corregir desbordes. Verificar sin errores en consola.
- [ ] **Step 7: Checkpoint:** `pytest -q` verde.

---

### Task 12: Verificación end-to-end, binario/VAD y documentación

**Files:**
- Modify: `docs/DECISIONS.md` (ADR-012, ADR-013), `README.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md` si aplica
- Possible: `core/whisper/*` (solo si pasa el criterio)

- [ ] **Step 1: Prueba en vivo:** `run_gui.bat` → ventana abre, estado pasa a Listo, Grabar 20-30 s hablando con algo sonando en parlantes, Detener, transcripción aparece en Historial, sin duplicado mic/sistema.
- [ ] **Step 2: Modelo grande:** desde Ajustes/banner descargar `large-v3-turbo` (reanuda `.part`), seleccionarlo, repetir una grabación y comparar contra la de `small` con el banco (Task 6).
- [ ] **Step 3: Binario y VAD (condicional):** copiar `core/whisper` a `core/whisper.bak`; obtener una build reciente de whisper.cpp con soporte Vulkan; reemplazar; verificar `--help` (backends, flags) y que `gpu_backend()` sigue detectando la GPU. Probar VAD sobre `recordings/2026-09-21_14-27-54/microphone.wav`: aceptar solo si la duración conservada ≥ 95 %; si no, restaurar `core/whisper.bak` o dejar VAD desactivado. Registrar resultado.
- [ ] **Step 4: Banco final:** correr `tools/bench_transcribe.py`; anotar WER por configuración.
- [ ] **Step 5: Docs:** ADR-012 (decisiones y resultados del banco), ADR-013 (GUI web reemplaza ADR-010), README (Quickstart, estructura, estado), ARCHITECTURE (diagrama con `audio_prep`/`postproc`/`api`).
- [ ] **Step 6: Cierre:** `pytest -q` verde; `main.py` y `app/tray.py` siguen arrancando (`python -c "import main, app.tray"`); apertura/cierre de la GUI sin procesos colgados (`tasklist` sin `whisper-cli`/`python` huérfanos).

---

## Self-Review

- **Cobertura del spec:** A1 → Task 12 paso 2 + Task 8 (`download_model`) + banner Task 11; A2 → Task 2/5; A3 → Task 1/5; A4 → Task 3; A5 → Task 12 paso 3; A6 → Task 1/5; A7 → Task 6; B1 → Task 10; B2 → Tasks 4, 5, 7, 8; B3/B4 → Task 11; errores (WebView2 ausente): añadir en Task 10 `webgui.main()` un `try/except` alrededor de `webview.start()` que en fallo imprima el error y lance `app.tray` como respaldo. Este paso se ejecuta junto con el Step 4 de Task 10.
- **Placeholders:** ninguno; cada paso de código incluye el código.
- **Consistencia de tipos:** `RecordingSession(..., vocabulary, level_cb, progress_cb)` (Task 5) coincide con el uso en Task 8; `CaptureSession(level_cb=...)` (Task 7) coincide con Task 5 paso 4; `Api` usa `controller.state/has_model/download_model/set_model/toggle/start/shutdown/model_name`, todos definidos en Task 8; eventos de Task 10 coinciden con los `echo.on` de Task 11.
- **Review Focus:** eco total (Task 1/5 tests), WAV vacío (Task 2), prompt raro (Task 3), config corrupta (Task 4), historial roto (Task 9), cierre de ventana (Task 10 `closing` → `_shutdown`, verificado en Task 12 paso 6).
