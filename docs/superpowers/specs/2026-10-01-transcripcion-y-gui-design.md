# EchoNote: mejora de transcripción + GUI web moderna

Fecha: 2026-10-01 · Estado: borrador para revisión

## Objetivo

1. Transcripción en español claramente más fiel (menos palabras erróneas o inventadas, sin eco duplicado entre `[YO]` y `[OTROS]`).
2. GUI de nivel producto comercial: moderna, animada, clara/oscura.

Supuestos: uso en español, reuniones/llamadas, 100 % local/offline, Windows, GPU NVIDIA (Vulkan) disponible.

## Hallazgos que motivan el cambio

- `%APPDATA%/EchoNote/config.json` tiene `"model": "small"`; la descarga de `large-v3-turbo` quedó en `.part`. ADR-011 asumió el modelo grande, pero no se está usando.
- El audio llega a whisper sin preprocesar (sin normalización, ruido ni anti-eco) y sin vocabulario de contexto ni ajuste de beam/temperatura.
- El micrófono capta el audio de los parlantes, que aparece duplicado en ambas pistas.
- VAD (Silero) descarta 99 % del habla real con el `whisper-cli` actual (ADR-011); el binario es antiguo.
- CustomTkinter limita el resultado visual (ADR-010).

## Decisiones (reabren ADR-010; ADR-001 se mantiene)

- GUI: **pywebview + HTML/CSS/JS** reemplaza `app/gui.py`. Consola y bandeja siguen sobre `RecordingController`.
- Motor: **whisper.cpp se mantiene**, con mejoras.

## Parte A: calidad de transcripción

### A1. Modelo
- Default `large-v3-turbo`. La descarga reanuda el `.part` existente (ya soportado por `Transcriber._download`).
- Si `config.json` tiene un modelo menor, la UI muestra un aviso con botón "Cambiar a Best"; no se cambia en silencio.

### A2. Preprocesado: `app/audio_prep.py`
Función `prepare(track_wav, kind, out_wav)` ejecutada con el `ffmpeg.exe` incluido, antes de whisper:
- mic: `highpass=f=80, afftdn, loudnorm`
- sistema: `loudnorm`
- Salida 16 kHz mono PCM s16le (lo que `Transcriber.to_wav` ya espera).

### A3. Anti-eco
1. Preferido: cancelación del eco del mic usando la pista de sistema como referencia (filtro adaptativo por ffmpeg o numpy), solo si mejora en el banco de pruebas.
2. Respaldo (siempre activo): descartar cues de mic cuyo intervalo se solape ≥ 60 % con un cue de sistema y cuyo texto sea similar (ratio difflib ≥ 0.75). Vive en `app/session.py::merge_transcripts`.

### A4. Decodificación (`Transcriber._run_chunk`)
`--beam-size 5`, `--best-of 5`, temperatura con fallback por defecto de whisper, `--max-context` acotado, `--prompt` = vocabulario del usuario + cola del chunk previo (ya existe `CARRY_CHARS`). Parámetros expuestos como constantes configurables.

### A5. VAD
Actualizar `core/whisper/whisper-cli.exe` y DLLs a una versión reciente de whisper.cpp. VAD solo se activa si una prueba automática sobre `recordings/` conserva ≥ 95 % de la duración de habla. Si falla, queda desactivado (estado actual).

### A6. Post-proceso
Colapso de repeticiones (`_detect_loops` pasa de aviso a limpieza), espacios y mayúsculas tras punto. Agrupación por turno existente se mantiene.

### A7. Medición: `tools/bench_transcribe.py`
Corre varias configuraciones sobre un WAV con referencia corregida a mano (`tests/fixtures/<n>.ref.txt`) y reporta WER y tiempo. Toda mejora de A2–A5 se acepta solo si baja el WER. Requiere una referencia de 2-3 min aportada por el usuario.

## Parte B: GUI web

### B1. Arquitectura
```text
ui/ (index.html, css/, js/ módulos ES, sin paso de build)
        ▲ evaluate_js (eventos)     │ js_api (comandos)
app/api.py  ── Api: puente fino ──► RecordingController (sin cambios de lógica)
app/webgui.py  ── crea ventana pywebview, arranca Api
```
- `Api` expone: `toggle()`, `get_state()`, `list_history()`, `load_transcript(id)`, `delete/rename(id)`, `get_settings()/set_settings()`, `list_devices()`, `download_model(name)`, `export(id, fmt)`, `open_folder(id)`.
- Eventos empujados a JS: `state`, `log`, `levels` (RMS por pista, ~20 Hz), `progress` (por chunk), `model_download`.
- Un solo hilo despacha a JS (cola + `evaluate_js`), igual que la cola actual de `gui.py`.

### B2. Cambios de backend requeridos
- `capture.py`: calcular RMS por callback y exponerlo (`on_level`).
- `controller.py`: reenviar niveles y progreso; ya tiene estados.
- `config.py`: pasar de solo modelo a ajustes (modelo, vocabulario, dispositivos, tema, hotkey).
- `session.py`: guardar `meta.json` por grabación (nombre, duración, modelo) para el historial.

### B3. Pantallas
- **Grabar:** botón central con anillo pulsante, waveform en vivo mic/sistema, timer, chip de GPU/modelo.
- **Transcripción:** burbujas por hablante (Tú/Otros), timestamps, búsqueda, copiar, exportar TXT/SRT/MD.
- **Historial:** lista con búsqueda, fecha, duración, vista previa, renombrar/borrar.
- **Ajustes:** dispositivos, modelo con barra de descarga, vocabulario, hotkey, tema.

### B4. Estilo
Tema oscuro/claro según sistema, Inter, vidrio/blur sutil, micro-animaciones, un único acento, responsive hasta 680 px.

## Errores y casos límite
- Sin WebView2 en el equipo: mensaje claro y fallback a bandeja.
- Pista en silencio: se omite (ADR-009 intacto).
- Cierre de ventana mientras graba: confirmación, luego `controller.shutdown()`.

## Pruebas
- Unitarias: `audio_prep` (comando ffmpeg y salida), dedupe de eco, `merge_transcripts`, `Api` con controller falso.
- Banco WER (A7) como criterio de aceptación de la Parte A.
- GUI: verificación visual en el navegador integrado sobre `ui/index.html` con `Api` simulado, más una prueba manual real de grabar → transcribir.

## Fuera de alcance
Diarización multi-hablante, nube, corrección por LLM, instalador, rediseño de la bandeja.

## Orden de implementación sugerido
1. Banco WER + referencia (base de medición).
2. A1, A4, A2, A3, A6 midiendo cada una.
3. A5 (binario + VAD condicional).
4. B2 (backend: niveles, ajustes, meta.json).
5. B1 + B3 + B4 (UI).
6. Verificación end-to-end.

## Riesgos
- Anti-eco adaptativo puede degradar voz propia: por eso el respaldo por texto es el default y el filtro solo entra si gana en WER.
- Binario nuevo de whisper.cpp puede cambiar flags: se valida con `--help` y el banco antes de reemplazar.
- Sin referencia corregida no hay WER confiable; se pide al usuario.
