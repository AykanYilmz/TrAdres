"""Numbered fields: bina no, kat, daire and posta kodu."""

from __future__ import annotations

import re
from collections.abc import Sequence

from tradres.abbreviations import lookup
from tradres.extractors import Extraction
from tradres.normalization import tr_title, tr_upper
from tradres.tokenizer import Token, TokenKind, street_keyword

__all__ = ["extract_numbers"]

_GLUED = re.compile(r"([dk])(\d{1,3})")  # "d4", "k2": flat and floor without a space
_POSTAL_CODE = re.compile(r"(0[1-9]|[1-7]\d|8[01])\d{3}")  # first two digits: plate code 01-81
_FLOOR_WORDS = frozenset({"zemin", "giris", "bodrum", "asma", "cati"})
_BASEMENT_FLOOR = re.compile(r"[bB]\d")
_MIN_ROAD_DIGITS = 3  # "D 100" is a road; "D 12" is flat 12


def _digits(token: Token) -> str:
    return token.text.rstrip(".")


def _is_labelled(token: Token) -> bool:
    """True for "D:" and "Daire", False for a bare "D", which could be a road."""
    return token.text.endswith(":") or len(token.key) > 1


def _flat_after(token: Token, value: Token) -> bool:
    return _is_labelled(token) or len(_digits(value)) < _MIN_ROAD_DIGITS


def _floor_after(token: Token, value: Token) -> bool:
    if value.is_number:
        return True
    return _is_labelled(token) and (
        value.key in _FLOOR_WORDS or _BASEMENT_FLOOR.fullmatch(value.text) is not None
    )


def _floor_value(value: Token) -> str:
    if value.is_number:
        return _digits(value)
    return tr_upper(value.text) if _BASEMENT_FLOOR.fullmatch(value.text) else tr_title(value.text)


class _Scanner:
    """Walks over the tokens once. A field keeps its first value; a later value
    stays free and ends up in ``kalan``, so it is never silently lost."""

    def __init__(self, tokens: Sequence[Token]) -> None:
        self.tokens = tokens
        self.fields: dict[str, str] = {}
        self.used: set[int] = set()

    def at(self, index: int) -> Token | None:
        return self.tokens[index] if 0 <= index < len(self.tokens) else None

    def take(self, field: str, value: str, *indexes: int) -> None:
        self.fields[field] = value
        self.used.update(indexes)

    def building(self, index: int) -> None:
        """``No:`` at ``index``, then 5, 5/3 or 7/A."""
        value = self.at(index + 1)
        if value is None or not value.is_number or "bina_no" in self.fields:
            return
        before = self.at(index - 1)
        if before is not None and before.key == "bina":  # "Bina No: 5"
            self.used.add(index - 1)
        number, slash, flat = _digits(value).partition("/")
        if slash and "daire" not in self.fields:
            self.take("bina_no", number, index, index + 1)
            self.take("daire", flat, index + 1)
            return
        if slash:  # the flat is already known, so keep the whole value: nothing is lost
            self.take("bina_no", _digits(value), index, index + 1)
            return
        mark, letter = self.at(index + 2), self.at(index + 3)
        if mark and mark.text == "/" and letter and len(letter.text) == 1:
            self.take("bina_no", f"{number}/{letter.text}", index, index + 1, index + 2, index + 3)
        else:
            self.take("bina_no", number, index, index + 1)

    def labelled(self, index: int) -> None:
        token = self.tokens[index]
        glued = _GLUED.fullmatch(token.key)
        if glued:
            field = "daire" if glued[1] == "d" else "kat"
            if field not in self.fields:
                self.take(field, glued[2], index)
            return
        found = lookup(token.text) if token.kind is TokenKind.WORD else None
        if found is None:
            return
        if found.kind == "bina_no":
            self.building(index)
            return
        if found.kind not in ("daire", "kat"):
            return
        # "Daire No: 3": skip the "No". A bare "D" or "K" keeps its own rule,
        # because in "Blok D No:5" the 5 is the building number.
        has_no_word = _is_labelled(token) and self.is_number_word(index + 1)
        last = index + 2 if has_no_word else index + 1
        value = self.at(last)
        if value is None or found.kind in self.fields:
            return
        if found.kind == "daire" and value.is_number and (has_no_word or _flat_after(token, value)):
            self.take("daire", _digits(value), *range(index, last + 1))
        elif found.kind == "kat" and _floor_after(token, value):
            self.take("kat", _floor_value(value), *range(index, last + 1))

    def is_number_word(self, index: int) -> bool:
        token = self.at(index)
        found = lookup(token.text) if token is not None and token.kind is TokenKind.WORD else None
        return found is not None and found.kind == "bina_no"

    def postal_label(self, index: int) -> None:
        """``PK 14100``, ``P.K. 14100`` or ``Posta Kodu: 14100``."""
        token, following = self.tokens[index], self.at(index + 1)
        steps = 0
        if token.key == "pk":
            steps = 1
        elif token.key == "posta" and following and following.key == "kodu":
            steps = 2
        value = self.at(index + steps)
        if "posta_kodu" in self.fields:
            return
        if steps and value and _POSTAL_CODE.fullmatch(value.text):
            self.take("posta_kodu", value.text, *range(index, index + steps + 1))

    def bare_values(self) -> None:
        """Unlabelled ``12/8`` and postal codes, after the labelled values."""
        for index, token in enumerate(self.tokens):
            following = self.at(index + 1)
            if index in self.used or not token.is_number:
                continue
            if following and (street_keyword(following) or following.key == "nolu"):
                continue  # "1752/3 Sk.", "64023 Sokak": a street number
            if _POSTAL_CODE.fullmatch(token.text):
                if "posta_kodu" not in self.fields:
                    self.take("posta_kodu", token.text, index)
            elif "/" in token.text and not {"bina_no", "daire"} & set(self.fields):
                number, _, flat = token.text.partition("/")
                self.take("bina_no", number, index)
                self.take("daire", flat, index)


def extract_numbers(tokens: Sequence[Token]) -> Extraction:
    """Find the numbered fields.

    Bare ``D`` followed by three digits stays free: ``D 100`` is a road.

    >>> from tradres.tokenizer import tokenize
    >>> extract_numbers(tokenize("Gül Sk. No:5/3 Kat:2")).fields
    {'bina_no': '5', 'daire': '3', 'kat': '2'}
    >>> extract_numbers(tokenize("D 100 karayolu üzeri")).fields
    {}
    """
    scanner = _Scanner(tokens)
    for index in range(len(tokens)):
        if index not in scanner.used:
            scanner.postal_label(index)
        if index not in scanner.used:
            scanner.labelled(index)
    scanner.bare_values()
    return Extraction(fields=scanner.fields, used=frozenset(scanner.used))
