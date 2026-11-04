"""Tests for tradres.normalization."""

from __future__ import annotations

import re

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tradres.normalization import ascii_key, clean, normalize, tr_lower, tr_title, tr_upper

TR_LOWER_LETTERS = "abcçdefgğhıijklmnoöprsştuüvyz"
TR_UPPER_LETTERS = "ABCÇDEFGĞHIİJKLMNOÖPRSŞTUÜVYZ"

# Text made only of Turkish letters, digits, spaces and common address punctuation.
turkish_text = st.text(alphabet=TR_LOWER_LETTERS + TR_UPPER_LETTERS + "0123456789 .,:/-'")
turkish_words = st.text(alphabet=TR_LOWER_LETTERS + TR_UPPER_LETTERS + " ")


# --------------------------------------------------------------------------- #
# tr_lower / tr_upper
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("I", "ı"),
        ("İ", "i"),
        ("KIZILAY", "kızılay"),
        ("İSTANBUL", "istanbul"),
        ("ŞİŞLİ", "şişli"),
        ("IĞDIR", "ığdır"),
        ("ÇANKAYA", "çankaya"),
        ("Atatürk", "atatürk"),
        ("I\u0307STANBUL", "istanbul"),  # decomposed İ (I + combining dot above)
        ("", ""),
    ],
)
def test_tr_lower(text: str, expected: str) -> None:
    assert tr_lower(text) == expected


def test_tr_lower_differs_from_str_lower() -> None:
    # The whole reason this function exists:
    assert "KIZILAY".lower() == "kizilay"
    assert tr_lower("KIZILAY") == "kızılay"
    # str.lower turns "İ" into "i" + combining dot (2 characters):
    assert len("İ".lower()) == 2
    assert tr_lower("İ") == "i"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("i", "İ"),
        ("ı", "I"),
        ("istanbul", "İSTANBUL"),
        ("kızılay", "KIZILAY"),
        ("ığdır", "IĞDIR"),
        ("şişli", "ŞİŞLİ"),
        ("", ""),
    ],
)
def test_tr_upper(text: str, expected: str) -> None:
    assert tr_upper(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("istanbul", "İstanbul"),
        ("IŞIKLAR CADDESİ", "Işıklar Caddesi"),
        ("23 nisan", "23 Nisan"),
        ("(merkez)", "(Merkez)"),
        ("gazi  mustafa", "Gazi  Mustafa"),  # does not collapse spaces
        ("1923", "1923"),
        ("", ""),
    ],
)
def test_tr_title(text: str, expected: str) -> None:
    assert tr_title(text) == expected


@given(st.text())
def test_tr_lower_is_idempotent(text: str) -> None:
    once = tr_lower(text)
    assert tr_lower(once) == once


@given(st.text())
def test_tr_upper_is_idempotent(text: str) -> None:
    once = tr_upper(text)
    assert tr_upper(once) == once


@given(turkish_words)
def test_lower_upper_round_trip_on_turkish_letters(text: str) -> None:
    assert tr_lower(tr_upper(text)) == tr_lower(text)
    assert tr_upper(tr_lower(text)) == tr_upper(text)
    assert len(tr_lower(text)) == len(text) == len(tr_upper(text))


# --------------------------------------------------------------------------- #
# ascii_key
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Çankaya", "cankaya"),
        ("ŞİŞLİ", "sisli"),
        ("Kızılay", "kizilay"),
        ("KIZILAY", "kizilay"),
        ("Iğdır", "igdir"),
        ("Gölbaşı", "golbasi"),
        ("Üsküdar", "uskudar"),
        ("Hâkimiyet-i Milliye", "hakimiyet i milliye"),
        ("Atatürk'ün", "ataturkun"),
        ("Atatürk\u2019ün", "ataturkun"),
        ("Gazi Mustafa Kemal Blv.", "gazi mustafa kemal blv"),
        ("  23 Nisan  ", "23 nisan"),
        ("Café", "cafe"),
        ("...", ""),
    ],
)
def test_ascii_key(text: str, expected: str) -> None:
    assert ascii_key(text) == expected


@pytest.mark.parametrize(
    "spellings",
    [
        ("Çankaya", "cankaya", "ÇANKAYA", "CANKAYA", "çankaya"),
        ("Şişli", "sisli", "ŞİŞLİ", "SISLI", "şisli"),
        ("Kızılay", "Kizilay", "KIZILAY", "kızılay"),
    ],
)
def test_ascii_key_merges_spellings(spellings: tuple[str, ...]) -> None:
    assert len({ascii_key(s) for s in spellings}) == 1


