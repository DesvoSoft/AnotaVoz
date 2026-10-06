from app.session import group_by_turn, merge_transcripts


def cue(s, e, t):
    return {"start": s, "end": e, "text": t}


def test_merge_drops_echo_and_orders():
    mic = [cue(1000, 3000, "hola a todos"), cue(8000, 9000, "yo sigo")]
    sys = [cue(1000, 3000, "Hola a todos."), cue(4000, 6000, "gracias por venir")]
    tagged = merge_transcripts(mic, sys)
    assert [(t[2], t[3]) for t in tagged] == [("OTROS", "Hola a todos."), ("OTROS", "gracias por venir"), ("YO", "yo sigo")]


def test_merge_total_echo_mic_empty_ok():
    mic = [cue(0, 2000, "buenos días")]
    sys = [cue(0, 2000, "buenos días")]
    tagged = merge_transcripts(mic, sys)
    assert [t[2] for t in tagged] == ["OTROS"]
    assert group_by_turn(tagged)[0]["speaker"] == "OTROS"


def test_merge_collapses_whisper_loop():
    sys = [cue(i * 1000, i * 1000 + 900, "you") for i in range(8)]
    assert len(merge_transcripts([], sys)) == 2


def test_merge_collapses_loop_inside_cue():
    sys = [cue(0, 5000, "Ay no tengo persona. " + "No, " * 30 + "después seguimos")]
    tagged = merge_transcripts([], sys)
    assert len(tagged[0][3]) < 80
