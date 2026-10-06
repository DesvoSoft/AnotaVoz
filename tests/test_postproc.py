from app.postproc import collapse_repeats, drop_echo, tidy_text


def cue(s, e, t):
    return {"start": s, "end": e, "text": t}


def test_drop_echo_removes_matching_mic_cue():
    mic = [cue(1000, 3000, "Hola, ¿cómo están todos?"), cue(5000, 7000, "Yo voy a comentar algo")]
    sys = [cue(1100, 3100, "hola cómo están todos")]
    kept = drop_echo(mic, sys)
    assert [c["text"] for c in kept] == ["Yo voy a comentar algo"]


def test_drop_echo_keeps_overlapping_but_different_text():
    mic = [cue(1000, 3000, "Estoy de acuerdo")]
    sys = [cue(1000, 3000, "Entonces cerramos la reunión")]
    assert drop_echo(mic, sys) == mic


def test_drop_echo_full_echo_leaves_empty_not_error():
    mic = [cue(0, 2000, "buenos días")]
    sys = [cue(0, 2000, "Buenos días.")]
    assert drop_echo(mic, sys) == []


def test_drop_echo_handles_empty_inputs():
    assert drop_echo([], [cue(0, 1, "x")]) == []
    assert drop_echo([cue(0, 1000, "x")], []) == [cue(0, 1000, "x")]


def test_collapse_repeats_limits_runs():
    cues = [cue(i, i + 1, "you") for i in range(6)] + [cue(10, 11, "otra cosa")]
    out = collapse_repeats(cues, max_run=2)
    assert [c["text"] for c in out] == ["you", "you", "otra cosa"]


def test_tidy_text_spaces_and_capitals():
    assert tidy_text("hola  mundo. esto  es   una prueba. ¿sí? claro") == "hola mundo. Esto es una prueba. ¿sí? Claro"


def test_collapse_word_loops_inside_one_cue():
    from app.postproc import collapse_word_loops
    text = "Ay, no tengo persona. " + "No, " * 20 + "no. Después seguimos."
    out = collapse_word_loops(text, max_run=3)
    assert out.lower().count("no,") + out.lower().count("no.") <= 4
    assert out.startswith("Ay, no tengo persona.") and out.endswith("Después seguimos.")


def test_collapse_word_loops_ngram_and_untouched_text():
    from app.postproc import collapse_word_loops
    assert collapse_word_loops("sí claro " * 8, max_run=2).count("sí claro") == 2
    plain = "Eso no, no y no. Pero sí."
    assert collapse_word_loops(plain) == plain
