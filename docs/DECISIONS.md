# Decisiones de diseño

Log corto tipo ADR. Cada entrada: decisión, por qué, alternativa descartada.
Se actualiza según avanza el roadmap.

## ADR-001 — Motor de transcripción: whisper.cpp (portado de Y2oby), no faster-whisper

El prototipo original (`Qwen_python_*.py`) usaba `faster-whisper`. Y2oby ya
tiene un wrapper de whisper.cpp probado en producción con:

- chunking de 600s/8s overlap para evitar el loop de alucinación de Whisper
  en audio largo continuo
- probe de backend GPU en runtime (Vulkan/CUDA/CPU) sin hardcodear hardware
- descarga y verificación de modelos con resume
- detección de líneas repetidas (loops) post-transcripción

Reusar esto evita rehacer ese trabajo y reduce dependencias Python pesadas
(no se necesita el paquete `faster-whisper` ni su runtime CTranslate2).

**Alternativa descartada**: `faster-whisper` (Python, CTranslate2) — más
simple de integrar pero sin el chunking anti-alucinación ni el manejo de
GPU/modelos ya resuelto.

## ADR-002 — No mezclar pistas mic + sistema antes de transcribir

El prototipo mezclaba `sys_audio * 0.7 + mic_audio * 0.3` antes de pasar a
Whisper. Eso pierde la separación de quién dijo qué, y el peso 0.7/0.3 es
arbitrario (se rompe si el nivel de entrada de alguna fuente es distinto al
de prueba).

Decisión: guardar y transcribir `microphone.wav` y `system.wav` por
separado, y unir cronológicamente después con tags (`[YO]` / `[OTROS]`).
Abre la puerta a diarización real más adelante sin rehacer la captura.

## ADR-003 — Captura de audio: evaluar `PyAudioWPatch` sobre `soundcard`

El prototipo usa `soundcard`, que localiza el loopback por nombre
(`default_speaker.name in m.name`) — frágil entre configuraciones de
Windows. `PyAudioWPatch` está hecho específicamente para WASAPI loopback en
Windows.

Estado: **propuesto, no confirmado**. Se decide en la fase de arquitectura
(Fase 1 del roadmap) tras validar sincronización de streams paralelos con
cada opción.

## ADR-004 — Hotkey: `keyboard` lib para MVP, `RegisterHotKey`/ctypes después

`keyboard` es suficiente y rápido de integrar para el MVP. Para una app
distribuible, `RegisterHotKey` vía `ctypes` da integración más nativa y
elimina una dependencia — pero no es prioridad hasta Fase 5.

## ADR-005 — Modelo debe estar listo antes de aceptar el hotkey

El prototipo carga el modelo Whisper en un thread de fondo pero no bloquea
el hotkey mientras carga — un `Ctrl+Shift+R` temprano puede intentar
transcribir con `whisper_model is None` y fallar.

Decisión: estado explícito `model_ready`; hotkey ignorado (o icono muestra
"🟡 Cargando modelo...") hasta que el modelo esté cargado.

## ADR-007 — Loopback necesita un stream de salida "keep-alive"

Verificado empíricamente (`tools/test_capture.py` vs `tools/test_capture_with_tone.py`):
grabar loopback durante silencio real da **0 frames**; la misma grabación con
un tono sonando da la duración completa. Windows suspende el render
endpoint WASAPI tras un rato sin nada que reproducir, y el loopback no
entrega callbacks si el endpoint está inactivo — no es un bug de
`PyAudioWPatch`, es el comportamiento del audio engine.

Decisión: `CaptureSession` abre un stream de salida silencioso
(`_KeepAliveOutput` en `app/capture.py`) hacia el dispositivo de salida
default, activo durante toda la grabación, para mantener el endpoint
despierto. Sin esto, cualquier pausa de silencio en una reunión real
(algo frecuente) perdería audio del sistema.

Confirmado con el fix: mic 3.968s vs sistema 4.075s en una grabación de 4s
en silencio real — ambas pistas completas, desfase de ~100ms atribuible a
latencia de arranque de cada driver, no a pérdida de frames.

## ADR-008 — Selección de modelo persistida, default liviano

`run.bat` bajaba `large-v3-turbo` (~1.6GB) a ciegas en el primer run — nadie
lo pidió, y es descarga grande sin forma de evitarla. Además, correr
`run.bat` y `run_console.bat` a la vez (fácil de hacer sin querer con una
tray app, que no muestra ventana propia) hace que dos procesos escriban al
mismo `.part` a la vez.

Decisión:
- `app/config.py` persiste el modelo elegido en `%APPDATA%/AnotaVoz/config.json`.
- Sin elección previa, el default es `small` (~488MB, "good, faster" según
  `MODEL_LABELS`), no `large-v3-turbo`.
