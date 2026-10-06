from app.api import Api


class FakeController:
    def __init__(self):
        self.state = "idle"
        self.model_name = "small"
        self.toggled = 0
        self.started = 0
        self.set = None

    def toggle(self):
        self.toggled += 1

    def start(self):
        self.started += 1

    def shutdown(self):
        pass

    def set_model(self, n):
        self.set = n

    def has_model(self, n):
        return n == "small"

    def download_model(self, n, p, d):
        p(10.0)
        d(True, "ok")


def make():
    events = []
    api = Api(controller_factory=lambda **kw: FakeController(), emit=lambda n, p=None: events.append((n, p)))
    return api, events


def test_bootstrap_shape():
    api, _ = make()
    b = api.bootstrap()
    assert {"state", "model", "models", "gpu", "settings", "history"} <= set(b)
    assert any(m["name"] == "small" and m["installed"] for m in b["models"])


def test_toggle_delegates():
    api, _ = make()
    api.toggle()
    assert api._controller.toggled == 1


def test_start_is_idempotent():
    api, _ = make()
    api._start()
    api._start()
    assert api._controller.started == 1


def test_levels_are_throttled():
    api, events = make()
    for _ in range(200):
        api._on_level("microphone", 0.5)
    assert 0 < sum(1 for n, _ in events if n == "levels") < 200


def test_download_emits_progress_and_done():
    api, events = make()
    api.download_model("large-v3-turbo")
    kinds = [p for n, p in events if n == "model_download"]
    assert kinds[0]["pct"] == 10.0 and kinds[-1]["done"] is True


def test_bad_history_id_returns_error_not_exception():
    api, _ = make()
    assert api.load_transcript("../etc")["error"]


def test_close_when_idle_is_allowed():
    api, _ = make()
    assert api._request_close() is True


def test_close_while_recording_stops_and_defers():
    api, _ = make()
    api._controller.state = "recording"
    destroyed = []
    api._on_close_ready = lambda: destroyed.append(1)
    assert api._request_close() is False
    assert api._controller.toggled == 1  # stop + transcribe, never drop the audio
    api._on_state("transcribing")
    assert not destroyed
    api._on_state("idle")
    assert destroyed == [1]


def test_close_while_transcribing_defers_without_toggle():
    api, _ = make()
    api._controller.state = "transcribing"
    destroyed = []
    api._on_close_ready = lambda: destroyed.append(1)
    assert api._request_close() is False and api._controller.toggled == 0
    api._on_state("idle")
    assert destroyed == [1]


def test_async_emitter_never_blocks_caller():
    import threading
    from app.api import AsyncEmitter
    gate, got = threading.Event(), []

    def slow(name, payload=None):
        gate.wait(2)
        got.append(name)
    em = AsyncEmitter(slow)
    em("levels", {"microphone": 0.1})  # must return immediately although slow() is stuck
    assert got == []
    gate.set()
    em.flush(2)
    assert got == ["levels"]


def test_open_folder_rejects_bad_ids():
    api, _ = make()
    assert api.open_folder("..")["error"]
