"""Tests for each pipeline step on its own."""

from __future__ import annotations

import pytest

from tradres.extractors.numbers import extract_numbers
from tradres.extractors.places import extract_places, free_windows
from tradres.extractors.streets import extract_streets
from tradres.gazetteer import load_gazetteer
from tradres.tokenizer import tokenize

# --------------------------------------------------------------------------- #
# Numbers
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("No:5", {"bina_no": "5"}),
        ("no 5", {"bina_no": "5"}),
        ("no5", {"bina_no": "5"}),
        ("Numara 12A", {"bina_no": "12A"}),
        ("No:5/3", {"bina_no": "5", "daire": "3"}),
        ("No:7/A", {"bina_no": "7/A"}),
        ("D:3", {"daire": "3"}),
        ("d 3", {"daire": "3"}),
        ("d4", {"daire": "4"}),
        ("Daire 100", {"daire": "100"}),
        ("D:100", {"daire": "100"}),
        ("K:2", {"kat": "2"}),
        ("Kat 2", {"kat": "2"}),
        ("k2", {"kat": "2"}),
        ("Kat:Zemin", {"kat": "Zemin"}),
        ("Kat Zemin", {"kat": "Zemin"}),
        ("Kat:B1", {"kat": "B1"}),
        ("12/8", {"bina_no": "12", "daire": "8"}),
        ("34000", {"posta_kodu": "34000"}),
        ("P.K. 13200", {"posta_kodu": "13200"}),
        ("PK 13200", {"posta_kodu": "13200"}),
        ("Posta Kodu: 35790", {"posta_kodu": "35790"}),
        ("No:5 D:3 K:2", {"bina_no": "5", "daire": "3", "kat": "2"}),
    ],
)
def test_numbers(text: str, expected: dict[str, str]) -> None:
    assert extract_numbers(tokenize(text)).fields == expected


@pytest.mark.parametrize(
    "text",
    [
        "D 100 karayolu",  # a road, not flat 100
        "D Blok",  # block D, not a flat
        "K Blok",  # block K, not a floor
        "K Zemin",  # a bare K needs a number
        "1752/3 Sk.",  # a street number in İzmir
        "64023 Sokak",  # a street number, not a postal code
        "24020 Nolu Sk.",
        "99000",  # no province has plate code 99
        "No",
        "Kat",
    ],
)
def test_not_numbers(text: str) -> None:
    assert extract_numbers(tokenize(text)).fields == {}


@pytest.mark.parametrize(
    ("text", "expected", "used"),
    [
        ("No:5 No:6", {"bina_no": "5"}, {0, 1}),
        ("d4 d5", {"daire": "4"}, {0}),
        ("k2 k3", {"kat": "2"}, {0}),
        ("34000 35000", {"posta_kodu": "34000"}, {0}),
        ("PK 34000 PK 35000", {"posta_kodu": "34000"}, {0, 1}),
        ("D: 7 12/3", {"daire": "7"}, {0, 1}),  # would overwrite the flat
        ("No:5 12/3", {"bina_no": "5"}, {0, 1}),
    ],
)
def test_first_value_wins_and_the_rest_stays_free(
    text: str, expected: dict[str, str], used: set[int]
) -> None:
    result = extract_numbers(tokenize(text))
    assert result.fields == expected
    assert result.used == used


def test_slash_keeps_both_numbers_when_the_flat_is_known() -> None:
    fields = extract_numbers(tokenize("D:3 No:5/6")).fields
    assert fields == {"daire": "3", "bina_no": "5/6"}


def test_used_marks_consumed_tokens() -> None:
    assert extract_numbers(tokenize("Gül No:5")).used == {1, 2}


# --------------------------------------------------------------------------- #
# Places
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("text", "il", "ilce"),
    [
        ("Merkez/Bolu", "Bolu", "Merkez"),
        ("Bolu Merkez", "Bolu", "Merkez"),
        ("Bolu - Merkez", "Bolu", "Merkez"),
        ("CANKAYA ANKARA", "Ankara", "Çankaya"),
        ("Kadıköy", "İstanbul", "Kadıköy"),
        ("Karadeniz Ereğli Zonguldak", "Zonguldak", "Ereğli"),
        ("Urfa Eyyübiye", "Şanlıurfa", "Eyyübiye"),
    ],
)
def test_places(text: str, il: str, ilce: str) -> None:
    fields = extract_places(tokenize(text), (), load_gazetteer()).fields
    assert fields == {"il": il, "ilce": ilce}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Merkez", {}),  # 51 provinces have a Merkez
        ("Ereğli", {}),  # two provinces
        ("Tekirdağ", {"il": "Tekirdağ"}),
        ("Van Cad.", {}),  # a street name
        ("Fatih Mah.", {}),
        ("24 Ankara Nolu Sokak", {}),
        ("Atlantis", {}),
    ],
)
def test_places_special_cases(text: str, expected: dict[str, str]) -> None:
    assert extract_places(tokenize(text), (), load_gazetteer()).fields == expected