@given(st.text())
def test_ascii_key_output_is_plain_ascii(text: str) -> None:
    assert re.fullmatch(r"([a-z0-9]+( [a-z0-9]+)*)?", ascii_key(text))


@given(st.text())
def test_ascii_key_is_idempotent(text: str) -> None:
    once = ascii_key(text)
    assert ascii_key(once) == once


@given(turkish_text)
def test_ascii_key_ignores_case(text: str) -> None:
    assert ascii_key(tr_upper(text)) == ascii_key(text) == ascii_key(tr_lower(text))


# --------------------------------------------------------------------------- #
# clean / normalize
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Examples from the project brief
        (
            "Atatürk Mah. 23 Nisan Cad. No:5/3 Merkez/Bolu",
            "Atatürk Mah. 23 Nisan Cad. No: 5/3 Merkez / Bolu",
        ),
        (
            "ataturk mh 23nisan cd no 5 d 3 bolu merkez",
            "ataturk mh 23 nisan cd no 5 d 3 bolu merkez",
        ),
        (
            "CANKAYA/ANKARA kizilay mah gmk bulvarı 12/8",
            "CANKAYA / ANKARA kizilay mah gmk bulvarı 12/8",
        ),
        (
            "Yenimahalle Ankara,Batıkent , 1923.Cadde",
            "Yenimahalle Ankara, Batıkent, 1923. Cadde",
        ),
        # Colons, commas, semicolons
        ("No : 12 Kat:4 Daire:8", "No: 12 Kat: 4 Daire: 8"),
        ("a;b", "a; b"),
        # Slashes
        ("12 / 8", "12/8"),
        ("Merkez/ Bolu", "Merkez / Bolu"),
        ("B/3", "B / 3"),
        # Dots
        ("Atatürk Cad.No:5", "Atatürk Cad. No: 5"),
        ("Mah.Atatürk", "Mah. Atatürk"),
        ("Sk.5", "Sk. 5"),
        ("Mah.23nisan", "Mah. 23 nisan"),
        ("P.K. 12", "P.K. 12"),  # initials stay together
        ("5.3", "5.3"),
        # Digit / letter boundaries
        ("no5", "no 5"),
        ("kat4", "kat 4"),
        ("1923sk", "1923 sk"),
        ("5A", "5A"),  # building number with a letter
        ("B3", "B3"),  # block name
        # Parentheses
        ("Kızılay(Merkez)Ankara", "Kızılay (Merkez) Ankara"),
        ("( Toki )", "(Toki)"),
        # Whitespace and invisible characters
        ("  çok   boşluk\t\nvar  ", "çok boşluk var"),
        ("Kızı\u200blay", "Kızılay"),  # zero-width space
        ("Bolu\u00a0Merkez", "Bolu Merkez"),  # no-break space
        # Unicode unification
        ("Bolu \u2013 Merkez", "Bolu - Merkez"),  # en dash
        ("Atatürk\u2019ün", "Atatürk'ün"),
        ("\uff2e\uff4f\uff1a\uff15", "No: 5"),  # full-width characters
        ("", ""),
    ],
)
def test_clean(text: str, expected: str) -> None:
    assert clean(text) == expected


def test_clean_keeps_case() -> None:
    assert clean("KIZILAY mah") == "KIZILAY mah"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ÇANKAYA/ANKARA Kızılay Mah.No:12", "çankaya / ankara kızılay mah. no: 12"),
        ("İSTANBUL", "istanbul"),
        ("\u210c", "h"),  # NFKC turns this symbol into "H"; must still end lowercase
    ],
)
def test_normalize(text: str, expected: str) -> None:
    assert normalize(text) == expected


@given(st.text())
def test_clean_is_idempotent(text: str) -> None:
    once = clean(text)
    assert clean(once) == once


@given(st.text())
def test_normalize_is_idempotent(text: str) -> None:
    once = normalize(text)
    assert normalize(once) == once


@given(st.text())
def test_clean_output_has_no_extra_whitespace(text: str) -> None:
    out = clean(text)
    assert out == out.strip()
    assert "  " not in out
    assert all(char == " " or not char.isspace() for char in out)


@given(turkish_text)
def test_normalize_ignores_case(text: str) -> None:
    assert normalize(tr_upper(text)) == normalize(text)
