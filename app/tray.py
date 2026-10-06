"""Tray front-end (Fase 3): invisible by default, one dot in the tray whose
color is the state. All the actual logic lives in RecordingController —
this module only draws state and wires the menu.
"""
import sys

import pystray
from PIL import Image, ImageDraw

from app import config, single_instance
from app.controller import IDLE, LOADING, PAUSED, RECORDING, TRANSCRIBING, RecordingController
from app.transcriber import MODELS

STATE_COLORS = {
    LOADING: (200, 180, 0, 255),
    IDLE: (50, 170, 80, 255),
    RECORDING: (220, 40, 40, 255),
    PAUSED: (140, 140, 150, 255),
    TRANSCRIBING: (230, 150, 20, 255),
}

STATE_LABELS = {
    LOADING: "AnotaVoz — loading model...",
    IDLE: "AnotaVoz — ready",
    RECORDING: "AnotaVoz — recording",
    PAUSED: "AnotaVoz — paused",
    TRANSCRIBING: "AnotaVoz — transcribing...",
}


def _icon_image(color):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((8, 8, 56, 56), fill=color)
    return img


class TrayApp:
    def __init__(self, hotkey=None):
        self._was_transcribing = False
        self.controller = RecordingController(
            hotkey=hotkey, on_state=self._on_state, on_log=self._on_log,
        )
        self._icon = pystray.Icon(
            "AnotaVoz",
            icon=_icon_image(STATE_COLORS[LOADING]),
            title=STATE_LABELS[LOADING],
            menu=pystray.Menu(
                pystray.MenuItem("Start/stop recording", self._on_toggle),
                pystray.MenuItem("Pause/resume", self._on_pause,
                                 enabled=lambda item: self.controller.state in (RECORDING, PAUSED)),
                pystray.MenuItem("Model", pystray.Menu(*self._model_menu_items())),
                pystray.MenuItem("Quit", self._on_quit),
            ),
        )

    def _select_model(self, name):
        # pystray inspects the action's argcount and requires exactly
        # (icon, item) — a default-arg closure trick adds a 3rd declared
        # param and pystray rejects it, so the name gets bound here instead.
        def _handler(icon, item):
            self.controller.set_model(name)
        return _handler

    def _model_menu_items(self):
        items = []
        for name, (_, _, size_mb) in MODELS.items():
            items.append(pystray.MenuItem(
                f"{name} (~{size_mb}MB)",
                self._select_model(name),
                checked=lambda item, name=name: self.controller.model_name == name,
                radio=True,
            ))
        return items

    def _on_state(self, state):
        self._icon.icon = _icon_image(STATE_COLORS[state])
        self._icon.title = STATE_LABELS[state]
        if state == IDLE and self._was_transcribing:
            try:
                self._icon.notify("Transcript ready", "AnotaVoz")
            except NotImplementedError:
                pass  # not every platform backend supports notify()
        self._was_transcribing = state == TRANSCRIBING

    def _on_log(self, msg):
        print(msg, flush=True)

    def _on_toggle(self, icon, item):
        self.controller.toggle()

    def _on_pause(self, icon, item):
        self.controller.pause()

    def _on_quit(self, icon, item):
        # Ordered shutdown, unlike the prototype's os._exit(0): release the
        # hotkey first so nothing can fire toggle() on a dead controller,
        # then stop the icon loop so run() returns normally.
        self.controller.shutdown()
        icon.stop()

    def run(self):
        self.controller.start()
        self._icon.run()  # blocks until _on_quit() calls icon.stop()


def main():
    config.migrate_legacy_dir()
    if not single_instance.acquire():
        print("AnotaVoz is already running (check your system tray).")
        sys.exit(1)
    TrayApp().run()


if __name__ == "__main__":
    main()
