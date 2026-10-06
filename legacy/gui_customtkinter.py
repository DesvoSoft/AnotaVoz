"""Desktop GUI front-end (CustomTkinter). Same RecordingController as
main.py/app/tray.py — this module only draws state and a transcript viewer.

Controller callbacks (on_state/on_log) fire from background threads
(prewarm, stop_and_transcribe); Tkinter widgets are not thread-safe, so
those callbacks only push onto a queue and the Tk mainloop drains it via
`after()` on its own thread.
"""
import os
import queue
import re
import time
import tkinter.font as tkfont

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk

from app import binaries, single_instance
from app.controller import IDLE, LOADING, RECORDING, TRANSCRIBING, RecordingController
from app.transcriber import MODEL_LABELS, MODELS, gpu_backend

# --- palette ----------------------------------------------------------
# A deliberate palette instead of ctk's stock theme: a calm slate
# background with a single warm accent, so the record button (the one
# thing this app is *for*) is the only saturated color on screen at rest.
BG = "#12141a"
SURFACE = "#1b1e27"
SURFACE_ALT = "#232733"
BORDER = "#2c3140"
TEXT = "#e7e9ee"
TEXT_DIM = "#8b91a3"
ACCENT = "#5b8def"
ACCENT_HOVER = "#4a77d1"
RECORD = "#e5484d"
RECORD_HOVER = "#c93f43"
SPEAKER_YO = "#5b8def"
SPEAKER_OTROS = "#f2a65a"

STATE_LABELS = {
    LOADING: "Cargando modelo...",
    IDLE: "Listo",
    RECORDING: "Grabando",
    TRANSCRIBING: "Transcribiendo...",
}
STATE_DOT = {
    LOADING: "#e6b800",
    IDLE: "#3ecf6e",
    RECORDING: RECORD,
    TRANSCRIBING: "#f2a65a",
}

_HEADER_RE = re.compile(r"^(\[\d{2}:\d{2}:\d{2}\]) (YO|OTROS)$")

ctk.set_appearance_mode("dark")


