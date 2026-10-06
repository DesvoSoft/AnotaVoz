from app.wer import wer


def test_identical_is_zero():
    assert wer("Hola, mundo.", "hola mundo") == 0.0


def test_one_substitution_in_four():
    assert wer("uno dos tres cuatro", "uno dos tres cinco") == 0.25


def test_empty_reference():
    assert wer("", "") == 0.0
    assert wer("", "algo") == 1.0
