"""Tests for tradres.abbreviations."""

from __future__ import annotations

import json
from importlib.resources import files

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tradres.abbreviations import (
    KINDS,
    AbbreviationDataError,
    alias_key,
    build_index,
    load_abbreviations,
    lookup,
)


def _raw_data() -> dict[str, object]:
    text = (files("tradres") / "data" / "abbreviations.json").read_text(encoding="utf-8")
    data = json.loads(text)
    assert isinstance(data, dict)
    return data


# --------------------------------------------------------------------------- #
# Lookups against the bundled data
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("token", "kind"),
    [
        # Spellings from the project brief
        ("Mah.", "mahalle"),
        ("Mh.", "mahalle"),
        ("Mahallesi", "mahalle"),
        ("MAHALLESİ", "mahalle"),
        ("Cad.", "cadde"),
        ("Cd.", "cadde"),
        ("Caddesi", "cadde"),
        ("Sok.", "sokak"),
        ("Sk.", "sokak"),
        ("Sokağı", "sokak"),
        ("sokagi", "sokak"),
        ("Blv.", "bulvar"),
        ("Bulvarı", "bulvar"),
        ("BULVARI", "bulvar"),
        ("Apt.", "apartman"),
        ("Apartmanı", "apartman"),
        ("Sit.", "site"),
        ("Sitesi", "site"),
        ("Bl.", "blok"),
        ("Blok", "blok"),
        ("No:", "bina_no"),
        ("No", "bina_no"),
        ("D:", "daire"),
        ("Daire", "daire"),
        ("K:", "kat"),
        ("Kat", "kat"),
        ("P.K.", "posta_kodu"),
    ],
)
def test_lookup_known_tokens(token: str, kind: str) -> None:
    found = lookup(token)
    assert found is not None
    assert found.kind == kind


@pytest.mark.parametrize("token", ["Kızılay", "Ankara", "5", "", "...", "da", "bul"])
def test_lookup_unknown_tokens(token: str) -> None:
    assert lookup(token) is None


def test_lookup_returns_formatting_forms() -> None:
    found = lookup("sk")
    assert found is not None
    assert (found.short, found.long) == ("Sk.", "Sokağı")


def test_load_is_cached() -> None:
    assert load_abbreviations() is load_abbreviations()


def test_index_is_read_only() -> None:
    index = load_abbreviations()
    with pytest.raises(TypeError):
        index["new"] = index["sk"]  # type: ignore[index]


# --------------------------------------------------------------------------- #
# Consistency of the bundled data (guards contributor edits)
# --------------------------------------------------------------------------- #


def test_data_covers_every_kind() -> None:
    assert {abbr.kind for abbr in load_abbreviations().values()} == KINDS


@pytest.mark.parametrize("kind", sorted(KINDS))
def test_short_form_resolves_to_its_own_kind(kind: str) -> None:
    entry = _raw_data()[kind]
    assert isinstance(entry, dict)
    found = lookup(entry["short"])
    assert found is not None
    assert found.kind == kind


@pytest.mark.parametrize("kind", sorted(KINDS))
def test_single_word_long_form_resolves_to_its_own_kind(kind: str) -> None:
    entry = _raw_data()[kind]
    assert isinstance(entry, dict)
    long = entry["long"]
    if " " in long:
        pytest.skip(f"{long!r} has several words; lookups are per word")
    found = lookup(long)
    assert found is not None
    assert found.kind == kind


# --------------------------------------------------------------------------- #
# Validation errors in build_index
# --------------------------------------------------------------------------- #

_GOOD = {"short": "Sk.", "long": "Sokağı", "aliases": ["sk"]}


def test_build_index_ignores_comment_keys() -> None:
    index = build_index({"_comment": ["anything"], "sokak": _GOOD})
    assert set(index) == {"sk"}


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"sokakk": _GOOD}, "unknown kind"),
        ({"sokak": "Sk."}, "must be an object"),
        ({"sokak": {**_GOOD, "short": ""}}, "'short'"),
        ({"sokak": {**_GOOD, "long": 5}}, "'long'"),
        ({"sokak": {**_GOOD, "aliases": []}}, "'aliases'"),
        ({"sokak": {**_GOOD, "aliases": "sk"}}, "'aliases'"),
        ({"sokak": {**_GOOD, "aliases": ["sk", 3]}}, "'aliases'"),
        ({"sokak": {**_GOOD, "aliases": ["..."]}}, "empty"),
        ({"sokak": {**_GOOD, "aliases": ["sokak adı"]}}, "single word"),
        ({"sokak": {**_GOOD, "aliases": ["sk", "SK."]}}, "listed twice"),
        (
            {"sokak": _GOOD, "site": {"short": "Sit.", "long": "Sitesi", "aliases": ["Sk"]}},
            "both 'sokak' and 'site'",
        ),
    ],
)
def test_build_index_rejects_bad_data(raw: dict[str, object], message: str) -> None:
    with pytest.raises(AbbreviationDataError, match=message):
        build_index(raw)


# --------------------------------------------------------------------------- #
# alias_key
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("token", "expected"),
    [("Sk.", "sk"), ("SOKAĞI", "sokagi"), ("No:", "no"), ("P.K.", "pk"), (":", "")],
)
def test_alias_key(token: str, expected: str) -> None:
    assert alias_key(token) == expected


@given(st.text())
def test_lookup_never_raises(token: str) -> None:
    lookup(token)
