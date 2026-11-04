"""Tests for tradres.gazetteer, against the bundled data."""

from __future__ import annotations

import re

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tradres.gazetteer import Gazetteer, GazetteerDataError, Il, load_gazetteer


@pytest.fixture(scope="module")
def gaz() -> Gazetteer:
    return load_gazetteer()


# --------------------------------------------------------------------------- #
# Shape of the bundled data
# --------------------------------------------------------------------------- #


def test_official_counts(gaz: Gazetteer) -> None:
    assert len(gaz.iller) == 81
    assert sum(len(gaz.ilceleri(il.ad)) for il in gaz.iller) == 973


def test_merkez_districts_only_in_non_metropolitan_provinces(gaz: Gazetteer) -> None:
    merkez = gaz.find_ilce("Merkez")
    assert len(merkez) == 51  # 81 provinces - 30 metropolitan
    assert "İstanbul" not in {i.il for i in merkez}


def test_neighbourhood_count_is_plausible(gaz: Gazetteer) -> None:
    # Official total is ~50,400 mahalle + köy; Wikidata covers most of them.
    total = sum(len(gaz.mahalleleri(i.il, i.ad)) for il in gaz.iller for i in gaz.ilceleri(il.ad))
    assert 40_000 < total < 55_000


def test_every_province_has_districts_and_a_plate_code(gaz: Gazetteer) -> None:
    for il in gaz.iller:
        assert gaz.ilceleri(il.ad), il
        assert re.fullmatch(r"\d{2}", il.plaka), il


def test_names_are_clean(gaz: Gazetteer) -> None:
    leftovers = re.compile(r"[(),]|\b(ilçesi|İlçesi|Mahallesi|Köyü|district)\b")
    for il in gaz.iller:
        for ilce in gaz.ilceleri(il.ad):
            assert not leftovers.search(ilce.ad), ilce
            for mahalle in gaz.mahalleleri(il.ad, ilce.ad):
                assert mahalle.ad.strip() == mahalle.ad != "", mahalle
                assert not leftovers.search(mahalle.ad), mahalle


@pytest.mark.parametrize(
    ("il", "count"), [("Ankara", 25), ("İstanbul", 39), ("İzmir", 30), ("Bolu", 9)]
)
def test_district_count_per_province(gaz: Gazetteer, il: str, count: int) -> None:
    assert len(gaz.ilceleri(il)) == count


# --------------------------------------------------------------------------- #
# find_il
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Ankara", "Ankara"),
        ("ANKARA", "Ankara"),
        ("istanbul", "İstanbul"),
        ("İSTANBUL", "İstanbul"),
        ("sanliurfa", "Şanlıurfa"),
        ("Hakkâri", "Hakkari"),
        ("Urfa", "Şanlıurfa"),
        ("Afyon", "Afyonkarahisar"),
        ("Maraş", "Kahramanmaraş"),
        ("içel", "Mersin"),
        ("Antep", "Gaziantep"),
    ],
)
def test_find_il(gaz: Gazetteer, name: str, expected: str) -> None:
    found = gaz.find_il(name)
    assert found is not None
    assert found.ad == expected


@pytest.mark.parametrize("name", ["Kızılay", "Atlantis", "", "Merkez"])
def test_find_il_unknown(gaz: Gazetteer, name: str) -> None:
    assert gaz.find_il(name) is None


def test_plate_codes(gaz: Gazetteer) -> None:
    ankara = gaz.find_il("Ankara")
    assert ankara is not None
    assert ankara.plaka == "06"


# --------------------------------------------------------------------------- #
# find_ilce / provinces_of_district
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("name", "il"),
    [
        ("Çankaya", "Ankara"),
        ("cankaya", "Ankara"),
        ("ŞİŞLİ", "İstanbul"),
        ("Kadıköy", "İstanbul"),
        ("Kahramankazan", "Ankara"),
        ("Kazan", "Ankara"),  # old name
        ("Eyüp", "İstanbul"),  # old name of Eyüpsultan
        ("Karadeniz Ereğli", "Zonguldak"),  # common name
        ("19 Mayıs", "Samsun"),
        ("Ondokuzmayıs", "Samsun"),
        ("Şile", "İstanbul"),
        ("Muratpaşa", "Antalya"),
    ],
)
def test_find_ilce_unique(gaz: Gazetteer, name: str, il: str) -> None:
    found = gaz.find_ilce(name)
    assert [i.il for i in found] == [il]


