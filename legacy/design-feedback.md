Sí. De hecho, lo que describes se puede hacer **sin meterse dentro de Teams, Discord, Zoom ni ninguna otra aplicación**. La idea sería capturar el audio directamente desde Windows, como una especie de “grabadora universal”.

### Cómo funcionaría

```text
                ┌─────────────────────┐
                │       Windows       │
                │                     │
Teams ────────► │                     │
Discord ──────► │   Audio del sistema │ ──────┐
YouTube ──────► │      (WASAPI)       │       │
Juegos ───────► │                     │       │
                └─────────────────────┘       │
                                              ▼
                                    ┌─────────────────┐
Micrófono ─────────────────────────►│ Capturador      │
                                    │                 │
                                    │ Track sistema   │
                                    │ Track micrófono │
                                    └────────┬────────┘
                                             │
                         ┌───────────────────┘
                         ▼
                  ┌─────────────┐
                  │ Transcriptor│
                  │   Whisper   │
                  └──────┬──────┘
                         ▼
                ┌──────────────────┐
                │ Transcript.txt   │
                │ o ventana        │
                └──────────────────┘
```

Windows tiene **WASAPI Loopback**, que permite capturar el audio que está reproduciendo un dispositivo de salida sin necesidad de instalar un “cable virtual” ni modificar las aplicaciones. Además, funciona en modo compartido, que es precisamente lo que nos interesa para una herramienta general. ([Microsoft Learn][1])

### Y el atajo sería realmente global

Podrías tener, por ejemplo:

**Ctrl + Shift + Space**

* Primera pulsación → empieza a escuchar
* Segunda pulsación → detiene
* La app puede mostrar un pequeño indicador en la bandeja: 🔴 REC
* No abre ninguna ventana encima de Teams/Discord
* No necesita saber qué aplicación está usando el audio

Windows dispone de `RegisterHotKey`, que registra una combinación de teclas a nivel del sistema y recibe el evento aunque otra aplicación esté en primer plano. ([Microsoft Learn][2])

### Para el MVP yo lo haría en Python

En tu caso no complicaría esto con C++ todavía.

| Parte                | Tecnología                          |
| -------------------- | ----------------------------------- |
| Captura audio del PC | **PyAudioWPatch / WASAPI**          |
| Micrófono            | **PyAudioWPatch**                   |
| Atajo global         | `RegisterHotKey` vía `ctypes`/Win32 |
| App residente        | `pystray`                           |
| Configuración mínima | Tkinter o CustomTkinter             |
| Transcripción        | **faster-whisper**                  |
| Audio temporal       | WAV                                 |
| Resultado            | TXT / Markdown                      |

`PyAudioWPatch` está específicamente diseñado para permitir que PyAudio utilice WASAPI Loopback y grabe el audio que sale por los parlantes o audífonos. ([GitHub][3])

Y `faster-whisper` es una implementación optimizada de Whisper que puede ejecutarse localmente y soporta Windows; además, puede utilizar GPU NVIDIA cuando está disponible. ([GitHub][4])

### Hay una decisión importante que yo cambiaría

No mezclaría inmediatamente el micrófono y el audio del PC.

Guardaría:

```text
grabacion_2026-09-21_09-30/
│
├── system.wav
├── microphone.wav
└── transcript.txt
```

Así podemos hacer posteriormente algo mucho más útil:

```text
[09:31:04] Tú:
Bueno, entonces revisamos el acta...

[09:31:08] Participante:
Sí, yo ya había revisado esa parte...

[09:31:15] Tú:
Perfecto, entonces...
```

Incluso podemos hacer que Whisper procese ambas pistas y usar:

**[YO]** → micrófono
**[OTROS]** → audio del sistema

Sin intentar inicialmente hacer identificación avanzada de personas.

### Y lo bueno es que NO necesitaríamos hacer esto

No necesitaríamos:

* plugins de Teams
* integración con Discord
* bots
* captura de pantalla
* leer ventanas
* inyectar código
* modificar procesos
* crear un dispositivo de audio virtual
* permisos de administrador para cada aplicación

Sería simplemente:

**Windows → capturar audio → transcribir.**

Eso encaja bastante bien con lo que llamas **NO INVASIVA**.

### Primera versión

Yo la haría extremadamente pequeña:

```text
Tray app

⚪ Esperando
🔴 Grabando
🟡 Transcribiendo

[ Ctrl + Shift + Space ]

Última transcripción:
2026-09-21_09-35.txt
```

Y en configuración únicamente:

```text
Micrófono:        [ Micrófono USB          ▼ ]
Salida sistema:   [ Headphones             ▼ ]

Atajo:            [ Ctrl + Shift + Space ]

Modelo Whisper:   [ small / medium / large ▼ ]

[ ✓ ] Iniciar con Windows
[ ✓ ] Mostrar indicador al grabar
```

La **primera versión ni siquiera tendría transcripción en tiempo real**. Al detener:

```text
Ctrl + Shift + Space
          ↓
deja de grabar
          ↓
faster-whisper procesa
          ↓
transcript.txt
          ↓
notificación "Transcripción lista"
```

Eso reduce muchísimo la complejidad y nos permite comprobar primero que **la captura simultánea de audio del PC + micrófono funciona perfectamente**.

Una consideración importante: WASAPI Loopback normalmente captura **la mezcla que Windows está reproduciendo por el dispositivo seleccionado**, por lo que también pueden entrar sonidos de notificaciones, YouTube, juegos, etc. y no solo Teams/Discord. ([Microsoft Learn][1])

Yo empezaría justamente por ese MVP porque después podemos convertirlo en algo bastante más interesante: transcripción casi en tiempo real, timestamps, detección de hablantes, búsqueda dentro de reuniones y resúmenes, sin cambiar la arquitectura principal.

[1]: https://learn.microsoft.com/en-us/windows/win32/coreaudio/loopback-recording?utm_source=chatgpt.com "Loopback Recording - Win32 apps | Microsoft Learn"
[2]: https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-registerhotkey?utm_source=chatgpt.com "RegisterHotKey function (winuser.h) - Win32 apps | Microsoft Learn"
[3]: https://github.com/s0d3s/PyAudioWPatch?utm_source=chatgpt.com "GitHub - s0d3s/PyAudioWPatch: 🐍 PyAudio | PortAudio fork with WASAPI loopback support 🔊 Record audio from speakers on Windows · GitHub"
[4]: https://github.com/SYSTRAN/faster-whisper/blob/master/README.md?utm_source=chatgpt.com "faster-whisper/README.md at master · SYSTRAN/faster-whisper · GitHub"
