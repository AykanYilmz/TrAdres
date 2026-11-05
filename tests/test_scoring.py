"""Tests for confidence scores."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from tradres import parse
from tradres.scoring import Origin, score_address

ALL_PLACES = {"il": Origin.EXACT, "ilce": Origin.EXACT, "mahalle": Origin.EXACT}


def test_nothing_found_is_zero() -> None:
    scores = score_address({}, total_words=3, leftover_words=3)
    assert scores.overall == 0.0
    assert scores.fields == {}


def test_official_places_are_fully_trusted() -> None:
    assert score_address(ALL_PLACES, total_words=3, leftover_words=0).overall == 1.0


def test_missing_place_lowers_the_score() -> None:
    full = score_address(ALL_PLACES, total_words=3, leftover_words=0).overall
    partial = {"il": Origin.EXACT, "ilce": Origin.EXACT}
    assert score_address(partial, total_words=3, leftover_words=0).overall < full


def test_leftover_words_lower_the_score() -> None:
    clean = score_address(ALL_PLACES, total_words=4, leftover_words=0).overall
    messy = score_address(ALL_PLACES, total_words=4, leftover_words=2).overall
    assert messy == clean * 0.75


def test_zero_words_do_not_divide_by_zero() -> None:
    assert score_address(ALL_PLACES, total_words=0, leftover_words=0).overall == 1.0


@given(
    st.dictionaries(
        st.sampled_from(["il", "ilce", "mahalle", "cadde", "kat"]), st.sampled_from(Origin)
    ),
    st.integers(0, 20),
    st.integers(0, 20),
)
def test_score_stays_between_zero_and_one(
    origins: dict[str, Origin], total: int, leftover: int
) -> None:
    scores = score_address(origins, total_words=total + leftover, leftover_words=leftover)
    assert 0.0 <= scores.overall <= 1.0


def test_clean_address_scores_higher_than_a_typo() -> None:
    clean = parse("Kızılay Mah. Atatürk Blv. No:9 Çankaya/Ankara")
    typo = parse("Kızılay Mah. Atatürk Blv. No:9 Çankya/Ankara")
    assert clean.ilce == typo.ilce == "Çankaya"
    assert typo.confidence < clean.confidence
    assert clean.field_confidence["ilce"] == Origin.EXACT.value
    assert typo.field_confidence["ilce"] == Origin.FUZZY.value


def test_wrong_province_lowers_the_score() -> None:
    address = parse("Kızılay Mah. Kadıköy/Ankara")
    assert (address.il, address.ilce) == ("Ankara", "Kadıköy")
    assert address.field_confidence["ilce"] == Origin.MISMATCH.value
    assert address.confidence < parse("Kızılay Mah. Çankaya/Ankara").confidence


def test_province_from_district_is_marked() -> None:
    address = parse("Moda Cad. Kadıköy")
    assert address.il == "İstanbul"
    assert address.field_confidence["il"] == Origin.INFERRED.value


def test_mahalle_unknown_to_the_gazetteer_is_marked() -> None:
    address = parse("Mavikaraca Mah. Seferihisar/İzmir")
    assert address.mahalle == "Mavikaraca"
    assert address.field_confidence["mahalle"] == Origin.UNVERIFIED.value


def test_to_dict_is_json_ready() -> None:
    data = parse("Çankaya/Ankara").to_dict()
    assert data["confidence"] == parse("Çankaya/Ankara").confidence
    assert data["field_confidence"] == {"il": 1.0, "ilce": 1.0}


def test_loose_mahalle_is_not_trusted() -> None:
    address = parse("Yenimahalle Ankara, Batıkent, 1923. Cadde")
    assert address.field_confidence["mahalle"] == Origin.UNVERIFIED.value


def test_site_without_a_keyword_is_not_trusted() -> None:
    address = parse("Mavi Rezidans, Çarşı Mah., Gerze/Sinop")
    assert address.field_confidence["site"] == Origin.UNVERIFIED.value