- `main.py` pregunta una vez por consola (`choose_model_console`) si no hay
  config; `app/tray.py` no bloquea con un prompt — arranca en `small` y
  expone un submenú "Model" (radio, un ítem por modelo de `transcriber.MODELS`)
  para cambiarlo cuando se quiera.
- `app/single_instance.py` — mutex de Windows (`CreateMutexW`) al arrancar;
  una segunda instancia se niega a correr en vez de competir por el mismo
  hotkey y el mismo archivo de descarga. Verificado: segunda llamada a
  `acquire()` devuelve `False`.

## ADR-009 — Saltar whisper en silencio digital, no confiar en `-nth`

Diagnosticado sobre una grabación real del usuario: el track `system.wav`
(3 min, nada sonando por parlantes durante esa reunión) salió transcrito
como `you` repetido 7 veces — la alucinación clásica de Whisper ante
silencio total, no un error de idioma.

Probado y descartado: subir el rigor de `-nth`/`--no-speech-thold` (0.6 →
0.4) sobre el mismo audio real no cambió el resultado — Whisper decodifica
"you" con confianza alta, así que ningún umbral de "probabilidad de no-habla"
lo iba a filtrar.

Medido: `wav_peak_amplitude()` (nuevo, en `app/transcriber.py`) da pico 1/32767
en ese `system.wav` — silencio digital real, no solo audio bajo. El mismo
`microphone.wav` (habla real) da pico 6578/32767.

Decisión: `app/session.py` calcula el pico de cada track *antes* de invocar
whisper; por debajo de `SILENCE_PEAK = 80` se salta la transcripción
directamente (mismo camino que "no se detectó voz"), sin gastar cómputo ni
arriesgar alucinación. `-nth` en 0.4 queda como red de seguridad secundaria
para tracks con habla real intercalada con silencios largos, no como fix
principal.

Regenerado con el fix: la grabación real del usuario
(`recordings/2026-09-21_14-27-54/`) — `system` ahora se omite limpio,
`microphone` sale en un solo párrafo por turno (ver ADR-002/formato abajo)
en vez de línea por línea.

Pendiente si vuelve a aparecer: bundlear un modelo VAD real de whisper.cpp
(`--vad`) en vez de este umbral de pico — más robusto para silencio parcial
dentro de un mismo track, pero requiere sumar un binario más a `core/`.

## ADR-010 — GUI: CustomTkinter, no la web UI de Y2oby

Y2oby ya tiene una UI web pulida (`desktop/index.html` + vitra.css) que se
podría reusar vía servidor local + pywebview. El usuario eligió
CustomTkinter en su lugar: nativo, sin servidor de por medio, se integra
directo con `RecordingController` sin una tercera pieza (server.py) que
mantener. Trade-off aceptado: menos pulido visual que un sistema de diseño
propio, pero mucho menos superficie nueva.

`app/gui.py` es un tercer front-end sobre el mismo `RecordingController`
(igual que `main.py` y `app/tray.py`): botón grabar/detener con color por
estado, selector de modelo con tamaño/nota de calidad, panel de
transcripción con historial de grabaciones anteriores. Callbacks del
controller llegan desde threads de fondo; se pasan por una `queue.Queue` y
se drenan con `after()` en el thread de Tk — tocar widgets desde otro
thread no es seguro en Tkinter.

## ADR-011 — GPU real, idioma fijo, VAD probado y descartado (por ahora)

El usuario reportó que la precisión seguía "super imprecisa" incluso
después de ADR-009. Investigación + benchmarking sobre la misma grabación
real (`recordings/2026-09-21_14-27-54/`):

**GPU nunca se activaba.** `Transcriber.transcribe()` siempre tenía
`use_gpu=False` por default y `app/session.py` nunca lo pasaba — corría
100% CPU pese a que la máquina tiene una NVIDIA RTX 5060 Ti con backend
Vulkan detectado (`transcriber.gpu_backend()` ya existía, nunca se llamaba
desde `session.py`). Fix: `session.py` detecta el backend GPU y lo pasa a
cada `engine.transcribe()`. No cambia precisión por sí solo (mismos pesos
del modelo), pero saca la excusa de tiempo para usar un modelo más grande —
"small" pasó a transcribir un clip de 3 min en ~9s con GPU.

**Idioma fijo a `es`.** Estaba en `lang="auto"` — sin motivo, ya que el uso
real de esta app es 100% español. Auto-detección por chunk es una apuesta
que solo puede restar precisión cuando el idioma nunca estuvo en duda.

