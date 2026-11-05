"""End-to-end tests for tradres.parse."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

import tradres
from eval.dataset import load_cases
from tradres import Address, parse
from tradres.abbreviations import alias_key, lookup
from tradres.models import FIELDS
from tradres.tokenizer import tokenize


def _found(address: Address) -> dict[str, str]:
    data = address.to_dict()
    return {key: str(data[key]) for key in [*FIELDS, "kalan"] if data[key] is not None}


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
                "sokak": "Gül",  # street spelling is a Faz 5 job
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


def test_direction_goes_to_tarif() -> None:
    address = parse("Tabaklar Mah. eski okul karşısı Merkez/Bolu")
    assert address.mahalle == "Tabaklar"
    assert address.tarif == "eski okul karşısı"


def test_road_name_is_not_a_flat() -> None:
    address = parse("Tabaklar Mah. D 100 yanı Merkez/Bolu")
    assert address.daire is None
    assert address.tarif == "D 100 yanı"


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
    assert list(Address().to_dict()) == [*FIELDS, "kalan", "confidence", "field_confidence"]


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
    output = alias_key(" ".join(_found(parse(text)).values()))
    for token in tokenize(text):
        if not token.is_separator and lookup(token.text) is None:
            for piece in token.text.split("/"):  # 12/3 is split into building and flat
                assert alias_key(piece) in output, token


@pytest.mark.parametrize(
    ("text", "mahalle", "kalan"),
    [
        ("Yenimahalle Ankara, Batıkent, 1923. Cadde", "Batıkent", None),
        ("Kuyuköy Merzifon Amasya", "Kuyuköy", None),
        ("Merzifon Amasya okul yanı", None, None),
        ("Merzifon Amasya bir iki üç", None, "bir iki üç"),
    ],
)
def test_loose_words_as_mahalle(text: str, mahalle: str | None, kalan: str | None) -> None:
    address = parse(text)
    assert (address.mahalle, address.kalan) == (mahalle, kalan)


@pytest.mark.parametrize(
    ("text", "tarif", "kalan"),
    [
        ("Yeni Mah. D 100 karayolu üzeri Güneş Apt. Kadıköy", "D 100 karayolu üzeri", None),
        ("Yeni Mah. eski belediye karşısı Kadıköy", "eski belediye karşısı", None),
        ("Yeni Mah. okul yanında No:4 Kadıköy", "okul yanında", None),
        ("Yeni Mah. Sanayi Sitesi yanı Kadıköy", "Sanayi Sitesi yanı", None),
        ("Yeni Mah. okul yanı, cami karşısı Kadıköy", "okul yanı", "cami karşısı"),
        ("Yeni Mah. okul yanı bir de bahçe Kadıköy", "okul yanı", "bir de bahçe"),
        ("Yeni Mah. köprüden geçince sağda sonra Kadıköy", None, "köprüden geçince sağda sonra"),
    ],
)
def test_directions(text: str, tarif: str | None, kalan: str | None) -> None:
    address = parse(text)
    assert (address.tarif, address.kalan) == (tarif, kalan)


def test_street_named_after_a_direction_is_not_a_direction() -> None:
    address = parse("Cami Yanı Sokak No:5 Kadıköy")
    assert (address.sokak, address.tarif) == ("Cami Yanı", None)


@pytest.mark.parametrize(
    ("text", "daire", "blok"),
    [
        ("Gül Sk. D:6/B Kadıköy", "6/B", None),
        ("Gül Sk. Daire:6/b Kadıköy", "6/B", None),
        ("Gül Sk. D:6/A Blok Kadıköy", "6", "A"),
        ("Gül Sk. D:6 / Kadıköy", "6", None),
    ],
)
def test_flat_with_a_letter(text: str, daire: str, blok: str | None) -> None:
    address = parse(text)
    assert (address.daire, address.blok) == (daire, blok)


@pytest.mark.parametrize(
    "text",
    [
        "Yeni Mah. Sinop Gerze/Sinop",
        "Yeni Mah. Gerze Gerze Sinop",
        "Sinop, Yeni Mah. Gerze/Sinop",
    ],
)
def test_repeated_place_is_not_left_over(text: str) -> None:
    address = parse(text)
    assert (address.il, address.ilce, address.kalan) == ("Sinop", "Gerze", None)


@pytest.mark.parametrize(
    ("text", "site", "kalan"),
    [
        ("Mavi Rezidans, Çarşı Mah., Lale Sk. No:3 Gerze/Sinop", "Mavi Rezidans", None),
        ("Çarşı Mah., Yeşil Vadi Evleri, No:3 Gerze/Sinop", "Yeşil Vadi Evleri", None),
        ("Çarşı Mah. Mavi Rezidans No:3 Gerze/Sinop", None, "Mavi Rezidans"),
        ("Mavi Rezidans, Lale Sk. No:3", None, "Mavi Rezidans"),
    ],
)
def test_piece_between_commas_is_a_site(text: str, site: str | None, kalan: str | None) -> None:
    address = parse(text)
    assert (address.site, address.kalan) == (site, kalan)


def test_words_before_a_building_number_are_not_a_mahalle() -> None:
    address = parse("Kordon Boyu No:6 Karşıyaka/İzmir")
    assert (address.mahalle, address.bina_no) == (None, "6")
    assert address.kalan == "Kordon Boyu"


def fields_of(address: Address) -> dict[str, str | None]:
    return {name: getattr(address, name) for name in FIELDS}


def test_format_order_and_labels() -> None:
    address = Address(
        il="Ankara",
        ilce="Çankaya",
        mahalle="Kızılay",
        bulvar="Atatürk",
        cadde="Gazi",
        sokak="Gül",
        site="Çamlık",
        bina_adi="Yıldız",
        blok="B",
        bina_no="5",
        kat="2",
        daire="3",
        posta_kodu="06420",
        tarif="okul yanı",
    )
    assert address.format() == (
        "Kızılay Mah. Atatürk Blv. Gazi Cad. Gül Sk. Çamlık Sit. Yıldız Apt. B Blok "
        "No:5 K:2 D:3 okul yanı 06420 Çankaya/Ankara"
    )


def test_format_of_an_empty_address() -> None:
    assert Address().format() == ""


def test_format_with_only_one_place() -> None:
    assert Address(il="Bolu").format() == "Bolu"
    assert Address(ilce="Merkez").format() == "Merkez"


def test_format_leaves_out_kalan() -> None:
    assert Address(il="Bolu", kalan="xqzv").format() == "Bolu"


def test_format_round_trips_on_the_development_set() -> None:
    for case in load_cases():
        first = parse(case.girdi)
        again = parse(first.format())
        assert fields_of(again) == fields_of(first), case.id


_NAMES = st.sampled_from(["Gül", "Atatürk", "23 Nisan", "Cumhuriyet", "Şehit Ali", "1923", "Barış"])
_NUMBERS = st.from_regex(r"[1-9][0-9]{0,2}[A-C]?", fullmatch=True)


@given(
    place=st.sampled_from(
        [("Bolu", "Merkez"), ("Ankara", "Çankaya"), ("İstanbul", "Şişli"), ("Muğla", "Bodrum")]
    ),
    mahalle=st.none() | st.sampled_from(["Atatürk", "Cumhuriyet", "Yeni"]),
    cadde=st.none() | _NAMES,
    sokak=st.none() | _NAMES,
    site=st.none() | st.sampled_from(["Çamlık", "Güneş Evleri"]),
    bina_adi=st.none() | st.sampled_from(["Yıldız", "Deniz"]),
    blok=st.none() | st.sampled_from(["A", "B", "C2"]),
    bina_no=st.none() | _NUMBERS,
    kat=st.none() | st.integers(1, 30).map(str),
    daire=st.none() | st.integers(1, 200).map(str),
    posta_kodu=st.none() | st.sampled_from(["06420", "14100"]),
)
def test_format_round_trips_on_any_mix_of_parts(
    place: tuple[str, str],
    mahalle: str | None,
    cadde: str | None,
    sokak: str | None,
    site: str | None,
    bina_adi: str | None,
    blok: str | None,
    bina_no: str | None,
    kat: str | None,
    daire: str | None,
    posta_kodu: str | None,
) -> None:
    address = Address(
        il=place[0],
        ilce=place[1],
        mahalle=mahalle,
        cadde=cadde,
        sokak=sokak,
        site=site,
        bina_adi=bina_adi,
        blok=blok,
        bina_no=bina_no,
        kat=kat,
        daire=daire,
        posta_kodu=posta_kodu,
    )
    assert fields_of(parse(address.format())) == fields_of(address)
