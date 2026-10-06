# EchoNote

Grabadora y transcriptor universal para Windows. Captura micrófono + audio del
sistema (WASAPI loopback) en segundo plano, sin integrarse con ninguna app
específica (Teams, Discord, Zoom, YouTube, juegos...), y transcribe todo
localmente y offline.

## Por qué

Reuniones y llamadas pasan por decenas de apps distintas. En vez de construir
un plugin por cada una, EchoNote captura a nivel de sistema operativo:

```text
Teams / Discord / Zoom / YouTube / Juegos
                │
                ▼
        Audio del sistema (WASAPI loopback)
                │
Micrófono ──────┼──────► Capturador (pistas separadas)
                │
                ▼
        Whisper (local, offline)
                │
                ▼
          transcript.txt
```

No requiere plugins, bots, captura de pantalla, inyección en procesos, ni
dispositivos de audio virtuales. Es "Windows → capturar audio → transcribir".

## Principios de diseño

- **No invasiva**: cero integración por-app. Todo a nivel de SO.
- **Pistas separadas**: micrófono y sistema se graban y transcriben por
  separado, nunca mezclados antes de Whisper (ver [docs/DECISIONS.md](docs/DECISIONS.md#adr-002)).
- **Offline / local**: sin llamadas a APIs externas de transcripción.
- **Invisible por defecto**: vive en la bandeja del sistema, hotkey global.
- **Ligera por defecto**: modelo `small` en CPU; el modelo grande y la GPU
  son opt-in.
- **Tres front-ends, un solo cerebro**: consola, bandeja y GUI web (pywebview)
  comparten `app/controller.py` — nada de lógica duplicada por interfaz.

## Instalar en otra PC

Requisitos: Windows 10/11 x64, [Python 3.10+](https://python.org) y
[Git](https://git-scm.com) (o bajar el ZIP del repo). No hace falta admin.

```bat
git clone https://github.com/DesvoSoft/EchoNote.git
cd EchoNote
run_gui.bat
```

El primer arranque se prepara solo (una única vez, necesita internet):

1. crea `.venv` e instala [`requirements.txt`](requirements.txt);
2. baja el motor whisper.cpp fijado en
   [`core/whisper/MANIFEST.json`](core/whisper/MANIFEST.json) (~8 MB) y
   verifica cada archivo por SHA-256 ([`tools/setup_binaries.py`](tools/setup_binaries.py));
3. baja `ffmpeg` (~115 MB) a `core/`;
4. baja el modelo `small` (~488 MB) a `%APPDATA%/EchoNote/models/`.

Después de eso funciona 100% offline.

### Modo ligero (default) y modo GPU

Una instalación nueva arranca en **modo ligero**: modelo `small`, solo CPU,
sin descargas de más de 500 MB. Es lo que conviene en una laptop de trabajo
sin GPU dedicada (ver [ADR-014](docs/DECISIONS.md#adr-014--modo-ligero-por-default)).

Si la máquina tiene GPU con Vulkan (NVIDIA/AMD/Intel reciente):

```bat
.venv\Scripts\python.exe tools\setup_binaries.py --gpu
```

y en *Ajustes → Modelo* elegí **Best** (`large-v3-turbo`, 1.6 GB). La GUI lo
sugiere sola cuando detecta la GPU.

### Sin acceso a GitHub / red restringida

Bajá en otra máquina
[`whisper-bin-x64.zip`](https://github.com/ggml-org/whisper.cpp/releases/tag/v1.9.2)
y pasalo por USB:

```bat
.venv\Scripts\python.exe tools\setup_binaries.py --whisper-zip whisper-bin-x64.zip
```

Si ya hay un `ffmpeg` en el `PATH` se usa ese. Los modelos son archivos
`ggml-*.bin` sueltos: se pueden copiar a mano a `%APPDATA%/EchoNote/models/`.

## Uso

Doble click en uno de:

- [`run_gui.bat`](run_gui.bat) — ventana con botón grabar, ondas en vivo,
  historial con búsqueda/exportar y ajustes (recomendado)
- [`run.bat`](run.bat) — solo bandeja del sistema
- [`run_console.bat`](run_console.bat) — consola, logs en vivo; pregunta el
  modelo la primera vez

`Ctrl+Shift+R` arranca/detiene la grabación en las tres interfaces. Al
detener, transcribe y escribe en `recordings/<fecha>/`: `transcript.txt`
(turnos `YO`/`OTROS` con timestamps), `microphone.wav`, `system.wav` y el
`.txt`/`.srt` de cada pista. Las grabaciones nunca salen de la máquina y
`recordings/` está fuera de git.

Ajustes en `%APPDATA%/EchoNote/config.json` (modelo, vocabulario, tema,
hotkey). Solo corre una instancia a la vez. El idioma de transcripción está
fijo en español (`LANG` en [`app/session.py`](app/session.py)).

## Estructura

```text
EchoNote/
├── app/        # captura, transcripción, controlador, front-ends
├── ui/         # GUI web (HTML/CSS/JS sin build) que abre pywebview
├── core/       # binarios (ffmpeg, whisper.cpp) — fuera de git, solo el MANIFEST
├── tools/      # setup_binaries, descarga de modelos, benchmarks, pruebas manuales
├── tests/      # pytest
├── docs/       # roadmap, decisiones (ADR), arquitectura
├── legacy/     # prototipo original, notas de diseño y la GUI CustomTkinter anterior
└── run*.bat    # launchers (comparten _bootstrap.bat)
```

Módulos principales:

- [`app/controller.py`](app/controller.py) — máquina de estados + hotkey
  global, compartida por los tres front-ends
- [`app/capture.py`](app/capture.py), [`app/devices.py`](app/devices.py) —
  mic + loopback WASAPI en paralelo, pistas separadas (ADR-002, ADR-007)
- [`app/session.py`](app/session.py) — un ciclo grabar → transcribir → merge
- [`app/transcriber.py`](app/transcriber.py), [`app/binaries.py`](app/binaries.py)
  *(portados de Y2oby)* — motor whisper.cpp, modelos, probe de GPU
- [`app/audio_prep.py`](app/audio_prep.py), [`app/postproc.py`](app/postproc.py) —
  preprocesado, anti-eco y limpieza de bucles (ADR-012)
- [`app/webgui.py`](app/webgui.py) + [`app/api.py`](app/api.py),
  [`app/tray.py`](app/tray.py), [`main.py`](main.py) — GUI, bandeja, consola

## Desarrollo

```bat
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest -q
```

- [docs/ROADMAP.md](docs/ROADMAP.md) — fases y pendientes
- [docs/DECISIONS.md](docs/DECISIONS.md) — decisiones de diseño y por qué
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — arquitectura técnica

## Stack

| Parte            | Tecnología                                   |
|------------------|----------------------------------------------|
| Captura          | PyAudioWPatch (WASAPI + loopback)            |
| Transcripción    | whisper.cpp (CPU; Vulkan opcional)           |
| Audio            | ffmpeg (normalización), WAV por pista        |
| GUI              | pywebview (WebView2) + HTML/CSS/JS           |
| Bandeja / hotkey | `pystray` / `keyboard`                       |
