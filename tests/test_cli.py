"""Tests for the command line."""

from __future__ import annotations

import csv
import io
import json
import runpy
import sys
from pathlib import Path

import pytest

from tradres import __version__, cli, parse
from tradres.cli import (
    CliError,
    Progress,
    Summary,
    convert_csv,
    detect_dialect,
    detect_encoding,
    find_column,
    fit_row,
    main,
    progress_line,
    safe_cell,
)
from tradres.models import FIELDS


def read_rows(path: Path, delimiter: str = ",") -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file, delimiter=delimiter))


def test_parse_prints_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["parse", "ataturk mh 23nisan cd no 5 d 3 bolu merkez"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["il"] == "Bolu"
    assert data["mahalle"] == "Atatürk"
    assert data["adres"] == "Atatürk Mah. 23 Nisan Cad. No:5 D:3 Merkez/Bolu"
    assert data["field_confidence"]["il"] == 1.0


def test_parse_output_keeps_turkish_letters(capsys: pytest.CaptureFixture[str]) -> None:
    main(["parse", "Şişli/İstanbul"])
    assert '"il": "İstanbul"' in capsys.readouterr().out


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stop:
        main(["--version"])
    assert stop.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_a_command_is_required() -> None:
    with pytest.raises(SystemExit) as stop:
        main([])
    assert stop.value.code == 2


def test_python_dash_m(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["tradres", "parse", "Bolu"])
    with pytest.raises(SystemExit) as stop:
        runpy.run_module("tradres", run_name="__main__")
    assert stop.value.code == 0
    assert '"il": "Bolu"' in capsys.readouterr().out


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("adres\nŞişli\n".encode(), "utf-8"),
        (b"adres\nBolu\n", "utf-8"),
        (b"\xef\xbb\xbfadres\n", "utf-8-sig"),
        ("adres\n".encode("utf-16"), "utf-16"),
        ("adres\nŞişli\n".encode("cp1254"), "cp1254"),
    ],
)
def test_detect_encoding(tmp_path: Path, content: bytes, expected: str) -> None:
    path = tmp_path / "in.csv"
    path.write_bytes(content)
    assert detect_encoding(path) == expected


def test_detect_encoding_sees_the_end_of_a_big_file(tmp_path: Path) -> None:
    path = tmp_path / "in.csv"
    path.write_bytes(b"a" * (cli._CHUNK_SIZE + 10) + "ş".encode("cp1254"))
    assert detect_encoding(path) == "cp1254"


@pytest.mark.parametrize(
    ("line", "delimiter"),
    [("ad,adres\n", ","), ("ad;adres\n", ";"), ("ad\tadres\n", "\t"), ("ad|adres\n", "|")],
)
def test_detect_dialect(line: str, delimiter: str) -> None:
    assert detect_dialect(line, "adres") == (delimiter, ["ad", "adres"], 1)


def test_detect_dialect_handles_a_quoted_header() -> None:
    assert detect_dialect('"ad, soyad";adres\n', "adres")[0] == ";"


def test_unknown_column_lists_the_columns() -> None:
    with pytest.raises(CliError, match="columns are: ad, not"):
        detect_dialect("ad,not\n", "adres")


def test_empty_header() -> None:
    with pytest.raises(CliError, match="empty"):
        detect_dialect("", "adres")


@pytest.mark.parametrize("name", ["ADRES", " adres ", "Adres"])
def test_find_column_ignores_case_and_spaces(name: str) -> None:
    assert find_column(["id", name], "adres") == 1


def test_find_column_uses_turkish_case() -> None:
    assert find_column(["İL"], "il") == 0
    assert find_column(["IL"], "il") is None


def test_fit_row() -> None:
    assert fit_row(["a", "b"], 2, ",") == (["a", "b"], False)
    assert fit_row(["a"], 2, ",") == (["a", ""], True)
    assert fit_row(["a", "b", "c"], 2, ";") == (["a", "b;c"], True)


@pytest.mark.parametrize("value", ["=1+1", "+90", "-5", "@x"])
def test_safe_cell_blocks_formulas(value: str) -> None:
    assert safe_cell(value) == f"'{value}"


def test_safe_cell_keeps_normal_text() -> None:
    assert safe_cell("Gül Sk. 5-3") == "Gül Sk. 5-3"


def test_progress_line() -> None:
    assert progress_line(50, 100, 10, 2.0) == f"[{'#' * 12}{'-' * 12}]  50%  10 rows  5/s"


def test_progress_line_with_nothing_to_measure() -> None:
    assert "100%" in progress_line(0, 0, 0, 0.0)
    assert "100%" in progress_line(200, 100, 1, 1.0)


def test_progress_writes_to_its_stream() -> None:
    stream = io.StringIO()
    bar = Progress(10, enabled=True, stream=stream)
    bar.update(5, 1, force=True)
    bar.close(10, 2)
    assert stream.getvalue().count("\r") == 2
    assert stream.getvalue().endswith("\n")