def test_find_ilce_ambiguous_name(gaz: Gazetteer) -> None:
    assert {i.il for i in gaz.find_ilce("Ereğli")} == {"Konya", "Zonguldak"}


def test_find_ilce_filtered_by_province(gaz: Gazetteer) -> None:
    found = gaz.find_ilce("merkez", il="bolu")
    assert [(i.ad, i.il) for i in found] == [("Merkez", "Bolu")]
    assert gaz.find_ilce("Çankaya", il="İzmir") == []
    assert gaz.find_ilce("Çankaya", il="Atlantis") == []


def test_alias_returns_official_name(gaz: Gazetteer) -> None:
    (found,) = gaz.find_ilce("Eyüp")
    assert found.ad == "Eyüpsultan"
    assert "Eyüp" in found.diger_adlar


def test_provinces_of_district(gaz: Gazetteer) -> None:
    assert [il.ad for il in gaz.provinces_of_district("Kadıköy")] == ["İstanbul"]
    assert len(gaz.provinces_of_district("Merkez")) == 51
    assert gaz.provinces_of_district("Atlantis") == []


# --------------------------------------------------------------------------- #
# find_mahalle / mahalleleri
# --------------------------------------------------------------------------- #


def test_find_mahalle_in_district(gaz: Gazetteer) -> None:
    found = gaz.find_mahalle("kizilay", ilce="Çankaya", il="Ankara")
    assert [(m.ad, m.ilce, m.il) for m in found] == [("Kızılay", "Çankaya", "Ankara")]


def test_find_mahalle_common_name_needs_filters(gaz: Gazetteer) -> None:
    everywhere = gaz.find_mahalle("Cumhuriyet")
    in_ankara = gaz.find_mahalle("Cumhuriyet", il="Ankara")
    assert len(everywhere) > len(in_ankara) > 0
    assert all(m.il == "Ankara" for m in in_ankara)


def test_find_mahalle_unknown_filters(gaz: Gazetteer) -> None:
    assert gaz.find_mahalle("Kızılay", il="Atlantis") == []
    assert gaz.find_mahalle("Kızılay", ilce="Atlantis") == []


def test_mahalleleri(gaz: Gazetteer) -> None:
    names = {m.ad for m in gaz.mahalleleri("ankara", "cankaya")}
    assert "Kızılay" in names
    assert gaz.mahalleleri("Ankara", "Atlantis") == ()
    assert gaz.mahalleleri("Atlantis", "Merkez") == ()


def test_ilceleri_unknown_province(gaz: Gazetteer) -> None:
    assert gaz.ilceleri("Atlantis") == ()


@given(st.text())
def test_lookups_never_raise(text: str) -> None:
    gaz = load_gazetteer()
    gaz.find_il(text)
    gaz.find_ilce(text, il=text)
    gaz.find_mahalle(text, ilce=text, il=text)
    gaz.provinces_of_district(text)


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #


def test_load_is_cached() -> None:
    assert load_gazetteer() is load_gazetteer()


def test_metadata_and_repr(gaz: Gazetteer) -> None:
    assert "Wikidata" in gaz.source
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", gaz.retrieved)
    assert "81 il, 973 ilçe" in repr(gaz)


def _tiny() -> dict[str, object]:
    return {
        "format": 1,
        "source": "test",
        "retrieved": "2026-01-01",
        "iller": [
            {
                "ad": "Bolu",
                "plaka": "14",
                "ilceler": [{"ad": "Merkez", "mahalleler": ["Tabaklar", "Karamanlı"]}],
            }
        ],
    }


def test_build_from_minimal_data() -> None:
    gaz = Gazetteer(_tiny())
    assert gaz.iller == (Il(ad="Bolu", plaka="14"),)
    assert [m.ad for m in gaz.mahalleleri("Bolu", "Merkez")] == ["Tabaklar", "Karamanlı"]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"format": 2}, "unsupported gazetteer format"),
        ({"iller": "not a list"}, "malformed"),
        ({"iller": [{"ad": "Bolu"}]}, "malformed"),
        ({"iller": [{"ad": "Bolu", "plaka": "14", "ilceler": [], "diger_adlar": 5}]}, "malformed"),
    ],
)
def test_bad_data_is_rejected(change: dict[str, object], message: str) -> None:
    with pytest.raises(GazetteerDataError, match=message):
        Gazetteer({**_tiny(), **change})
