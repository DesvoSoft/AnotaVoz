import soundcard as sc
import soundfile as sf
import numpy as np
import keyboard
import pystray
from PIL import Image, ImageDraw
import threading
from faster_whisper import WhisperModel
import os
import time

# --- CONFIGURACIÓN ---
HOTKEY = 'ctrl+shift+r'
SAMPLE_RATE = 16000
WHISPER_MODEL_SIZE = "base" # "tiny", "base", "small", "medium", "large-v3"

# --- VARIABLES GLOBALES ---
is_recording = False
record_thread = None
whisper_model = None

def load_model():
    global whisper_model
    print("Cargando modelo de transcripción (puede tardar la primera vez)...")
    whisper_model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
    print("Modelo cargado.")

def get_audio_devices():
    # Obtener todos los micrófonos y dispositivos de loopback (audio del sistema)
    mics = sc.all_microphones(include_loopback=True)
    
    default_mic = sc.default_microphone()
    
    # Buscar el dispositivo de loopback del altavoz por defecto
    default_speaker = sc.default_speaker()
    loopback_mic = None
    for m in mics:
        if m.isloopback and default_speaker.name in m.name:
            loopback_mic = m
            break
            
    # Fallback si no encuentra el loopback exacto
    if not loopback_mic:
        for m in mics:
            if m.isloopback:
                loopback_mic = m
                break
                
    return default_mic, loopback_mic

def record_audio():
    global is_recording
    default_mic, loopback_mic = get_audio_devices()
    
    if not loopback_mic:
        print("Error: No se pudo encontrar el dispositivo de audio del sistema (Loopback).")
        return

    print(f"Grabando Micro: {default_mic.name}")
    print(f"Grabando Sistema: {loopback_mic.name}")
    
    # Grabamos ambos canales. 
    # soundcard permite grabar múltiples dispositivos si los pasas como lista.
    # Para simplificar, grabaremos por separado y los mezclaremos, 
    # o usaremos la función de grabación multicanal.
    
    audio_data_mic = []
    audio_data_sys = []
    
    # Grabador para Micrófono
    with default_mic.recorder(samplerate=SAMPLE_RATE, channels=1) as mic_rec:
        # Grabador para Sistema (Loopback)
        with loopback_mic.recorder(samplerate=SAMPLE_RATE, channels=1) as sys_rec:
            
            while is_recording:
                # Grabar bloques de 0.5 segundos
                data_mic = mic_rec.record(numframes=int(SAMPLE_RATE * 0.5))
                data_sys = sys_rec.record(numframes=int(SAMPLE_RATE * 0.5))
                
                audio_data_mic.append(data_mic)
                audio_data_sys.append(data_sys)

    # Procesar y guardar al terminar
    if audio_data_mic and audio_data_sys:
        mic_audio = np.concatenate(audio_data_mic, axis=0)
        sys_audio = np.concatenate(audio_data_sys, axis=0)
        
        # Mezclar ambos audios (sumar y normalizar para que no sature)
        # Ajusta los pesos (0.7 sistema, 0.3 micro) según prefieras
        mixed_audio = (sys_audio * 0.7 + mic_audio * 0.3) 
        mixed_audio = mixed_audio / np.max(np.abs(mixed_audio)) # Normalizar
        
        filename = "grabacion_temp.wav"
        sf.write(filename, mixed_audio, SAMPLE_RATE)
        print("Grabación guardada. Transcribiendo...")
        transcribe_audio(filename)

def transcribe_audio(file_path):
    segments, info = whisper_model.transcribe(file_path, language="es")
    transcript = " ".join([segment.text for segment in segments])
    
    print("\n--- TRANSCRIPCIÓN ---")
    print(transcript)
    print("---------------------\n")
    
    # Aquí puedes guardar el texto en un archivo .txt o copiarlo al portapapeles
    with open("transcripcion.txt", "a", encoding="utf-8") as f:
        f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}]\n{transcript}\n")
        
    os.remove(file_path) # Limpiar audio temp

def toggle_recording():
    global is_recording, record_thread
    if not is_recording:
        print("Iniciando grabación...")
        is_recording = True
        record_thread = threading.Thread(target=record_audio, daemon=True)
        record_thread.start()
    else:
        print("Deteniendo grabación...")
        is_recording = False

# --- INTERFAZ DE BANDEJA DEL SISTEMA (TRAY) ---
def create_image():
    # Crear un ícono simple (un círculo rojo)
    image = Image.new('RGB', (64, 64), color=(73, 109, 137))
    d = ImageDraw.Draw(image)
    d.ellipse((16, 16, 48, 48), fill=(255, 0, 0))
    return image

def on_clicked(icon, item):
    if str(item) == 'Salir':
        icon.stop()
        os._exit(0)

def setup_tray():
    menu = pystray.Menu(
        pystray.MenuItem('Iniciar/Parar Grabación', lambda: toggle_recording()),
        pystray.MenuItem('Salir', on_clicked)
    )
    icon = pystray.Icon("TranscriptorApp", create_image(), "Transcriptor", menu)
    
    # Configurar el atajo global
    keyboard.add_hotkey(HOTKEY, toggle_recording)
    print(f"App corriendo en bandeja. Usa {HOTKEY} para grabar.")
    
    icon.run()

if __name__ == "__main__":
    # Cargar modelo en un hilo para no bloquear el inicio
    threading.Thread(target=load_model, daemon=True).start()
    
    # Iniciar bandeja del sistema (esto bloquea el hilo principal)
    setup_tray()