def test_progress_does_not_redraw_too_often() -> None:
    stream = io.StringIO()
    bar = Progress(10, enabled=True, stream=stream)
    bar.update(1, 1, force=True)
    bar.update(2, 2)
    assert stream.getvalue().count("\r") == 1


def test_disabled_progress_is_silent() -> None:
    stream = io.StringIO()
    bar = Progress(10, enabled=False, stream=stream)
    bar.update(5, 1, force=True)
    bar.close(10, 2)
    assert stream.getvalue() == ""


def test_summary_text() -> None:
    assert "0 rows, 0 empty, mean confidence 0.00" in str(Summary())
    assert "warning" in str(Summary(rows=1, uneven=1))


def test_csv_keeps_columns_and_adds_results(tmp_path: Path) -> None:
    source = tmp_path / "in.csv"
    target = tmp_path / "out.csv"
    source.write_text('id,adres\n7,"Gül Sk. No:5/3, Merkez/Bolu"\n', encoding="utf-8")
    summary = convert_csv(source, target, column="adres")
    row = read_rows(target)[0]
    assert (row["id"], row["adres"]) == ("7", "Gül Sk. No:5/3, Merkez/Bolu")
    assert row["tradres_il"] == "Bolu"
    assert row["tradres_sokak"] == "Gül"
    assert row["tradres_daire"] == "3"
    assert row["tradres_adres"] == "Gül Sk. No:5 D:3 Merkez/Bolu"
    assert float(row["tradres_guven"]) > 0
    assert (summary.rows, summary.empty) == (1, 0)


def test_csv_has_a_column_for_every_field(tmp_path: Path) -> None:
    source = tmp_path / "in.csv"
    target = tmp_path / "out.csv"
    source.write_text("adres\nBolu\n", encoding="utf-8")
    convert_csv(source, target, column="adres")
    assert list(read_rows(target)[0]) == [
        "adres",
        *(f"tradres_{name}" for name in FIELDS),
        "tradres_kalan",
        "tradres_guven",
        "tradres_adres",
    ]


def test_csv_from_turkish_excel(tmp_path: Path) -> None:
    source = tmp_path / "in.csv"
    target = tmp_path / "out.csv"
    source.write_bytes("ad;Adres\nX;Şişli/İstanbul\n".encode("cp1254"))
    convert_csv(source, target, column="adres")
    row = read_rows(target, ";")[0]
    assert (row["tradres_il"], row["tradres_ilce"]) == ("İstanbul", "Şişli")


def test_csv_output_starts_with_a_bom_for_excel(tmp_path: Path) -> None:
    source = tmp_path / "in.csv"
    target = tmp_path / "out.csv"
    source.write_text("adres\nBolu\n", encoding="utf-8")
    convert_csv(source, target, column="adres")
    assert target.read_bytes().startswith(b"\xef\xbb\xbf")


def test_csv_output_encoding_and_delimiter_options(tmp_path: Path) -> None:
    source = tmp_path / "in.csv"
    target = tmp_path / "out.csv"
    source.write_bytes("adres\tnot\nŞişli/İstanbul\tx\n".encode("iso-8859-9"))
    convert_csv(
        source,
        target,
        column="adres",
        encoding="iso-8859-9",
        delimiter="\t",
        output_encoding="utf-8",
    )
    assert "Şişli" in target.read_text(encoding="utf-8")
    assert not target.read_bytes().startswith(b"\xef\xbb\xbf")


def test_csv_keeps_multiline_cells(tmp_path: Path) -> None:
    source = tmp_path / "in.csv"
    target = tmp_path / "out.csv"
    source.write_text('adres,not\n"Gül Sk.\nBolu",x\n', encoding="utf-8")
    assert convert_csv(source, target, column="adres").rows == 1
    assert read_rows(target)[0]["tradres_il"] == "Bolu"


def test_csv_empty_cells_and_blank_lines(tmp_path: Path) -> None:
    source = tmp_path / "in.csv"
    target = tmp_path / "out.csv"
    source.write_text("id,adres\n1,\n\n2,Bolu\n", encoding="utf-8")
    summary = convert_csv(source, target, column="adres")
    assert (summary.rows, summary.empty, summary.uneven) == (2, 1, 0)
    assert read_rows(target)[0]["tradres_guven"] == "0.00"


def test_csv_with_an_unquoted_comma_loses_nothing(tmp_path: Path) -> None:
    source = tmp_path / "in.csv"
    target = tmp_path / "out.csv"
    source.write_text("id,adres\n1,Gül Sk. 5, Merkez/Bolu\n2\n", encoding="utf-8")
    summary = convert_csv(source, target, column="adres")
    rows = read_rows(target)
    assert rows[0]["adres"] == "Gül Sk. 5, Merkez/Bolu"
    assert rows[0]["tradres_il"] == "Bolu"
    assert rows[1]["id"] == "2"
    assert summary.uneven == 2


