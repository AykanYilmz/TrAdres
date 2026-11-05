"""Tests for tradres.tokenizer."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tradres.tokenizer import TokenKind, street_keyword, tokenize


def _texts(text: str) -> list[str]:
    return [token.text for token in tokenize(text)]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Gül Sk. No:5/3", ["Gül", "Sk.", "No:", "5/3"]),
        ("Merkez/Bolu", ["Merkez", "/", "Bolu"]),
        ("Ankara,Batıkent", ["Ankara", ",", "Batıkent"]),
        ("Kızılay(Merkez)", ["Kızılay", "(", "Merkez", ")"]),
        ("23nisan", ["23", "nisan"]),
        ("Bolu - Merkez", ["Bolu", "-", "Merkez"]),
        ("B-3 Blok", ["B-3", "Blok"]),
        ("", []),
    ],
)
def test_tokenize(text: str, expected: list[str]) -> None:
    assert _texts(text) == expected


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("5", TokenKind.NUMBER),
        ("12A", TokenKind.NUMBER),
        ("1923.", TokenKind.NUMBER),
        ("5/3", TokenKind.NUMBER),
        ("B3", TokenKind.WORD),
        ("Kızılay", TokenKind.WORD),
        (",", TokenKind.SEPARATOR),
        ("-", TokenKind.SEPARATOR),
    ],
)
def test_token_kinds(text: str, kind: TokenKind) -> None:
    (token,) = tokenize(text)
    assert token.kind is kind


def test_token_key_ignores_case_letters_and_dots() -> None:
    assert tokenize("SOKAĞI:")[0].key == "sokagi"
    assert tokenize("P.K.")[0].key == "pk"


@pytest.mark.parametrize(
    ("text", "kind"),
    [("Mah.", "mahalle"), ("Köyü", "mahalle"), ("Cd.", "cadde"), ("Apt", "apartman")],
)
def test_street_keyword(text: str, kind: str) -> None:
    found = street_keyword(tokenize(text)[0])
    assert found is not None
    assert found.kind == kind


@pytest.mark.parametrize("text", ["No:", "D:", "Kızılay", "5", ","])
def test_not_street_keyword(text: str) -> None:
    assert street_keyword(tokenize(text)[0]) is None


@given(st.text())
def test_tokens_are_never_empty(text: str) -> None:
    assert all(token.text for token in tokenize(text))
