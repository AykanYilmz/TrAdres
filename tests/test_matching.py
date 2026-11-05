"""Tests for fuzzy matching: the helper, the gazetteer lookups and the parser."""

from __future__ import annotations

import pytest

from tradres import MatchConfig, parse
from tradres.gazetteer import load_gazetteer
from tradres.matching import DEFAULT_CONFIG, closest
from tradres.tokenizer import street_keyword, tokenize


def test_a_swap_is_one_edit() -> None:
    assert closest("malatay", ["malatya"]) == "malatya"


def test_nothing_close_enough() -> None:
    assert closest("trabzon", ["ankara", "izmir"]) is None


def test_a_tie_is_not_a_guess() -> None:
    assert closest("kalo", ["kale", "kala"]) is None


def test_allowed_edits_grow_with_length() -> None:
    assert DEFAULT_CONFIG.allowed_edits("bolu") == 1
    assert DEFAULT_CONFIG.allowed_edits("kirikkale") == 2


def test_config_can_turn_fuzzy_matching_off() -> None:
    off = MatchConfig(short_edits=0, long_edits=0)
    assert parse("Gül Sk. No:5 Malatay", config=off).il is None
    assert parse("Gül Sk. No:5 Malatay").il == "Malatya"


@pytest.mark.parametrize(
    ("typo", "official"),
    [
        ("Ankra", "Ankara"),
        ("Erzincann", "Erzincan"),
        ("Malatay", "Malatya"),
        ("adıyman", "Adıyaman"),
    ],
)
def test_fuzzy_il(typo: str, official: str) -> None:
    found = load_gazetteer().fuzzy_il(typo)
    assert found is not None
    assert found.ad == official


def test_short_words_are_not_corrected() -> None:
    assert load_gazetteer().fuzzy_il("Vaan") is not None
    assert load_gazetteer().fuzzy_il("Yan") is None
    assert load_gazetteer().fuzzy_ilce("Kaş") is None


def test_fuzzy_ilce_stays_inside_the_province() -> None:
    gazetteer = load_gazetteer()
    found = gazetteer.fuzzy_ilce("Çankya", il="Ankara")
    assert found is not None
    assert found.ad == "Çankaya"
    assert gazetteer.fuzzy_ilce("Çankya", il="Bolu") is None


def test_fuzzy_ilce_without_a_province_needs_a_one_province_name() -> None:
    found = load_gazetteer().fuzzy_ilce("Kadıköyy")
    assert found is not None
    assert found.il == "İstanbul"


def test_fuzzy_mahalle_stays_inside_the_district() -> None:
    gazetteer = load_gazetteer()
    found = gazetteer.fuzzy_mahalle("Kzılay", il="Ankara", ilce="Çankaya")
    assert found is not None
    assert found.ad == "Kızılay"
    assert gazetteer.fuzzy_mahalle("Yeni", il="Ankara", ilce="Çankaya") is None


@pytest.mark.parametrize(
    ("word", "kind"),
    [("Mahalesi", "mahalle"), ("Cadesi", "cadde"), ("Apartmaı", "apartman")],
)
def test_misspelled_keywords(word: str, kind: str) -> None:
    found = street_keyword(tokenize(word)[0])
    assert found is not None
    assert found.kind == kind


@pytest.mark.parametrize("word", ["Bulgar", "Kale", "Madde"])
def test_other_words_are_not_keywords(word: str) -> None:
    assert street_keyword(tokenize(word)[0]) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Kizilay mahalesi Çankya Ankra", ("Ankara", "Çankaya", "Kızılay")),
        ("Sarıharman Köyü Adıyman Merkez", ("Adıyaman", "Merkez", "Sarıharman")),
        ("sarıot mah kale malatay", ("Malatya", "Kale", "Sarıot")),
    ],
)
def test_typos_end_to_end(text: str, expected: tuple[str, str, str]) -> None:
    address = parse(text)
    assert (address.il, address.ilce, address.mahalle) == expected


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("Ataturk", "Atatürk"),
        ("19 Mayis", "19 Mayıs"),
        ("Sehit Kurtulus", "Şehit Kurtuluş"),
        ("Xqzw", "Xqzw"),  # unknown words stay
        ("Çinar", "Çinar"),  # words with Turkish letters stay
    ],
)
def test_respell(written: str, expected: str) -> None:
    assert load_gazetteer().respell(written) == expected


def test_ascii_street_names_get_their_letters_back() -> None:
    address = parse("yeni mah ataturk cad kurtulus sk no 5 bolu merkez")
    assert (address.cadde, address.sokak) == ("Atatürk", "Kurtuluş")


def test_name_word_is_expanded() -> None:
    assert parse("Kızılay Mah. gmk bulvarı No:12 Çankaya").bulvar == "Gazi Mustafa Kemal"


@pytest.mark.parametrize(
    ("written", "il"),
    [("İst.", "İstanbul"), ("Ist", "İstanbul"), ("Ş.Urfa", "Şanlıurfa"), ("G.Antep", "Gaziantep")],
)
def test_short_province_names(written: str, il: str) -> None:
    assert parse(f"Yeni Mah. {written}").il == il