def test_csv_blocks_formulas_in_new_cells(tmp_path: Path) -> None:
    source = tmp_path / "in.csv"
    target = tmp_path / "out.csv"
    source.write_text('adres\n"=cmd() Bolu"\n', encoding="utf-8")
    convert_csv(source, target, column="adres")
    row = read_rows(target)[0]
    assert row["adres"] == "=cmd() Bolu"
    assert row["tradres_kalan"].startswith("'=")


def test_csv_counts_unparsed_rows(tmp_path: Path) -> None:
    source = tmp_path / "in.csv"
    target = tmp_path / "out.csv"
    source.write_text("adres\nBolu xqzv\n", encoding="utf-8")
    assert convert_csv(source, target, column="adres").with_kalan == 1


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(CliError, match="not found"):
        convert_csv(tmp_path / "no.csv", tmp_path / "out.csv", column="adres")


def test_output_must_differ_from_input(tmp_path: Path) -> None:
    source = tmp_path / "in.csv"
    source.write_text("adres\nBolu\n", encoding="utf-8")
    with pytest.raises(CliError, match="must not be the input"):
        convert_csv(source, source, column="adres")
    assert source.read_text(encoding="utf-8") == "adres\nBolu\n"


def test_second_run_on_own_output_is_refused(tmp_path: Path) -> None:
    source = tmp_path / "in.csv"
    target = tmp_path / "out.csv"
    source.write_text("adres\nBolu\n", encoding="utf-8")
    convert_csv(source, target, column="adres")
    with pytest.raises(CliError, match="already has result columns"):
        convert_csv(target, tmp_path / "again.csv", column="adres")


def test_unknown_encoding_is_a_clean_error(tmp_path: Path) -> None:
    source = tmp_path / "in.csv"
    source.write_text("adres\nBolu\n", encoding="utf-8")
    with pytest.raises(CliError, match="unknown encoding"):
        convert_csv(source, tmp_path / "out.csv", column="adres", encoding="nope")


def test_output_folder_missing_is_a_clean_error(tmp_path: Path) -> None:
    source = tmp_path / "in.csv"
    source.write_text("adres\nBolu\n", encoding="utf-8")
    with pytest.raises(CliError):
        convert_csv(source, tmp_path / "no" / "out.csv", column="adres")


def test_parse_csv_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "in.csv"
    target = tmp_path / "out.csv"
    source.write_text("adres\nBolu\n", encoding="utf-8")
    code = main(["parse-csv", str(source), "--column", "adres", "-o", str(target)])
    assert code == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "1 rows" in captured.err


def test_tab_can_be_typed_as_backslash_t(tmp_path: Path) -> None:
    source = tmp_path / "in.csv"
    target = tmp_path / "out.csv"
    source.write_text("ad\tadres\nx\tBolu\n", encoding="utf-8")
    args = ["parse-csv", str(source), "--column", "adres", "-o", str(target), "--delimiter", r"\t"]
    assert main(args) == 0
    assert read_rows(target, "\t")[0]["tradres_il"] == "Bolu"


def test_delimiter_must_be_one_character(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stop:
        main(["parse-csv", "a", "--column", "b", "-o", "c", "--delimiter", "ab"])
    assert stop.value.code == 2
    assert "one character" in capsys.readouterr().err


def test_errors_are_one_line_with_exit_code_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["parse-csv", str(tmp_path / "no.csv"), "--column", "a", "-o", "b.csv"])
    assert code == 1
    assert capsys.readouterr().err.startswith("tradres: error: file not found")


def test_ctrl_c_says_the_output_is_not_complete(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def stop(*_args: object, **_kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "convert_csv", stop)
    assert main(["parse-csv", "a", "--column", "b", "-o", "c"]) == 130
    assert "not complete" in capsys.readouterr().err


def test_csv_gives_the_same_result_as_parse(tmp_path: Path) -> None:
    text = "Kızılay Mah. Gül Sk. No:5/3 Çankaya/Ankara"
    source = tmp_path / "in.csv"
    target = tmp_path / "out.csv"
    source.write_text(f"adres\n{text}\n", encoding="utf-8")
    convert_csv(source, target, column="adres")
    row = read_rows(target)[0]
    address = parse(text)
    for name in FIELDS:
        assert row[f"tradres_{name}"] == (getattr(address, name) or "")


def test_csv_of_one_column_with_commas_gives_no_warning(tmp_path: Path) -> None:
    source = tmp_path / "in.csv"
    target = tmp_path / "out.csv"
    source.write_text("adres\nGül Sk. No:5, Merkez/Bolu\n", encoding="utf-8")
    summary = convert_csv(source, target, column="adres")
    assert summary.uneven == 0
    assert read_rows(target)[0]["adres"] == "Gül Sk. No:5, Merkez/Bolu"