**Modelo default subido a `large-v3-turbo`.** Con GPU quitando la excusa de
tiempo, el único costo real de un modelo grande es la descarga (una sola
vez). `FALLBACK_MODEL` en `app/controller.py` pasa de `small` a
`large-v3-turbo` — instalaciones nuevas lo usan directo; el `small` que ya
tenías configurado en `config.json` no se toca solo, lo cambiás vos desde
el dropdown.

**VAD (Silero, vía `--vad` de whisper.cpp) — probado y descartado por
ahora.** La investigación (ver fuentes abajo) señala VAD como el fix
correcto para reducir alucinaciones más allá del caso de silencio total ya
cubierto por ADR-009. Se implementó completo: descarga del modelo
(`ggml-silero-v6.2.0.bin` desde `ggml-org/whisper-vad` en HuggingFace),
flags `--vad -vm <path>` en `_run_chunk`. Probado sobre el mismo
`microphone.wav` real (181s de habla continua real):

```
whisper_vad: Reduced audio from 2903041 to 20960 samples (99.3% reduction)
[00:02:39.680 --> 00:02:40.990]   de una persona otra.
```

VAD clasificó el 99.3% de habla real como no-habla y dejó un único
segmento de 1.3s — el resultado fue peor que sin VAD (una alucinación en
vez de una transcripción completa y correcta). No se pudo aislar si es un
problema de versión del modelo (6.2.0) contra este build de `whisper-cli`
portado de Y2oby, threshold, o un bug del lado de whisper.cpp. La
plantería queda en el código (`Transcriber.ensure_vad_model`,
`vad_model_path` en `transcribe()`) pero **`app/session.py` pasa
`vad_model_path=None` siempre** — no se usa hasta confirmar una
combinación binario+modelo que funcione.

Pendiente si se retoma: recompilar/actualizar `whisper-cli.exe` a una
versión más reciente de whisper.cpp, o probar otra versión del modelo VAD,
antes de volver a intentar.

