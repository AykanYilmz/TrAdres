"""Split an address into tokens, the small pieces the extractors work on."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from tradres.abbreviations import Abbreviation, alias_key, lookup
from tradres.normalization import clean

__all__ = ["STREET_KINDS", "Token", "TokenKind", "street_keyword", "tokenize"]

#: Keywords that follow a name: "Kızılay Mahallesi", "Gül Sokak", "B Blok".
STREET_KINDS = frozenset({"mahalle", "cadde", "sokak", "bulvar", "site", "apartman", "blok"})

_TOKEN = re.compile(r"[,;()/]|[^\s,;()]+")
_SEPARATORS = frozenset(",;()/-")
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


def street_keyword(token: Token) -> Abbreviation | None:
    """The keyword this token stands for, if it is one of :data:`STREET_KINDS`."""
    if token.kind is not TokenKind.WORD:
        return None
    found = lookup(token.text)
    return found if found is not None and found.kind in STREET_KINDS else None