def test_places_skip_used_tokens() -> None:
    tokens = tokenize("Bolu Ankara")
    assert extract_places(tokens, {1}, load_gazetteer()).fields == {"il": "Bolu"}


def test_district_word_is_consumed() -> None:
    result = extract_places(tokenize("Pınarbaşı ilçesi Kayseri"), (), load_gazetteer())
    assert result.fields == {"il": "Kayseri", "ilce": "Pınarbaşı"}
    assert result.used == {0, 1, 2}


def test_free_windows_stop_at_separators() -> None:
    windows = [window.text for window in free_windows(tokenize("A B, C"), ())]
    assert windows == ["A", "A B", "B", "C"]


# --------------------------------------------------------------------------- #
# Streets
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Kızılay Mah.", {"mahalle": "Kızılay"}),
        ("Alpağut Köyü", {"mahalle": "Alpağut"}),
        ("23 Nisan Cad.", {"cadde": "23 Nisan"}),
        ("1923. Cadde", {"cadde": "1923"}),
        ("75. Yıl Cad.", {"cadde": "75. Yıl"}),
        ("24020 Nolu Sk.", {"sokak": "24020"}),
        ("1752/3 sk", {"sokak": "1752/3"}),
        ("GAZİ MUSTAFA KEMAL BULVARI", {"bulvar": "Gazi Mustafa Kemal"}),
        ("Güneş Sitesi C Blok", {"site": "Güneş", "blok": "C"}),
        ("Gül Apartmanı", {"bina_adi": "Gül"}),
        ("A-2 Blok", {"blok": "A-2"}),
        ("Blok a2", {"blok": "A2"}),
        ("Kardelen Sokak Mavi C Blok", {"sokak": "Kardelen", "blok": "C"}),
        ("Atatürk Mah. Gül Sk. Çınar Sk.", {"mahalle": "Atatürk", "sokak": "Gül"}),
    ],
)
def test_streets(text: str, expected: dict[str, str]) -> None:
    assert extract_streets(tokenize(text), ()).fields == expected


@pytest.mark.parametrize("text", ["Sokak", "Mah.", ", Cad.", "Blok", "Blok,"])
def test_keyword_without_a_name_stays_free(text: str) -> None:
    result = extract_streets(tokenize(text), ())
    assert result.fields == {}
    assert result.used == frozenset()


def test_used_token_breaks_a_name() -> None:
    assert extract_streets(tokenize("Gül No 5 Çınar Sk."), {1, 2}).fields == {"sokak": "Çınar"}


@pytest.mark.parametrize(
    ("text", "name"),
    [
        ("Karayolu üzeri Güneş Apt.", "Güneş"),
        ("Okul yanı Lale Apartmanı", "Lale"),
        ("Valilik lojmanları Şehit Ali Demir Apt.", "Şehit Ali Demir"),
        ("Yol üzeri Devlet lojmanları Çınar Apt.", "Çınar"),
    ],
)
def test_building_name_starts_after_a_description(text: str, name: str) -> None:
    assert extract_streets(tokenize(text), ()).fields == {"bina_adi": name}


def test_description_alone_is_not_a_building_name() -> None:
    assert extract_streets(tokenize("Okul yanı Apt."), ()).fields == {}


@pytest.mark.parametrize(
    ("text", "field", "name"),
    [("Cami Yanı Sokak", "sokak", "Cami Yanı"), ("Kale Arkası Cad.", "cadde", "Kale Arkası")],
)
def test_description_words_stay_in_street_names(text: str, field: str, name: str) -> None:
    assert extract_streets(tokenize(text), ()).fields == {field: name}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("No:5 Daire No:3", {"bina_no": "5", "daire": "3"}),
        ("No 5 Daire No 3", {"bina_no": "5", "daire": "3"}),
        ("No:5 daire no: 300", {"bina_no": "5", "daire": "300"}),
        ("Daire Numara 3", {"daire": "3"}),
        ("No:5 Kat No:2 Daire No:3", {"bina_no": "5", "kat": "2", "daire": "3"}),
        ("Bina No:5 Daire No:3", {"bina_no": "5", "daire": "3"}),
    ],
)
def test_no_word_after_a_flat_or_floor_label(text: str, expected: dict[str, str]) -> None:
    found = extract_numbers(tokenize(text))
    assert found.fields == expected
    assert len(found.used) == len(tokenize(text))


@pytest.mark.parametrize("text", ["Blok D No:5", "Blok K No:5"])
def test_bare_letter_before_no_is_not_a_label(text: str) -> None:
    assert extract_numbers(tokenize(text)).fields == {"bina_no": "5"}
