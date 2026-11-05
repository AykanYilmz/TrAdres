"""End-to-end tests for tradres.parse."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

import tradres
from tradres import Address, parse
from tradres.abbreviations import alias_key, lookup
from tradres.models import FIELDS
from tradres.tokenizer import tokenize


def _found(address: Address) -> dict[str, str]:
    return {key: value for key, value in address.to_dict().items() if value is not None}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Atatürk Mah. 23 Nisan Cad. No:5/3 Merkez/Bolu",
            {
                "il": "Bolu",
                "ilce": "Merkez",
                "mahalle": "Atatürk",
                "cadde": "23 Nisan",
                "bina_no": "5",
                "daire": "3",
            },
        ),
        (
            "Çankaya Ankara Kızılay Mahallesi Gazi Mustafa Kemal Blv. No: 12 Kat: 4 Daire: 8",
            {
                "il": "Ankara",
                "ilce": "Çankaya",
                "mahalle": "Kızılay",
                "bulvar": "Gazi Mustafa Kemal",
                "bina_no": "12",
                "kat": "4",
                "daire": "8",
            },
        ),
        (
            "kizilay mah. gul sk. no:5 cankaya ankara",
            {
                "il": "Ankara",
                "ilce": "Çankaya",
                "mahalle": "Kızılay",  # spelling comes from the gazetteer
                "sokak": "Gul",  # street spelling is a Faz 5 job
                "bina_no": "5",
            },
        ),
        (
            "Hassa Yukarıkarafakılı",  # a mahalle with no keyword
            {"il": "Hatay", "ilce": "Hassa", "mahalle": "Yukarıkarafakılı"},
        ),
        ("Gazi Cad. 15 Ankara", {"il": "Ankara", "cadde": "Gazi", "bina_no": "15"}),
    ],
)
def test_parse(text: str, expected: dict[str, str]) -> None:
    assert _found(parse(text)) == expected


def test_unknown_text_goes_to_kalan() -> None:
    address = parse("Tabaklar Mah. eski okul karşısı Merkez/Bolu")
    assert address.mahalle == "Tabaklar"
    assert address.kalan == "eski okul karşısı"


def test_road_name_is_not_a_flat() -> None:
    address = parse("Tabaklar Mah. D 100 yanı Merkez/Bolu")
    assert address.daire is None
    assert address.kalan == "D 100 yanı"


def test_mahalle_unknown_to_the_gazetteer_stays_as_written() -> None:
    assert parse("Atlantis Mah. Kadıköy").mahalle == "Atlantis"


def test_second_value_of_a_field_goes_to_kalan() -> None:
    address = parse("D: 34000 12/3")  # found by hypothesis: 34000 was overwritten
    assert address.daire == "34000"
    assert address.kalan == "12/3"


def test_empty_input() -> None:
    assert parse("") == Address()
    assert parse("   , / ") == Address()


def test_to_dict_has_every_field() -> None:
    assert list(Address().to_dict()) == [*FIELDS, "kalan"]


def test_address_is_immutable() -> None:
    with pytest.raises(AttributeError):
        Address().il = "Bolu"  # type: ignore[misc]


def test_public_api() -> None:
    assert tradres.parse is parse
    assert tradres.Address is Address


@given(st.text())
def test_parse_never_raises(text: str) -> None:
    assert isinstance(parse(text), Address)


address_words = st.lists(
    st.sampled_from(
        [
            "Gül",
            "Kale",
            "Ova",
            "Çınar",
            "Yıldız",
            "Bolu",
            "Ankara",
            "Merkez",
            "Kadıköy",
            "5",
            "12",
            "12/3",
            "34000",
            "Mah.",
            "Cad.",
            "Sk.",
            "Blv.",
            "Apt.",
            "Sit.",
            "Blok",
            "No:",
            "D:",
            "K:",
            ",",
            "/",
            "-",
        ]
    ),
    max_size=14,
).map(" ".join)


@given(address_words)
def test_no_word_is_lost(text: str) -> None:
    """Every word of the input is in some field or in kalan."""
    output = alias_key(" ".join(value or "" for value in parse(text).to_dict().values()))
    for token in tokenize(text):
        if not token.is_separator and lookup(token.text) is None:
            for piece in token.text.split("/"):  # 12/3 is split into building and flat
                assert alias_key(piece) in output, token
