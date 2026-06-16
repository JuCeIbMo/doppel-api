from app.services.phone import normalize_phone


def test_normalize_strips_symbols():
    assert normalize_phone("+52 1 234-567 8900") == "5212345678900"


def test_normalize_empty():
    assert normalize_phone("") == ""


def test_normalize_non_numeric():
    assert normalize_phone("abc") == ""
