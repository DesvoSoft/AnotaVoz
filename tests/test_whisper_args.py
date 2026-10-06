from app.transcriber import build_whisper_args, normalize_prompt


def args(**kw):
    base = dict(whisper_cli="w.exe", model_path="m.bin", wav="a.wav", prefix="p", lang="es", threads=4)
    base.update(kw)
    return build_whisper_args(**base)


def test_decoding_flags_present():
    a = args()
    assert a[a.index("-bs") + 1] == "5" and a[a.index("-bo") + 1] == "5"
    assert a[a.index("-mc") + 1] == "64"


def test_cpu_vs_gpu():
    assert "-ng" in args()
    g = args(use_gpu=True, gpu_index=1)
    assert "-ng" not in g and g[g.index("-dev") + 1] == "1"


def test_prompt_is_single_argument():
    a = args(prompt='Daniel "Dani" Pérez\nSIGEC')
    assert a[a.index("--prompt") + 1] == 'Daniel "Dani" Pérez SIGEC'


def test_normalize_prompt_truncates_and_empties():
    assert normalize_prompt("   ") is None
    assert len(normalize_prompt("x" * 1000)) <= 300
    assert normalize_prompt(None) is None


def test_compose_prompt_keeps_vocabulary_when_carry_is_long():
    from app.transcriber import compose_prompt
    p = compose_prompt("SIGEC Dani", "x" * 300)
    assert p.startswith("SIGEC Dani") and len(p) <= 300


def test_compose_prompt_handles_missing_parts():
    from app.transcriber import compose_prompt
    assert compose_prompt(None, None) is None
    assert compose_prompt("vocab", None) == "vocab"
    assert compose_prompt(None, "carry") == "carry"
