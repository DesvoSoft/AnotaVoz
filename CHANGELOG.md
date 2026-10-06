# Changelog

## v0.2.0 — 2026-10-06

**El proyecto pasa a llamarse AnotaVoz** (antes EchoNote: el nombre ya lo
usaban varias apps parecidas).

- Repo: `github.com/DesvoSoft/AnotaVoz`. La URL anterior redirige.
- La carpeta de datos pasa de `%APPDATA%/EchoNote` a `%APPDATA%/AnotaVoz`. Se
  mueve sola en el primer arranque: ajustes y modelos ya descargados se
  conservan.
- Variables de entorno: `ANOTAVOZ_FFMPEG` / `ANOTAVOZ_WHISPER` (antes
  `ECHONOTE_*`). Log: `anotavoz.log`.
- Sin cambios de funcionalidad respecto de v0.1.0.

## v0.1.0 — 2026-10-06

Primera versión publicada, con el nombre EchoNote. Grabadora y transcriptor local para Windows:
micrófono + audio del sistema en pistas separadas, transcripción offline con
whisper.cpp.

### Incluye

- **Captura** de micrófono y audio del sistema (WASAPI loopback) en paralelo,
  sin integrarse con ninguna app.
- **Transcripción local** por pista, unida cronológicamente con turnos
  `YO` / `OTROS` y timestamps. Exporta TXT, Markdown y SRT.
- **Tres interfaces** sobre el mismo controlador: ventana (pywebview), bandeja
  y consola.
- **Modo ligero por default**: modelo `small` en CPU. GPU (Vulkan) y
  `large-v3-turbo` son opt-in.
- **Pausar / reanudar** sin transcribir: botón en la ventana, ítem en la
  bandeja y atajo `Ctrl+Shift+Espacio`. Se transcribe una sola vez, al detener.
- **Graba con una sola fuente** si la otra falta (sin micrófono, micrófono
  bloqueado o sin salida de audio) y avisa cuál falta.
- **Primer arranque visible**: la ventana se abre enseguida y muestra con barra
  de progreso la descarga del motor, `ffmpeg` y el modelo.
- **Ventana sin consola**: `run_gui.bat` arranca con `pythonw`; los errores van
  a `%APPDATA%/AnotaVoz/anotavoz.log`.
- **Instalación en otra PC**: clonar y doble click. Los binarios se bajan
  fijados por SHA-256 (`core/whisper/MANIFEST.json`), con instalación offline
  desde zip para redes restringidas.

### Requisitos

Windows 10/11 x64 y Python 3.10+. No hay ejecutable portable todavía.

### Limitaciones conocidas

- Idioma de transcripción fijo en español.
- Sin selector de dispositivo de audio ni de atajos en la ventana (se editan en
  `config.json`).
- Tras una pausa, los timestamps cuentan tiempo grabado, no hora de reloj.
