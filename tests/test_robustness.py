"""Tests for the damage functions of the robustness report."""

from __future__ import annotations

import pytest

from eval.dataset import Case
from eval.robustness import (
    NOISES,
    all_caps,
    all_lower,
    everything_at_once,
    extra_spaces,
    format_failures,
    format_table,
    main,
    no_punctuation,
    no_spaces_after_punctuation,
    no_turkish_letters,
    place_first,
    score_noise,
    typo_in_place,
)


def case(text: str, **labels: str) -> Case:
    return Case(id="x1", girdi=text, beklenen=labels, etiketler=frozenset())


def test_no_turkish_letters() -> None:
    assert no_turkish_letters(case("Şişli Çağ Ğ İ ı")) == "Sisli Cag G I i"


def test_case_noises_use_turkish_rules() -> None:
    assert all_caps(case("kızılay i")) == "KIZILAY İ"
    assert all_lower(case("KIZILAY İ")) == "kızılay i"


def test_no_punctuation() -> None:
    assert no_punctuation(case("Gül Sk. No:5, Bolu")) == "Gül Sk No 5 Bolu"


def test_no_spaces_after_punctuation() -> None:
    assert no_spaces_after_punctuation(case("Gül Sk. No: 5, Bolu")) == "Gül Sk.No:5,Bolu"


def test_extra_spaces() -> None:
    assert extra_spaces(case("a b")) == "a   b"


def test_typo_changes_a_place_name_and_is_repeatable() -> None:
    address = case("Kızılay Mah. Çankaya/Ankara", mahalle="Kızılay", ilce="Çankaya", il="Ankara")
    damaged = typo_in_place(address)
    assert damaged != address.girdi
    assert damaged == typo_in_place(address)


def test_typo_needs_a_long_place_name() -> None:
    address = case("Gül Sk. Van", il="Van")
    assert typo_in_place(address) == address.girdi


def test_place_first_with_commas() -> None:
    assert place_first(case("Gül Sk. 5, Merkez/Bolu")) == "Merkez/Bolu, Gül Sk. 5"


def test_place_first_without_commas() -> None:
    assert place_first(case("Gül Sk. 5 Merkez/Bolu")) == "Merkez/Bolu Gül Sk. 5"
    assert place_first(case("Gül Sk. 5")) == "Gül Sk. 5"


def test_everything_at_once() -> None:
    assert everything_at_once(case("Şişli Mah. No:5")) == "sisli mah no 5"


def test_score_and_table() -> None:
    cases = [case("Kızılay Mah. Çankaya/Ankara", mahalle="Kızılay", ilce="Çankaya", il="Ankara")]
    clean = score_noise(cases, lambda item: item.girdi)
    damaged = score_noise(cases, NOISES["no_turkish_letters"])
    assert clean.exact == 1
    assert "no_turkish_letters" in format_table(clean, {"no_turkish_letters": damaged})


def test_failures_are_listed() -> None:
    report = score_noise([case("Bolu", il="Ankara")], lambda item: item.girdi)
    assert "expected 'Ankara', got 'Bolu'" in format_failures(report, 5)


def test_holdout_shows_totals_only() -> None:
    assert main(["--holdout", "1", "--failures", "all_caps"]) == 2


def test_report_runs(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--failures", "all_caps", "--limit", "1"]) == 0
    assert "everything_at_once" in capsys.readouterr().out
