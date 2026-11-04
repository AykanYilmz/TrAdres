"""Tests for the pure transform functions in scripts/build_gazetteer.py.

The fixtures copy real Wikidata problems we found (messy labels, duplicate
items, towns between a mahalle and its district) in a few rows each.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "build_gazetteer.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_gazetteer", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_gazetteer"] = module  # dataclasses need the module registered
    spec.loader.exec_module(module)
    return module


bg = _load_script()

PROVINCES = [
    {"item": "Q1", "label": "Bolu", "plate": "14"},
    {"item": "Q2", "label": "Ankara", "plate": "06"},
    {"item": "Q3", "label": "Şanlıurfa", "plate": "63"},
]


def _build(
    districts: list[dict[str, str]],
    settlements: list[dict[str, str]] | None = None,
    corrections: object | None = None,
) -> tuple[dict[str, object], Any]:
    raw = {
        "provinces": PROVINCES,
        "districts": districts,
        "mahalleler": settlements or [],
        "koyler": [],
    }
    return bg.build(raw, corrections or bg.Corrections(), "2026-01-01")  # type: ignore[no-any-return]


def _districts(payload: dict[str, object], il: str) -> dict[str, list[str]]:
    iller = payload["iller"]
    assert isinstance(iller, list)
    (province,) = [p for p in iller if p["ad"] == il]
    return {d["ad"]: d["mahalleler"] for d in province["ilceler"]}


# --------------------------------------------------------------------------- #
# Label cleaning
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Mengen (ilçe)", "Mengen"),
        ("Mudurnu ilçesi", "Mudurnu"),
        ("Yeniçağa İlçesi", "Yeniçağa"),
        ("Edremit (Balıkesir) ilçesi", "Edremit"),
        ("Güzelyurt, Aksaray", "Güzelyurt"),
        ("Köprübaşı, Manisa (ilçe)", "Köprübaşı"),
        ("Diyadin'in ilçesi", "Diyadin"),
        ("Tillo'nun ilçesi", "Tillo"),
        ("Şirvan'ın ilçesi", "Şirvan"),
        ("Distretto di Konyaaltı", "Konyaaltı"),
        ("Polatlı District", "Polatlı"),
        ("Çankaya", "Çankaya"),
    ],
)
def test_clean_district_label(label: str, expected: str) -> None:
    assert bg.clean_district_label(label) == expected


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Yeşilköy (Kaş)", "Yeşilköy"),
        ("Kızılay Mahallesi", "Kızılay"),
        ("Alpağut Köyü", "Alpağut"),
        ("Merkez, Kaş", "Merkez"),
        ("Tabaklar", "Tabaklar"),
    ],
)
def test_clean_settlement_label(label: str, expected: str) -> None:
    assert bg.clean_settlement_label(label) == expected


# --------------------------------------------------------------------------- #
# Districts
# --------------------------------------------------------------------------- #


def test_central_district_becomes_merkez() -> None:
    payload, _ = _build([{"item": "Q10", "label": "Bolu", "parent": "Q1"}])
    assert list(_districts(payload, "Bolu")) == ["Merkez"]


def test_stale_merkez_in_metropolitan_province_is_dropped() -> None:
    payload, report = _build([{"item": "Q10", "label": "Şanlıurfa (ilçe)", "parent": "Q3"}])
    assert _districts(payload, "Şanlıurfa") == {}
    assert report.districts_stale_merkez


def test_duplicate_items_are_merged() -> None:
    payload, report = _build(
        [
            {"item": "Q10", "label": "Mengen", "parent": "Q1"},
            {"item": "Q11", "label": "Mengen (ilçe)", "parent": "Q1"},
        ]
    )
    assert list(_districts(payload, "Bolu")) == ["Mengen"]
    assert len(report.districts_merged) == 1


def test_inactive_districts_are_skipped() -> None:
    payload, _ = _build(
        [
            {"item": "Q10", "label": "Eski", "parent": "Q1", "dissolved": "2012-01-01"},
            {"item": "Q11", "label": "Bitti", "parent": "Q1", "ended": "2014-01-01"},
        ]
    )
    assert _districts(payload, "Bolu") == {}


def test_province_found_via_grandparent_or_parent_label() -> None:
    payload, _ = _build(
        [
            {"item": "Q10", "label": "Seben", "parent": "Q99", "grandparent": "Q1"},
            {"item": "Q11", "label": "Gerede", "parent": "Q98", "parentLabel": "Bolu"},
        ]
    )
    assert sorted(_districts(payload, "Bolu")) == ["Gerede", "Seben"]


def test_district_without_province_is_reported() -> None:
    payload, report = _build([{"item": "Q10", "label": "Arife İlçesi"}])
    assert _districts(payload, "Bolu") == {}
    assert report.districts_dropped_no_province == ["Q10 'Arife İlçesi'"]


def test_label_language_preference() -> None:
    rows = [
        {"item": "Q10", "parent": "Q2", "otherLabel": "Distretto di Kazan", "otherLang": "it"},
        {"item": "Q10", "parent": "Q2", "otherLabel": "Kazan", "otherLang": "mul"},
    ]
    payload, _ = _build(rows)
    assert list(_districts(payload, "Ankara")) == ["Kazan"]


# --------------------------------------------------------------------------- #
# Corrections
# --------------------------------------------------------------------------- #


def _corrections(**sections: dict[str, dict[str, object]]) -> object:
    return bg.Corrections.from_json(sections)


def test_corrections_rename_add_and_drop() -> None:
    corrections = _corrections(
        district_names={"Q10": {"name": "Kahramankazan", "aliases": ["Kazan"], "reason": "r"}},
        extra_districts={"Q11": {"il": "Ankara", "reason": "r"}},
        drop_districts={"Q12": {"reason": "r"}},
    )
    payload, _ = _build(
        [
            {"item": "Q10", "label": "Kazan (rayon)", "parent": "Q2"},
            {"item": "Q11", "label": "Pursaklar"},
            {"item": "Q12", "label": "Wikimedia yineleme sayfası", "parent": "Q2"},
        ],
        corrections=corrections,
    )
    assert sorted(_districts(payload, "Ankara")) == ["Kahramankazan", "Pursaklar"]
    iller = payload["iller"]
    assert isinstance(iller, list)
    (ankara,) = [p for p in iller if p["ad"] == "Ankara"]
    kazan = next(d for d in ankara["ilceler"] if d["ad"] == "Kahramankazan")
    assert kazan["diger_adlar"] == ["Kazan"]


def test_province_aliases() -> None:
    corrections = _corrections(province_aliases={"Q3": {"aliases": ["Urfa"], "reason": "r"}})
    payload, _ = _build([], corrections=corrections)
    iller = payload["iller"]
    assert isinstance(iller, list)
    (urfa,) = [p for p in iller if p["ad"] == "Şanlıurfa"]
    assert urfa["diger_adlar"] == ["Urfa"]


@pytest.mark.parametrize(
    "data",
    [
        {"district_names": {"Q10": {"name": "X"}}},  # no reason
        {"district_names": {"not-a-qid": {"name": "X", "reason": "r"}}},
        {"drop_districts": ["Q10"]},  # must be an object
    ],
)
def test_corrections_are_validated(data: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="corrections"):
        bg.Corrections.from_json(data)


def test_bundled_corrections_file_is_valid() -> None:
    path = SCRIPT.parent / "gazetteer_corrections.json"
    corrections = bg.Corrections.from_json(json.loads(path.read_text(encoding="utf-8")))
    assert corrections.district_names


# --------------------------------------------------------------------------- #
# Settlements
# --------------------------------------------------------------------------- #

BOLU_MERKEZ = {"item": "Q10", "label": "Bolu", "parent": "Q1"}
CANKAYA = {"item": "Q20", "label": "Çankaya (ilçe)", "parent": "Q2"}


def test_settlement_attached_to_parent_district() -> None:
    payload, _ = _build([BOLU_MERKEZ], [{"item": "Q100", "label": "Tabaklar", "parent": "Q10"}])
    assert _districts(payload, "Bolu") == {"Merkez": ["Tabaklar"]}


def test_settlement_attached_via_belde() -> None:
    payload, _ = _build(
        [BOLU_MERKEZ],
        [{"item": "Q100", "label": "Karacasu Mahallesi", "parent": "Q50", "grandparent": "Q10"}],
    )
    assert _districts(payload, "Bolu") == {"Merkez": ["Karacasu"]}


def test_settlement_attached_via_town_in_province() -> None:
    # parent is the town "Bolu" placed directly in Bolu province
    row = {"item": "Q100", "label": "Tabaklar", "parent": "Q50", "parentLabel": "Bolu"}
    payload, _ = _build([BOLU_MERKEZ], [{**row, "grandparent": "Q1"}])
    assert _districts(payload, "Bolu") == {"Merkez": ["Tabaklar"]}


def test_settlement_attached_via_unique_district_name() -> None:
    row = {"item": "Q100", "label": "Kızılay", "parent": "Q51", "parentLabel": "Çankaya"}
    payload, _ = _build([CANKAYA], [row])
    assert _districts(payload, "Ankara") == {"Çankaya": ["Kızılay"]}


def test_unresolved_and_inactive_settlements_are_counted() -> None:
    payload, report = _build(
        [BOLU_MERKEZ],
        [
            {"item": "Q100", "label": "Kayıp", "parent": "Q999"},
            {"item": "Q101", "label": "Eski", "parent": "Q10", "dissolved": "2000-01-01"},
        ],
    )
    assert _districts(payload, "Bolu") == {"Merkez": []}
    assert report.settlements_unresolved == 1
    assert report.settlements_inactive == 1


def test_village_that_became_mahalle_is_active() -> None:
    # One class statement ended (village), the other (mahalle) did not.
    rows = [
        {"item": "Q100", "label": "Tabaklar", "parent": "Q10", "ended": "2014-03-30"},
        {"item": "Q100", "label": "Tabaklar", "parent": "Q10"},
    ]
    payload, _ = _build([BOLU_MERKEZ], rows)
    assert _districts(payload, "Bolu") == {"Merkez": ["Tabaklar"]}


def test_output_is_sorted_and_versioned() -> None:
    payload, _ = _build(
        [BOLU_MERKEZ],
        [
            {"item": "Q101", "label": "Zeytin", "parent": "Q10"},
            {"item": "Q100", "label": "Çay", "parent": "Q10"},
        ],
    )
    assert payload["format"] == bg.FORMAT_VERSION
    assert _districts(payload, "Bolu") == {"Merkez": ["Çay", "Zeytin"]}