def _app_icon_image(size=128):
    """Simple mark: a mic capsule inside a rounded accent tile. Generated
    instead of shipping a binary asset — cheap, no extra file to track."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=size // 4, fill=ACCENT)
    cx, cy = size // 2, size * 0.42
    cap_w, cap_h = size * 0.24, size * 0.4
    d.rounded_rectangle((cx - cap_w / 2, cy - cap_h / 2, cx + cap_w / 2, cy + cap_h / 2),
                        radius=cap_w / 2, fill="white")
    stand_r = size * 0.32
    d.arc((cx - stand_r, cy - stand_r * 0.6, cx + stand_r, cy + stand_r * 0.9),
          start=20, end=160, fill="white", width=max(2, size // 22))
    d.line((cx, cy + stand_r * 0.55, cx, cy + stand_r * 0.85), fill="white", width=max(2, size // 22))
    d.line((cx - size * 0.14, cy + stand_r * 0.85, cx + size * 0.14, cy + stand_r * 0.85),
           fill="white", width=max(2, size // 22))
    return img


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("EchoNote")
        self.geometry("880x640")
        self.minsize(680, 480)
        self.configure(fg_color=BG)

        self._icon_photo = ImageTk.PhotoImage(_app_icon_image())
        self.wm_iconphoto(True, self._icon_photo)

        self._events = queue.Queue()
        self._recording_started_at = None
        self._current_transcript_dir = None
        self.controller = RecordingController(
            on_state=lambda s: self._events.put(("state", s)),
            on_log=lambda m: self._events.put(("log", m)),
        )

        self._build_ui()
        self._apply_state(LOADING)
        self.controller.start()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(150, self._poll_events)
        self.after(500, self._tick_timer)

    # --- layout ------------------------------------------------------

    def _card(self, parent, **kwargs):
        opts = dict(fg_color=SURFACE, corner_radius=14, border_width=1, border_color=BORDER)
        opts.update(kwargs)
        return ctk.CTkFrame(parent, **opts)

    def _build_ui(self):
        root = ctk.CTkFrame(self, fg_color="transparent")
        root.pack(fill="both", expand=True, padx=18, pady=18)
        root.grid_columnconfigure(1, weight=1)
        root.grid_rowconfigure(0, weight=1)

        self._build_sidebar(root)
        self._build_main(root)

    def _build_sidebar(self, root):
        sidebar = self._card(root, width=220)
        sidebar.grid(row=0, column=0, sticky="ns", padx=(0, 14))
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(3, weight=1)

        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=16, pady=(18, 4))
        ctk.CTkLabel(brand, text="🎙 EchoNote", font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(brand, text="Transcripción local, offline", font=ctk.CTkFont(size=11),
                     text_color=TEXT_DIM).pack(anchor="w")

        gpu_text, gpu_color = self._probe_gpu_label()
        ctk.CTkLabel(sidebar, text=gpu_text, font=ctk.CTkFont(size=11), text_color=gpu_color,
                     wraplength=190, justify="left").grid(row=1, column=0, sticky="ew", padx=16, pady=(10, 14))

        ctk.CTkLabel(sidebar, text="HISTORIAL", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=TEXT_DIM).grid(row=2, column=0, sticky="w", padx=16, pady=(4, 6))

        self.history_frame = ctk.CTkScrollableFrame(sidebar, fg_color="transparent")
        self.history_frame.grid(row=3, column=0, sticky="nsew", padx=8, pady=(0, 12))
        self._refresh_history()

    def _probe_gpu_label(self):
        try:
            whisper_cli = binaries.get_whisper_cli()
            gpu = gpu_backend(whisper_cli) if whisper_cli else None
        except Exception:
            gpu = None
        if gpu and gpu.get("device"):
            return f"⚡ GPU: {gpu['device']}", "#3ecf6e"
        if gpu:
            return f"⚡ GPU: {gpu['name']}", "#3ecf6e"
        return "CPU only (sin GPU compatible)", TEXT_DIM

    def _build_main(self, root):
        main = ctk.CTkFrame(root, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(2, weight=1)

        self._build_status_row(main)
        self._build_controls_row(main)
        self._build_transcript_card(main)

        self.log_label = ctk.CTkLabel(main, text="", anchor="w", font=ctk.CTkFont(size=11),
                                       text_color=TEXT_DIM)
        self.log_label.grid(row=3, column=0, sticky="ew", pady=(8, 0))

    def _build_status_row(self, main):
        row = ctk.CTkFrame(main, fg_color="transparent")
        row.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        row.grid_columnconfigure(0, weight=1)

        left = ctk.CTkFrame(row, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w")
        self.status_dot = ctk.CTkLabel(left, text="●", font=ctk.CTkFont(size=16),
                                        text_color=STATE_DOT[LOADING])
        self.status_dot.pack(side="left")
        self.status_label = ctk.CTkLabel(left, text=STATE_LABELS[LOADING],
                                          font=ctk.CTkFont(size=15, weight="bold"), text_color=TEXT)
        self.status_label.pack(side="left", padx=(6, 0))
        self.timer_label = ctk.CTkLabel(left, text="", font=ctk.CTkFont(size=13), text_color=TEXT_DIM)
        self.timer_label.pack(side="left", padx=(12, 0))

    def _build_controls_row(self, main):
        card = self._card(main)
        card.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=18, pady=16)

        self.record_btn = ctk.CTkButton(
            inner, text="●  Grabar", height=48, width=170,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=10,
            command=self._on_toggle, state="disabled",
        )
        self.record_btn.pack(side="left")

        model_box = ctk.CTkFrame(inner, fg_color="transparent")
        model_box.pack(side="left", padx=(28, 0))
        ctk.CTkLabel(model_box, text="Modelo", font=ctk.CTkFont(size=11), text_color=TEXT_DIM).pack(anchor="w")
        names = list(MODELS.keys())
        self._model_labels = {
            n: f"{n}  ·  ~{MODELS[n][2]}MB  ·  {MODEL_LABELS.get(n, {}).get('note', '')}" for n in names
        }
        self._label_to_name = {v: k for k, v in self._model_labels.items()}
        self.model_menu = ctk.CTkOptionMenu(
            model_box, values=list(self._model_labels.values()), command=self._on_model_change,
            width=320, fg_color=SURFACE_ALT, button_color=SURFACE_ALT, button_hover_color=BORDER,
            dropdown_fg_color=SURFACE_ALT,
        )
        self.model_menu.pack(anchor="w", pady=(2, 0))

    def _build_transcript_card(self, main):
        card = self._card(main)
        card.grid(row=2, column=0, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)

        toolbar = ctk.CTkFrame(card, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 6))
        self.transcript_title = ctk.CTkLabel(toolbar, text="Transcripción", font=ctk.CTkFont(size=13, weight="bold"),
                                              text_color=TEXT)
        self.transcript_title.pack(side="left")
        ctk.CTkButton(toolbar, text="Abrir carpeta", width=110, height=26, font=ctk.CTkFont(size=11),
                     fg_color=SURFACE_ALT, hover_color=BORDER, command=self._open_folder).pack(side="right", padx=(6, 0))
        ctk.CTkButton(toolbar, text="Copiar", width=90, height=26, font=ctk.CTkFont(size=11),
                     fg_color=SURFACE_ALT, hover_color=BORDER, command=self._copy_transcript).pack(side="right")

        self.transcript_box = ctk.CTkTextbox(card, wrap="word", font=ctk.CTkFont(size=14),
                                              fg_color=SURFACE, corner_radius=0, border_width=0,
                                              text_color=TEXT)
        self.transcript_box.grid(row=1, column=0, sticky="nsew", padx=2, pady=(0, 2))
        self._configure_transcript_tags()
        self._set_transcript_text(
            "Grabá algo con Ctrl+Shift+R (o el botón de arriba)\npara ver la transcripción acá.")

    def _configure_transcript_tags(self):
        # CTkTextbox.tag_config() forbids the `font` option outright ("would
        # be incompatible with scaling") — go through the raw tkinter.Text
        # it wraps (`._textbox`) for the one tag that needs bold.
        raw = self.transcript_box._textbox
        bold = tkfont.Font(family="Segoe UI", size=13, weight="bold")
        raw.tag_config("yo", foreground=SPEAKER_YO, font=bold)
        raw.tag_config("otros", foreground=SPEAKER_OTROS, font=bold)
        raw.tag_config("stamp", foreground=TEXT_DIM)
        raw.tag_config("body", foreground=TEXT, spacing3=10)

    # --- controller wiring ---------------------------------------------

    def _on_toggle(self):
        self.controller.toggle()

    def _on_model_change(self, label):
        name = self._label_to_name.get(label)
        if name:
            self.controller.set_model(name)

    def _poll_events(self):
        try:
            while True:
                kind, payload = self._events.get_nowait()
                if kind == "state":
                    self._apply_state(payload)
                elif kind == "log":
                    self.log_label.configure(text=payload)
                    if payload.startswith("Ready:"):
                        path = payload.split(":", 1)[1].strip()
                        self._load_transcript(path)
                        self._refresh_history()
        except queue.Empty:
            pass
        self.after(150, self._poll_events)

    def _tick_timer(self):
        if self._recording_started_at is not None:
            elapsed = int(time.time() - self._recording_started_at)
            self.timer_label.configure(text=f"{elapsed // 60:02d}:{elapsed % 60:02d}")
        self.after(500, self._tick_timer)

    def _apply_state(self, state):
        self.status_dot.configure(text_color=STATE_DOT[state])
        self.status_label.configure(text=STATE_LABELS[state])
        self.record_btn.configure(state="disabled" if state in (LOADING, TRANSCRIBING) else "normal")
        if state == RECORDING:
            self.record_btn.configure(text="■  Detener", fg_color=RECORD, hover_color=RECORD_HOVER)
            self._recording_started_at = time.time()
        else:
            self.record_btn.configure(text="●  Grabar", fg_color=ACCENT, hover_color=ACCENT_HOVER)
            self._recording_started_at = None
            self.timer_label.configure(text="")
        if state == IDLE and self.controller.model_name in self._model_labels:
            self.model_menu.set(self._model_labels[self.controller.model_name])

    # --- transcript / history -------------------------------------------

    def _set_transcript_text(self, text):
        self.transcript_box.configure(state="normal")
        self.transcript_box.delete("1.0", "end")
        self.transcript_box.insert("1.0", text, ("body",))
        self.transcript_box.configure(state="disabled")

    def _render_transcript(self, text):
        self.transcript_box.configure(state="normal")
        self.transcript_box.delete("1.0", "end")
        for line in text.split("\n"):
            m = _HEADER_RE.match(line.strip())
            if m:
                stamp, speaker = m.groups()
                tag = "yo" if speaker == "YO" else "otros"
                who = "Tú" if speaker == "YO" else "Otros"
                self.transcript_box.insert("end", f"{stamp}  ", ("stamp",))
                self.transcript_box.insert("end", f"{who}\n", (tag,))
            elif line.strip():
                self.transcript_box.insert("end", line + "\n\n", ("body",))
        self.transcript_box.configure(state="disabled")

    def _load_transcript(self, path):
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read().strip()
        except OSError:
            text = ""
            self._set_transcript_text("(no se pudo leer el transcript)")
            self._current_transcript_dir = None
            return
        self._current_transcript_dir = os.path.dirname(path)
        self.transcript_title.configure(text=f"Transcripción — {os.path.basename(self._current_transcript_dir)}")
        if text:
            self._render_transcript(text)
        else:
            self._set_transcript_text("(transcripción vacía — no se detectó voz)")

    def _refresh_history(self):
        for w in self.history_frame.winfo_children():
            w.destroy()
        base = "recordings"
        if not os.path.isdir(base):
            return
        for entry in sorted(os.listdir(base), reverse=True)[:60]:
            path = os.path.join(base, entry, "transcript.txt")
            if os.path.isfile(path):
                date_part, _, time_part = entry.partition("_")
                label = f"{date_part}\n{time_part.replace('-', ':')}"
                ctk.CTkButton(
                    self.history_frame, text=label, anchor="w", height=40,
                    font=ctk.CTkFont(size=11), fg_color="transparent", hover_color=SURFACE_ALT,
                    text_color=TEXT_DIM, command=lambda p=path: self._load_transcript(p),
                ).pack(fill="x", pady=1)

    def _copy_transcript(self):
        text = self.transcript_box.get("1.0", "end").strip()
        self.clipboard_clear()
        self.clipboard_append(text)

    def _open_folder(self):
        if self._current_transcript_dir and os.path.isdir(self._current_transcript_dir):
            os.startfile(self._current_transcript_dir)

    def _on_close(self):
        self.controller.shutdown()
        self.destroy()


def main():
    if not single_instance.acquire():
        print("EchoNote is already running.")
        return
    App().mainloop()


if __name__ == "__main__":
    main()
