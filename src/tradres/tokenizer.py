"""Split an address into tokens, the small pieces the extractors work on."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from functools import cache

from tradres.abbreviations import Abbreviation, alias_key, load_abbreviations, lookup
from tradres.matching import closest
from tradres.normalization import clean

__all__ = ["STREET_KINDS", "Token", "TokenKind", "street_keyword", "tokenize"]

#: Keywords that follow a name: "Kızılay Mahallesi", "Gül Sokak", "B Blok".
STREET_KINDS = frozenset({"mahalle", "cadde", "sokak", "bulvar", "site", "apartman", "blok"})

_TOKEN = re.compile(r"[,;()/]|[^\s,;()]+")
_SEPARATORS = frozenset(",;()/-")
_MIN_KEYWORD_LENGTH = 6  # only full forms such as "Mahallesi" are corrected
# 5, 12A, 1923. (ordinal) or 5/3 (building/flat, or a street number in İzmir)
_NUMBER = re.compile(r"\d+[^\W\d_]?\.?|\d+/\d+")


class TokenKind(Enum):
    WORD = "word"
    NUMBER = "number"
    SEPARATOR = "separator"


@dataclass(frozen=True)
class Token:
    """One piece of the address.

    Attributes:
        text: As written, after :func:`~tradres.normalization.clean`.
        kind: Word, number or separator.
        key: Lookup key: no case, Turkish letters or punctuation.
    """

    text: str
    kind: TokenKind
    key: str

    @property
    def is_number(self) -> bool:
        return self.kind is TokenKind.NUMBER

    @property
    def is_separator(self) -> bool:
        return self.kind is TokenKind.SEPARATOR


def _token(text: str) -> Token:
    if text in _SEPARATORS:
        kind = TokenKind.SEPARATOR
    elif _NUMBER.fullmatch(text):
        kind = TokenKind.NUMBER
    else:
        kind = TokenKind.WORD
    return Token(text=text, kind=kind, key=alias_key(text))


def tokenize(text: str) -> tuple[Token, ...]:
    """Clean ``text`` and split it.

    >>> [token.text for token in tokenize("Gül Sk.No:5/3,Merkez/Bolu")]
    ['Gül', 'Sk.', 'No:', '5/3', ',', 'Merkez', '/', 'Bolu']
    """
    return tuple(_token(piece) for piece in _TOKEN.findall(clean(text)))


@cache
def _long_forms() -> dict[str, Abbreviation]:
    keywords = (a for a in load_abbreviations().values() if a.kind in STREET_KINDS)
    return {alias_key(a.long): a for a in keywords if len(a.long) >= _MIN_KEYWORD_LENGTH}


@cache
def _misspelled_keyword(key: str) -> Abbreviation | None:
    """A typo in a full keyword: "Mahalesi", "Cadesi". The first letter must be right."""
    if len(key) < _MIN_KEYWORD_LENGTH:
        return None
    forms = _long_forms()
    hit = closest(key, [form for form in forms if form[0] == key[0]])
    return forms[hit] if hit is not None else None


def street_keyword(token: Token) -> Abbreviation | None:
    """The keyword this token stands for, if it is one of :data:`STREET_KINDS`.

    >>> street_keyword(tokenize("Mahalesi")[0]).kind
    'mahalle'
    """
    if token.kind is not TokenKind.WORD:
        return None
    found = lookup(token.text)
    if found is None:
        return _misspelled_keyword(token.key)
    return found if found.kind in STREET_KINDS else None
