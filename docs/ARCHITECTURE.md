# Arquitectura

## Componentes

```text
┌─────────────┐   hotkey    ┌──────────────────┐
│  TrayApp     │────────────►│  CaptureSession  │
│  (Fase 3)    │◄────state───│  (app/capture.py)│
└─────────────┘             └────────┬─────────┘
                                      │ start()/stop()
                    ┌─────────────────┼─────────────────┐
                    ▼                                   ▼
          ┌───────────────────┐               ┌───────────────────┐
          │ StreamRecorder     │               │ StreamRecorder     │
          │ (mic, WASAPI)      │               │ (system, loopback) │
          └─────────┬──────────┘               └─────────┬──────────┘
                    ▼                                     ▼
            microphone.wav                          system.wav
                    │                                     │
                    └───────────────┬─────────────────────┘
                                     ▼
                          ┌───────────────────┐
                          │ Transcriber        │  (ya portado, app/transcriber.py)
                          │ (whisper.cpp x2)    │
                          └─────────┬───────────┘
                                     ▼
                          ┌───────────────────┐
                          │ merge_transcripts() │  por timestamp
                          └─────────┬───────────┘
                                     ▼
                              transcript.txt
```

## Módulos

- **`app/devices.py`** — enumera dispositivos WASAPI (mic + loopback del
  speaker default) vía `PyAudioWPatch`. Expone `default_mic()` y
  `default_loopback()`; selección explícita queda para Fase 4, pero la
  función ya devuelve objetos con `index`/`name` para no reescribir la API
  cuando se agregue el selector.
- **`app/capture.py`** — `StreamRecorder`: abre un stream PyAudio en modo
  callback (no polling por bloques como el prototipo) y escribe frames
  crudos directo a un `.wav` vía el módulo `wave` de la stdlib, incremental
  (no acumula todo en memoria). `CaptureSession` arranca los dos
  `StreamRecorder` (mic + loopback) casi simultáneamente y devuelve las
  rutas de los dos WAV al parar.
- **`app/transcriber.py`** *(ya portado)* — corre whisper.cpp sobre un WAV,
  devuelve cues con timestamps.
- **`app/session.py`** — `RecordingSession`, un ciclo hotkey-toggle: crea
  `recordings/<timestamp>/`, llama `CaptureSession`, luego `Transcriber`
  sobre cada pista por separado (una pista sin voz no aborta la otra),
  `merge_transcripts()` intercala por timestamp con tags `[YO]` / `[OTROS]`,
  escribe `transcript.txt`.
- **`app/controller.py`** — `RecordingController`: la máquina de estados
  (`loading → idle → recording → transcribing → idle`) y el hotkey global,
  compartidos entre los dos front-ends de abajo para no duplicar el gate
  `model_ready` (ADR-005).
- **`main.py`** (Fase 2) — front-end de consola sobre `RecordingController`.
- **`app/tray.py`** (Fase 3) — front-end de bandeja sobre el mismo
  `RecordingController`: color de ícono por estado, notificación al
  terminar, cierre ordenado (unhook antes de `icon.stop()`, sin `os._exit`).

## Concurrencia

PyAudioWPatch usa streams por **callback**, no por polling (`stream.read()`
en loop como el prototipo, que desfasaba mic/sistema por el tiempo que tarda
cada `.record()` bloqueante). El callback de audio corre en un thread nativo
de PortAudio; cada `StreamRecorder` solo escribe los frames que recibe a su
propio WAV — no hay mezcla, no hay estado compartido entre mic y sistema
salvo el instante de `start()`.

Sincronía: los dos streams se abren (`open()`) antes de que cualquiera
empiece a recibir callbacks, y se arrancan en la misma línea. El desfase
esperado es del orden de microsegundos (dos llamadas Python consecutivas),
muy por debajo de lo que importa para transcripción. Se valida en Fase 1
con una prueba de aplauso simultáneo grabado por las dos fuentes.

## Estado y errores

```text
idle ──(modelo cargando)──► loading ──(modelo listo)──► ready
ready ──(hotkey)──► recording ──(hotkey)──► transcribing ──► ready
```

- Hotkey ignorado mientras `state != ready` fuera de `recording` (ver
  ADR-005) — evita transcribir con modelo `None`.
- Si no se encuentra el dispositivo de loopback: error explícito, no
  silencioso (el prototipo solo hacía `print` y `return`).
- Si `whisper-cli` no está (ver `app/binaries.py`): se avisa al arrancar, no
  a mitad de grabación; `tools/setup_binaries.py` lo instala y verifica
  contra `core/whisper/MANIFEST.json`. `ffmpeg` se baja solo si falta.

## Layout de archivos por sesión

```text
recordings/2026-09-21_14-30-00/
├── microphone.wav
├── system.wav
└── transcript.txt
```

## Decisiones que fija esta arquitectura

- ADR-003 resuelto: **PyAudioWPatch** (confirmado, wheel cp314 disponible,
  instalado en `.venv`). Da loopback por índice de dispositivo, no por
  match de nombre de string.
- Escritura de WAV incremental (stream → disco), no acumular en listas de
  numpy arrays como el prototipo — evita picos de memoria en grabaciones
  largas y no necesita `numpy`/`soundfile` para la etapa de captura.
