"""Address keywords (Mahallesi, Cad., No, D: ...) and their abbreviations.

The data lives in ``data/abbreviations.json`` so contributors can add new
spellings without touching Python code. This module loads that file once,
checks it, and builds a lookup table keyed by :func:`alias_key`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from types import MappingProxyType

from tradres.normalization import ascii_key

__all__ = [
    "KINDS",
    "Abbreviation",
    "AbbreviationDataError",
    "alias_key",
    "build_index",
    "load_abbreviations",
    "lookup",
]

#: Every keyword kind the parser knows. Names match the address fields.
KINDS: frozenset[str] = frozenset(
    {
        "mahalle",
        "cadde",
        "sokak",
        "bulvar",
        "site",
        "apartman",
        "blok",
        "bina_no",
        "kat",
        "daire",
        "posta_kodu",
    }
)

_DATA_FILE = "abbreviations.json"
_NAME_WORDS_FILE = "name_words.json"
_ASCII_NAMES_FILE = "ascii_names.json"
_COUNTRY_NAMES_FILE = "country_names.json"
_DESCRIPTION_WORDS_FILE = "description_words.json"


@dataclass(frozen=True)
class Abbreviation:
    """One address keyword.

    Attributes:
        kind: Which address part it marks, e.g. ``"sokak"``. Always in :data:`KINDS`.
        short: Spelling used when formatting, e.g. ``"Sk."``.
        long: Full word, e.g. ``"Sokağı"``.
    """

    kind: str
    short: str
    long: str


class AbbreviationDataError(ValueError):
    """The abbreviation data file is malformed."""


def alias_key(token: str) -> str:
    """Return the lookup key for a single word.

    Like :func:`~tradres.normalization.ascii_key`, but dots, colons and
    inner spaces are removed too, so ``"Sk."``, ``"SK"``, ``"sk:"`` and
    ``"P.K."`` -> ``"sk"`` / ``"pk"``.

    >>> alias_key("Sokağı:")
    'sokagi'
    """
    return ascii_key(token).replace(" ", "")


def build_index(raw: Mapping[str, object]) -> dict[str, Abbreviation]:
    """Check parsed JSON data and return an ``alias key -> Abbreviation`` table.

    Keys starting with ``_`` (like ``"_comment"``) are ignored.

    Raises:
        AbbreviationDataError: if a kind is unknown, a field is missing or has
            the wrong type, an alias is empty or has several words, or the
            same alias appears twice.
    """
    index: dict[str, Abbreviation] = {}
    for kind, entry in raw.items():
        if kind.startswith("_"):
            continue
        if kind not in KINDS:
            raise AbbreviationDataError(f"unknown kind {kind!r}; expected one of {sorted(KINDS)}")
        abbreviation, aliases = _parse_entry(kind, entry)
        for alias in aliases:
            key = alias_key(alias)
            if not key:
                raise AbbreviationDataError(f"{kind}: alias {alias!r} is empty after normalizing")
            if " " in ascii_key(alias):
                raise AbbreviationDataError(f"{kind}: alias {alias!r} must be a single word")
            if key in index:
                other = index[key].kind
                raise AbbreviationDataError(
                    f"alias {alias!r} (key {key!r}) is listed under both {other!r} and {kind!r}"
                    if other != kind
                    else f"{kind}: alias {alias!r} (key {key!r}) is listed twice"
                )
            index[key] = abbreviation
    return index


def _parse_entry(kind: str, entry: object) -> tuple[Abbreviation, list[str]]:
    if not isinstance(entry, dict):
        raise AbbreviationDataError(f"{kind}: entry must be an object")
    short, long, aliases = entry.get("short"), entry.get("long"), entry.get("aliases")
    if not isinstance(short, str) or not short:
        raise AbbreviationDataError(f"{kind}: 'short' must be a non-empty string")
    if not isinstance(long, str) or not long:
        raise AbbreviationDataError(f"{kind}: 'long' must be a non-empty string")
    if (
        not isinstance(aliases, list)
        or not aliases
        or not all(isinstance(alias, str) for alias in aliases)
    ):
        raise AbbreviationDataError(f"{kind}: 'aliases' must be a non-empty list of strings")
    return Abbreviation(kind=kind, short=short, long=long), aliases


@cache
def load_abbreviations() -> Mapping[str, Abbreviation]:
    """Load the bundled data file once and return the read-only lookup table.

    ``@cache`` means the file is read on the first call only; later calls
    return the same object.
    """
    text = (files("tradres") / "data" / _DATA_FILE).read_text(encoding="utf-8")
    raw = json.loads(text)
    if not isinstance(raw, dict):
        raise AbbreviationDataError(f"{_DATA_FILE}: top level must be an object")
    return MappingProxyType(build_index(raw))


@cache
def load_name_words() -> Mapping[str, str]:
    """Short forms of words inside names, such as "gmk". See data/name_words.json."""
    text = (files("tradres") / "data" / _NAME_WORDS_FILE).read_text(encoding="utf-8")
    raw = json.loads(text)
    return MappingProxyType(
        {alias_key(key): value for key, value in raw.items() if not key.startswith("_")}
    )


@cache
def load_ascii_names() -> frozenset[str]:
    """Names that are never respelled, as keys. See data/ascii_names.json."""
    text = (files("tradres") / "data" / _ASCII_NAMES_FILE).read_text(encoding="utf-8")
    return frozenset(alias_key(name) for name in json.loads(text)["names"])


@cache
def load_country_names() -> frozenset[str]:
    """Names of the country, as keys. See data/country_names.json."""
    text = (files("tradres") / "data" / _COUNTRY_NAMES_FILE).read_text(encoding="utf-8")
    return frozenset(alias_key(name) for name in json.loads(text)["names"])


@cache
def load_description_words() -> frozenset[str]:
    """Keys of the words that end a direction. See data/description_words.json."""
    text = (files("tradres") / "data" / _DESCRIPTION_WORDS_FILE).read_text(encoding="utf-8")
    return frozenset(alias_key(word) for word in json.loads(text)["words"])


def lookup(token: str) -> Abbreviation | None:
    """Return the keyword a single word stands for, or ``None``.

    >>> lookup("Cd.")
    Abbreviation(kind='cadde', short='Cad.', long='Caddesi')
    >>> lookup("SOKAGI").kind
    'sokak'
    >>> lookup("Kızılay") is None
    True
    """
    return load_abbreviations().get(alias_key(token))
