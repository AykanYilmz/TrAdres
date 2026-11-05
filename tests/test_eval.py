"""Tests for the evaluation package and the labelled data."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from eval.__main__ import (
    as_fields,
    format_failures,
    format_markdown,
    format_text,
    load_parser,
    main,
)
from eval.baseline import parse as baseline_parse
from eval.dataset import (
    HOLDOUT_DIR,
    MISSING_TAG,
    SPELLING_TAG,
    Case,
    DatasetError,
    load_cases,
    parse_entry,
    tag_counts,
)
from eval.metrics import FieldScore, Predict, canonical, evaluate, score_field
from tradres.gazetteer import load_gazetteer

GOOD: dict[str, Any] = {
    "id": "t1",
    "girdi": "Kızılay Mah. Çankaya Ankara",
    "beklenen": {"il": "Ankara", "ilce": "Çankaya", "mahalle": "Kızılay"},
    "etiketler": ["temiz"],
}


def _entry(**changes: Any) -> dict[str, Any]:
    return {**GOOD, **changes}


def _labels(**changes: str) -> dict[str, str]:
    return {**GOOD["beklenen"], **changes}


# --------------------------------------------------------------------------- #
# The bundled data
# --------------------------------------------------------------------------- #


def test_bundled_cases_are_valid_and_enough() -> None:
    cases = load_cases()
    assert len(cases) >= 300
    assert len({case.id for case in cases}) == len(cases)


def test_bundled_cases_cover_the_styles_we_care_about() -> None:
    counts = tag_counts(load_cases())
    for tag in ("ascii", "kisaltma", "yazim_hatasi", "sira", "il_eksik", "tuzak", "koy"):
        assert counts.get(tag, 0) >= 10, tag


def test_bundled_cases_measure_the_gazetteer_gap() -> None:
    assert tag_counts(load_cases()).get(MISSING_TAG, 0) >= 20


def test_many_provinces_are_covered() -> None:
    provinces = {case.beklenen.get("il") for case in load_cases()}
    assert len(provinces) >= 60


# --------------------------------------------------------------------------- #
# parse_entry
# --------------------------------------------------------------------------- #


def test_valid_entry() -> None:
    case = parse_entry(_entry(), load_gazetteer())
    assert case.id == "t1"
    assert case.etiketler == {"temiz"}


def test_missing_mahalle_gets_the_automatic_tag() -> None:
    entry = _entry(beklenen=_labels(mahalle="Atlantis"))
    assert MISSING_TAG in parse_entry(entry, load_gazetteer()).etiketler


def test_differently_spelled_mahalle_gets_the_automatic_tag() -> None:
    entry = _entry(beklenen=_labels(mahalle="Kizilay"))
    assert SPELLING_TAG in parse_entry(entry, load_gazetteer()).etiketler


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        ("text", "must be a mapping"),
        (_entry(id=5), "'id'"),
        (_entry(girdi=" "), "'girdi'"),
        (_entry(extra="x"), "unknown keys"),
        (_entry(beklenen={}), "'beklenen'"),
        (_entry(beklenen={"mahala": "X"}), "unknown fields"),
        (_entry(beklenen=_labels(bina_no=5)), "quoted string"),  # type: ignore[arg-type]
        (_entry(etiketler="temiz"), "'etiketler'"),
        (_entry(etiketler=["temizz"]), "unknown tags"),
        (_entry(etiketler=[MISSING_TAG]), "automatically"),
        (_entry(beklenen=_labels(il="Ankra")), "il 'Ankra'"),
        (_entry(beklenen=_labels(il="ANKARA")), "il 'ANKARA'"),
        (_entry(beklenen=_labels(ilce="Kadıköy")), "ilce 'Kadıköy'"),
    ],
)
def test_bad_entries_are_rejected(entry: object, message: str) -> None:
    with pytest.raises(DatasetError, match=message):
        parse_entry(entry, load_gazetteer())


def _write(directory: Path, name: str, text: str) -> None:
    (directory / name).write_text(text, encoding="utf-8")


def test_load_cases_rejects_duplicate_ids(tmp_path: Path) -> None:
    entry = '- {id: "x", girdi: "Ankara", beklenen: {il: Ankara}}\n'
    _write(tmp_path, "a.yaml", entry)
    _write(tmp_path, "b.yaml", entry)
    with pytest.raises(DatasetError, match="duplicate id"):
        load_cases(tmp_path)


def test_load_cases_rejects_a_non_list_file(tmp_path: Path) -> None:
    _write(tmp_path, "a.yaml", "id: x\n")
    with pytest.raises(DatasetError, match="must be a YAML list"):
        load_cases(tmp_path)


def test_load_cases_sorts_by_id(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "a.yaml",
        '- {id: "b", girdi: "Ankara", beklenen: {il: Ankara}}\n'
        '- {id: "a", girdi: "Bolu", beklenen: {il: Bolu}}\n',
    )
    assert [case.id for case in load_cases(tmp_path)] == ["a", "b"]


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("left", "right", "same"),
    [
        ("Kızılay", "KIZILAY", True),
        ("İstanbul", "istanbul", True),
        (" 23  Nisan ", "23 nisan", True),
        ("Cankaya", "Çankaya", False),
        (None, "", True),
        (5, "5", True),
    ],
)
def test_canonical(left: object, right: object, same: bool) -> None:
    assert (canonical(left) == canonical(right)) is same


@pytest.mark.parametrize(
    ("expected", "predicted", "counts"),
    [
        ("Bolu", "BOLU", (1, 0, 0)),  # correct
        ("Bolu", "Düzce", (0, 1, 1)),  # wrong value counts twice
        ("Bolu", None, (0, 0, 1)),  # missed
        (None, "Bolu", (0, 1, 0)),  # invented
        (None, "", (0, 0, 0)),  # nothing to find
    ],
)
def test_score_field(expected: object, predicted: object, counts: tuple[int, int, int]) -> None:
    score = score_field(expected, predicted)
    assert (score.tp, score.fp, score.fn) == counts


def test_field_score_formulas() -> None:
    score = FieldScore(tp=8, fp=2, fn=8)
    assert score.precision == pytest.approx(0.8)
    assert score.recall == pytest.approx(0.5)
    assert score.f1 == pytest.approx(2 * 0.8 * 0.5 / 1.3)
    assert score.support == 16


def test_field_score_with_nothing_to_count() -> None:
    assert (FieldScore().precision, FieldScore().recall, FieldScore().f1) == (0.0, 0.0, 0.0)


def _case(case_id: str, tags: frozenset[str] = frozenset(), **labels: str) -> Case:
    return Case(id=case_id, girdi=case_id, beklenen=labels, etiketler=tags)


def test_evaluate_counts_exact_addresses_and_groups() -> None:
    cases = [
        _case("ok", frozenset({"ascii"}), il="Bolu"),
        _case("bad", frozenset({"ascii"}), il="Bolu", daire="3"),
    ]
    report = evaluate(cases, lambda text: {"il": "Bolu"})
    assert (report.exact, report.total, report.exact_rate) == (1, 2, 0.5)
    assert report.fields["il"].tp == 2
    assert report.fields["daire"].fn == 1
    assert report.groups["ascii"].rate == 0.5
    assert report.failures[0].wrong == {"daire": ("3", "")}


def test_extra_prediction_breaks_an_exact_match() -> None:
    report = evaluate([_case("x", il="Bolu")], lambda text: {"il": "Bolu", "kat": "2"})
    assert report.exact == 0
    assert report.fields["kat"].fp == 1


def test_kalan_is_not_scored() -> None:
    report = evaluate([_case("x", il="Bolu", kalan="yan")], lambda text: {"il": "Bolu"})
    assert report.exact == 1


def test_crash_counts_as_empty_result() -> None:
    def explode(text: str) -> Mapping[str, object]:
        raise RuntimeError(text)

    report = evaluate([_case("x", il="Bolu")], explode)
    assert report.crashes == 1
    assert report.fields["il"].fn == 1


def test_empty_report() -> None:
    report = evaluate([], lambda text: {})
    assert report.exact_rate == 0.0
    assert report.overall.f1 == 0.0


# --------------------------------------------------------------------------- #
# Baseline
# --------------------------------------------------------------------------- #


def test_baseline_finds_simple_fields() -> None:
    result = baseline_parse("Tabaklar Mah. Gül Sk. No:5 K:2 D:3 Merkez/Bolu 14100")
    assert result["il"] == "Bolu"
    assert result["mahalle"] == "Tabaklar"
    assert result["sokak"] == "Gül"
    assert (result["bina_no"], result["kat"], result["daire"]) == ("5", "2", "3")
    assert result["posta_kodu"] == "14100"


def test_baseline_infers_province_from_district() -> None:
    assert baseline_parse("Kadıköy")["il"] == "İstanbul"


def test_baseline_never_crashes_on_the_set() -> None:
    assert evaluate(load_cases(), baseline_parse).crashes == 0


# --------------------------------------------------------------------------- #
# Command line
# --------------------------------------------------------------------------- #


def _perfect(text: str) -> Predict:
    labels = {case.girdi: case.beklenen for case in load_cases()}
    return lambda girdi: labels[girdi]


def test_as_fields_accepts_mappings_and_objects() -> None:
    class Result:
        il = "Bolu"

    assert as_fields({"il": "Bolu"}) == {"il": "Bolu"}
    assert as_fields(Result())["il"] == "Bolu"
    assert as_fields(Result())["kat"] is None


def test_load_parser() -> None:
    predict = load_parser("eval.baseline:parse")
    assert predict("Bolu")["il"] == "Bolu"


def test_main_check(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--check"]) == 0
    assert "addresses are valid" in capsys.readouterr().out


def test_main_scores_a_parser(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--min-f1", "0.99", "--min-exact", "0.99"], loader=_perfect) == 0
    assert "exact addresses" in capsys.readouterr().out


def test_main_fails_below_threshold(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--parser", "eval.baseline:parse", "--min-f1", "0.99"])
    assert code == 1
    assert "below threshold" in capsys.readouterr().err


def test_main_reports_a_missing_parser(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--parser", "tradres:no_such_function"]) == 2
    assert "eval.baseline:parse" in capsys.readouterr().err


def test_main_tag_filter_markdown_and_failures(capsys: pytest.CaptureFixture[str]) -> None:
    args = ["--parser", "eval.baseline:parse", "--tag", "ascii", "--markdown", "--failures", "1"]
    assert main(args) == 0
    output = capsys.readouterr().out
    assert "| Field |" in output
    assert "expected" in output


def test_report_formats_show_crashes() -> None:
    def explode(text: str) -> Mapping[str, object]:
        raise RuntimeError(text)

    report = evaluate([_case("x", frozenset({"ascii"}), il="Bolu")], explode)
    assert "CRASHES: 1" in format_text(report)
    assert "**All fields**" in format_markdown(report)
    assert "expected 'Bolu'" in format_failures(report, 5)


def test_holdout_set_is_valid_and_separate() -> None:
    holdout = load_cases(HOLDOUT_DIR)
    assert len(holdout) == 100
    assert not {case.girdi for case in holdout} & {case.girdi for case in load_cases()}


@pytest.mark.parametrize("extra", [["--failures", "1"], ["--tag", "ascii"]])
def test_holdout_refuses_to_show_details(extra: list[str]) -> None:
    assert main(["--holdout", *extra]) == 2


def test_holdout_prints_totals(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--holdout", "--parser", "eval.baseline:parse"]) == 0
    out = capsys.readouterr().out
    assert "locked test set: 100" in out
    assert "tag " not in out