Fuentes consultadas:
- [whisper.cpp VAD model source (ggml-org/whisper-vad)](https://huggingface.co/ggml-org/whisper-vad)
- [whisper : add Silero VAD built-in support (whisper.cpp#3003)](https://github.com/ggml-org/whisper.cpp/issues/3003)
- Comparación de modelos STT open source 2026 (Whisper large-v3 sigue entre
  los mejores para español; NVIDIA Canary/IBM Granite lideran en inglés)

## ADR-006 — Sin GUI hasta que el core sea sólido

Interfaz gráfica se pospone hasta que `hotkey → grabar → hotkey →
transcribir` funcione de forma confiable (fin de Fase 2). Evita construir UI
sobre una base de captura/transcripción que todavía puede cambiar.

## ADR-012 — Mejoras de calidad: modelo grande real, preprocesado, anti-eco, bucles

Diagnóstico (2026-10-01): `config.json` seguía en `small` porque la descarga de
`large-v3-turbo` había quedado en `.part`; ADR-011 asumía el modelo grande.
Se completó la descarga (`tools/download_model.py`) y el modelo activo es ahora
`large-v3-turbo`.

Medido sobre `recordings/2026-09-21_14-27-54/microphone.wav` (181 s, GPU Vulkan):
`small` → "organismos colegiados / coquita / AMQ", `large-v3-turbo` → "órganos
colegiados / cosita / cédula", y ~6 s de cómputo por 3 min de audio.

- `app/audio_prep.py`: highpass 80 Hz + `loudnorm` (mic), `loudnorm` (sistema).
  **`afftdn` (denoise) se probó y se retiró**: cambió "actas" por "aptas".
  El preprocesado recupera habla baja (403 vs 366 palabras) pero también
  disparó un bucle "no, no, no…" dentro de un solo cue → `collapse_word_loops`.
- `app/postproc.py`: `drop_echo` (cues del mic que repiten al sistema por
  solape de tiempo y similitud de texto), `collapse_repeats`,
  `collapse_word_loops`.
- `build_whisper_args`: `-bs 5 -bo 5 -mc 64` + prompt de vocabulario. Nota: el
  default de este whisper-cli ya era beam 5, así que el beam no es una mejora
  por sí solo; el salto de calidad viene del modelo.
- **VAD retestado** con turbo (umbrales 0.5 y 0.25): sigue descartando >93 % del
  habla real (8-25 palabras de ~370). Se mantiene desactivado. El binario de
  whisper.cpp no se reemplazó: no hay build Vulkan verificada y el riesgo supera
  el beneficio sin una referencia WER.
- `tools/bench_transcribe.py` compara configuraciones y calcula WER si se da una
  referencia corregida a mano. **Pendiente:** aportar esa referencia; sin ella
  las comparaciones son por lectura.

## ADR-013 — GUI web (pywebview) reemplaza CustomTkinter (revierte ADR-010)

El usuario pidió una GUI "muy bonita y moderna". CustomTkinter no da
animaciones, blur ni waveform fluido. `app/webgui.py` abre `ui/index.html`
(HTML/CSS/JS sin build) en pywebview; `app/api.py` es el puente fino sobre
`RecordingController` (comandos por `js_api`, eventos por `window.echo.emit`).
La GUI anterior queda en `legacy/gui_customtkinter.py`. Si WebView2 o pywebview
faltan, `webgui` cae a la bandeja.

## ADR-014 — Modo ligero por default

AnotaVoz tiene que poder clonarse y usarse en otra PC (en particular una
laptop de trabajo sin GPU dedicada). ADR-011 había subido el default a
`large-v3-turbo` porque la máquina de desarrollo tiene GPU; en una máquina
sin ella eso es una descarga de 1.6 GB y una transcripción lenta que nadie
pidió. Revierte ese punto de ADR-011 y vuelve al espíritu de ADR-008.

- `FALLBACK_MODEL`/`DEFAULT_MODEL` = `small`. Un `config.json` existente no se
  toca. La GUI solo sugiere pasar a "Best" cuando detecta una GPU.
- Los binarios no viven en git (`ffmpeg.exe` ~100 MB, `ggml-vulkan.dll`
  ~54 MB). `tools/setup_binaries.py` baja el zip oficial de whisper.cpp
  v1.9.2 y verifica cada archivo contra `core/whisper/MANIFEST.json` antes de
  copiarlo; un zip que no coincide no pisa una instalación que funciona.
- El backend Vulkan es opt-in (`--gpu`): ggml carga los backends que encuentra
  junto al exe, así que sin esa DLL corre en CPU sin tocar código.
- `--whisper-zip`/`--vulkan-zip` instalan desde un zip local, para redes que
  bloquean GitHub.
- Los tres `run*.bat` comparten `_bootstrap.bat` (Python, `.venv`,
  dependencias), así que clonar + doble click alcanza.
- Motor, `ffmpeg` y modelo los baja la app misma en el prewarm
  (`RecordingController._first_run_setup`), no el `.bat`: como la GUI corre
  sin consola, la ventana tiene que estar ya abierta mostrando el progreso, o
  el primer arranque parece colgado durante ~600 MB de descargas.

Costo aceptado: `small` es menos preciso en audio real de reunión (ver las
comparaciones de ADR-012). Quien tenga hardware lo cambia con un click.

## ADR-015 — Pausa: descartar frames, no cerrar streams

Pausar/reanudar una grabación sin disparar la transcripción (que solo corre
al detener). Estado nuevo `paused` en `RecordingController`, entre
`recording` y `transcribing`.

- Los streams WASAPI (mic, loopback y keep-alive) **siguen abiertos** en
  pausa; `StreamRecorder` simplemente descarta los frames. Reanudar es
  instantáneo y no hay que volver a resolver dispositivos ni reabrir el
  loopback (ver ADR-007).
- Las dos pistas se pausan juntas (`CaptureSession.set_paused`), así que
  saltan el mismo tramo y el merge por timestamp sigue alineado. El desfase
  posible es de un buffer (~20 ms).
- Un solo par de WAV por grabación, sin segmentos: el resto del pipeline
  (preprocesado, whisper, merge, historial) no cambia. Costo: los timestamps
  son de tiempo grabado, no de reloj.
- Atajo global `Ctrl+Shift+Espacio` (`pause_hotkey` en config, `""` lo
  apaga). `keyboard` no suprime la tecla, así que la app enfocada también la
  recibe: se eligió una combinación que casi ninguna app usa, y no
  `Ctrl+Shift+P` (paleta de comandos en VS Code, ventana privada en Firefox).
  Un valor inválido en config se ignora con un aviso en vez de impedir grabar.

## ADR-016 — Grabar con una sola fuente si la otra falta

Sin micrófono default, `CaptureSession.start()` lanzaba `DeviceError` y no se
grababa nada, ni siquiera el audio del sistema — que es justo lo que importa
en una reunión donde solo se escucha. Lo mismo si el micrófono existe pero
Windows bloquea el acceso (política corporativa).

- Cada pista se resuelve y abre por separado (`_open_recorder`). La que falla
  queda en `CaptureSession.skipped` con el motivo y no deja un WAV vacío.
- `stop()` devuelve `None` para la pista no grabada; `session.py` la salta.
- El motivo llega a la UI como el mensaje de inicio de grabación, en vez del
  genérico.
- Sin ninguna de las dos fuentes sigue siendo un error explícito.
