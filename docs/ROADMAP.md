# Roadmap

Cada fase deja el core funcionando de punta a punta antes de sumar la
siguiente capa. No se cambia arquitectura base entre fases — solo se agrega
encima.

## Fase 0 — Documentación inicial ✅ (en curso)

- [x] Portar motor whisper.cpp + ffmpeg desde Y2oby
- [x] README, roadmap, decisiones de diseño
- [ ] Arquitectura técnica detallada (siguiente paso del loop)

## Fase 1 — Captura simultánea (sin transcripción)

Objetivo: probar que mic + sistema se graban en simultáneo, sincronizados,
sin mezclar.

- [x] Reemplazar `soundcard` por `PyAudioWPatch` (WASAPI loopback nativo)
- [x] Grabar en dos streams paralelos (callback mode, no polling secuencial)
- [x] Guardar `microphone.wav` + `system.wav` por separado
- [x] Resolución de dispositivo por índice, no por nombre (`app/devices.py`) —
      picker de UI sigue siendo Fase 4
- [x] Verificar sincronía — offset ~100ms en pruebas reales (`tools/test_capture.py`),
      atribuible a latencia de arranque de driver, no a pérdida de frames
- [x] Bug encontrado y resuelto: loopback no captura nada en silencio real sin
      un stream "keep-alive" activo en la salida (ver ADR-007)

## Fase 2 — Transcripción end-to-end (CLI/hotkey, sin tray)

Objetivo: `hotkey → grabar → hotkey → transcribir` sólido.

- [x] Integrar `app/transcriber.py` (whisper.cpp) sobre las dos pistas
      (`app/session.py`) — verificado end-to-end con `tools/test_transcribe.py`
- [x] Transcribir cada pista por separado, no audio mezclado
- [x] Merge cronológico: `[YO]` (mic) / `[OTROS]` (sistema) por timestamp
      (`merge_transcripts` en `app/session.py`)
- [x] Gate: hotkey ignorado hasta que el modelo esté listo (`main.py`,
      estado `LOADING` antes de `IDLE`)
- [x] Salida: `transcript.txt` con speaker tags + timestamps —
      verificado con `tools/test_session.py`
- [x] Confirmado en vivo por el usuario — grabación real de reunión
      (`recordings/2026-09-21_14-27-54/`) probó el ciclo completo y expuso
      los problemas de calidad resueltos abajo

### Calidad de transcripción (encontrado en la grabación real de arriba)

- [x] Formato feo: línea por cue → agrupado por turno de hablante en un
      párrafo (`group_by_turn` en `app/session.py`, ver ADR-009/010)
- [x] Alucinación "you" en silencio total del track `system` → se detecta
      silencio digital (`wav_peak_amplitude`) y se salta whisper directo,
      en vez de confiar en `-nth` (probado, no alcanzaba) — ver ADR-009
- [x] Transcript de la grabación real regenerado con el fix

## Fase 3 — Tray app (invisible por defecto)

- [x] Icono de bandeja con estados (color por estado) — `app/tray.py`
- [x] Hotkey global — extraído a `app/controller.py`, compartido entre
      `main.py` (consola) y `app/tray.py` (bandeja)
- [x] Notificación al terminar transcripción (`icon.notify`)
- [x] Cierre limpio: `unhook_all_hotkeys()` antes de `icon.stop()`, sin
      `os._exit`; construcción + start/shutdown verificados por script
- [x] Confirmado en vivo — mismo run real de arriba

## Fase 3.5 — GUI de escritorio (CustomTkinter)

Pedido explícito del usuario tras ver el formato feo/output impreciso:
querían algo más visual que consola/bandeja para controlar grabación,
modelo y revisar transcripciones.

- [x] `app/gui.py` — tercer front-end sobre el mismo `RecordingController`
      (cero lógica duplicada, ver ADR-010)
- [x] Botón grabar/detener con color por estado, selector de modelo con
      tamaño/nota de calidad, panel de transcripción + historial de
      grabaciones anteriores
- [x] Verificado visualmente con screenshot real (`run_gui.bat` /
      `python -m app.gui`)
- [x] v2 (pedido "mejorá mucho más la GUI"): tema propio (no el verde
      stock de ctk), ícono de app generado, timer de grabación en vivo,
      badge de GPU detectada, transcripción con color por hablante
      (Tú/Otros), botones copiar + abrir carpeta, sidebar de historial con
      fecha/hora legible — verificado con screenshot cargando una
      transcripción real, acentos correctos

## Precisión de transcripción — segunda ronda (ADR-011)

Usuario reportó que seguía "super impreciso" después de la Fase 2.5.
Investigación + benchmarking sobre la misma grabación real:

- [x] Bug real encontrado: GPU nunca se activaba (`use_gpu` nunca se pasaba
      desde `session.py` pese a tener `transcriber.gpu_backend()` ya
      escrito) — ahora se detecta y usa automáticamente
- [x] Idioma fijado a `es` (estaba en `auto`, sin motivo para este uso)
- [x] Modelo default subido a `large-v3-turbo` para instalaciones nuevas —
      GPU quita la excusa de tiempo, solo queda el costo de descarga
- [x] VAD (Silero) investigado, implementado, probado sobre audio real, y
      **desactivado**: redujo 181s de habla real a 1.3s y produjo una
      alucinación en vez de transcripción — queda en el código pero no en
      el pipeline por default hasta encontrar una combinación
      binario/modelo que funcione

## Fase 4 — Configuración mínima

- [x] Selector de modelo Whisper — cubierto por el dropdown de `app/gui.py`
      y el submenú "Model" de `app/tray.py`
- [ ] Selector de dispositivo mic/sistema (no auto-detección frágil)
- [ ] Selector de hotkey
- [ ] "Iniciar con Windows"

## Fase 4.5 — Portabilidad (ADR-014)

- [x] Modo ligero por default: `small` en CPU, GPU/Vulkan y modelo grande opt-in
- [x] `tools/setup_binaries.py`: binarios fijados por hash, con instalación
      offline desde zip
- [x] `_bootstrap.bat` compartido: clonar + doble click en cualquier PC con Python
- [x] Repo en GitHub

## Fase 5 — Mejoras nativas / distribución

- [ ] `RegisterHotKey` vía `ctypes` en vez de `keyboard` (menos dependencias, más nativo)
- [ ] Empaquetado `.exe` portable (PyInstaller), para PCs sin Python

## Backlog (post-MVP, no bloquea nada de arriba)

- Transcripción casi en tiempo real
- Detección de hablantes múltiples dentro de una misma pista (diarización)
- Búsqueda dentro de transcripciones históricas
- Resúmenes automáticos de reunión
