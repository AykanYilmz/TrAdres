"""Command line interface: ``tradres parse`` and ``tradres parse-csv``."""

from __future__ import annotations

import argparse
import codecs
import csv
import io
import json
import sys
import time
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from tradres import __version__
from tradres.models import FIELDS, Address
from tradres.normalization import tr_lower
from tradres.parser import parse

__all__ = ["main"]

_PREFIX = "tradres_"
_RESULT_COLUMNS = (
    *(f"{_PREFIX}{name}" for name in FIELDS),
    f"{_PREFIX}kalan",
    f"{_PREFIX}guven",
    f"{_PREFIX}adres",
)
_DELIMITERS = ",;\t|"
_CHUNK_SIZE = 1 << 20
_FORMULA_STARTS = ("=", "+", "-", "@")
_BAR_WIDTH = 24
_REFRESH_SECONDS = 0.1
_INTERRUPTED = 130


class CliError(Exception):
    """A problem to show the user as one line, without a traceback."""


def detect_encoding(path: Path) -> str:
    """Guess a text file's encoding: BOM, then UTF-8, then Turkish Windows.

    Excel in Turkey saves "CSV" as cp1254. Those bytes are almost never valid
    UTF-8, so a full UTF-8 check separates the two well.
    """
    with path.open("rb") as file:
        start = file.read(4)
        if start.startswith(codecs.BOM_UTF8):
            return "utf-8-sig"
        if start.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
            return "utf-16"
        decoder = codecs.getincrementaldecoder("utf-8")()
        try:
            decoder.decode(start)
            while chunk := file.read(_CHUNK_SIZE):
                decoder.decode(chunk)
            decoder.decode(b"", final=True)
        except UnicodeDecodeError:
            return "cp1254"
    return "utf-8"


def find_column(header: Sequence[str], column: str) -> int | None:
    """Index of a column, ignoring case and spaces around the name."""
    wanted = tr_lower(column.strip())
    for index, name in enumerate(header):
        if tr_lower(name.strip()) == wanted:
            return index
    return None


def detect_dialect(
    header_line: str, column: str, delimiters: str = _DELIMITERS
) -> tuple[str, list[str], int]:
    """Find the delimiter that makes ``column`` a real column of the header.

    Sniffing the data is unreliable because addresses are full of commas, but
    the user has told us one column name, and only the right delimiter finds it.
    """
    seen: list[str] = []
    for delimiter in delimiters:
        header = next(csv.reader([header_line], delimiter=delimiter), [])
        index = find_column(header, column)
        if index is not None:
            return delimiter, header, index
        if len(header) > len(seen):
            seen = header
    names = ", ".join(seen) or "(empty)"
    raise CliError(f"column {column!r} not found; columns are: {names}")


def fit_row(row: Sequence[str], width: int, delimiter: str) -> tuple[list[str], bool]:
    """Make a row as wide as the header and say whether it had to be changed.

    An unquoted delimiter in an address gives a row extra cells. They join the
    last cell, so no text is lost; the address is often the last column.
    """
    if len(row) == width:
        return list(row), False
    if len(row) < width:
        return [*row, *[""] * (width - len(row))], True
    return [*row[: width - 1], delimiter.join(row[width - 1 :])], True


def safe_cell(value: str) -> str:
    """Stop a spreadsheet from running a cell of ours as a formula."""
    return f"'{value}" if value.startswith(_FORMULA_STARTS) else value


def result_cells(address: Address) -> list[str]:
    """The cells of one address, in the order of ``_RESULT_COLUMNS``."""
    parts = [getattr(address, name) or "" for name in (*FIELDS, "kalan")]
    return [
        *(safe_cell(part) for part in parts),
        f"{address.confidence:.2f}",
        safe_cell(address.format()),
    ]


@dataclass
class Summary:
    """What happened in one CSV run."""

    rows: int = 0
    empty: int = 0
    with_kalan: int = 0
    uneven: int = 0
    total_confidence: float = 0.0

    def add(self, address: Address, *, blank: bool, uneven: bool) -> None:
        """Count one row."""
        self.rows += 1
        self.empty += blank
        self.with_kalan += address.kalan is not None
        self.uneven += uneven
        self.total_confidence += address.confidence

    def __str__(self) -> str:
        parsed = self.rows - self.empty
        mean = self.total_confidence / parsed if parsed else 0.0
        lines = [
            f"{self.rows} rows, {self.empty} empty, mean confidence {mean:.2f}",
            f"unparsed text in {self.with_kalan} of them (see {_PREFIX}kalan)",
        ]
        if self.uneven:
            lines.append(f"warning: column count differs from the header in {self.uneven} rows")
        return "\n".join(lines)


def progress_line(done: int, total: int, rows: int, elapsed: float) -> str:
    """One line of the progress bar. ``done`` and ``total`` are bytes."""
    share = min(done / total, 1.0) if total else 1.0
    filled = round(share * _BAR_WIDTH)
    bar = "#" * filled + "-" * (_BAR_WIDTH - filled)
    speed = rows / elapsed if elapsed > 0 else 0.0
    return f"[{bar}] {share:4.0%}  {rows} rows  {speed:.0f}/s"


class Progress:
    """A progress bar on stderr, so it never mixes with the data."""

    def __init__(self, total: int, *, enabled: bool, stream: TextIO) -> None:
        self._total = total
        self._enabled = enabled
        self._stream = stream
        self._start = time.monotonic()
        self._last = 0.0

    def update(self, done: int, rows: int, *, force: bool = False) -> None:
        """Redraw the bar, but not more often than the screen needs."""
        if not self._enabled:
            return
        now = time.monotonic()
        if force or now - self._last >= _REFRESH_SECONDS:
            self._last = now
            line = progress_line(done, self._total, rows, now - self._start)
            self._stream.write(f"\r{line}")
            self._stream.flush()

    def close(self, done: int, rows: int) -> None:
        """Draw the last state and end the line."""
        if self._enabled:
            self.update(done, rows, force=True)
            self._stream.write("\n")


def parse_rows(
    rows: Iterable[Sequence[str]], column: int, width: int, delimiter: str, summary: Summary
) -> Iterator[list[str]]:
    """Add the result cells to each CSV row. Blank lines are not rows."""
    for row in rows:
        if not row:
            continue
        cells, uneven = fit_row(row, width, delimiter)
        text = cells[column]
        address = parse(text)
        summary.add(address, blank=not text.strip(), uneven=uneven)
        yield [*cells, *result_cells(address)]


def convert_csv(
    source: Path,
    target: Path,
    *,
    column: str,
    encoding: str | None = None,
    delimiter: str | None = None,
    output_encoding: str = "utf-8-sig",
    progress: bool = False,
) -> Summary:
    """Parse one column of a CSV file and write the file with result columns."""
    if not source.is_file():
        raise CliError(f"file not found: {source}")
    if target.exists() and target.samefile(source):
        raise CliError("the output file must not be the input file")

    try:
        with source.open("rb") as binary:
            text = io.TextIOWrapper(binary, encoding or detect_encoding(source), newline="")
            delimiter, header, index = detect_dialect(
                text.readline(), column, _DELIMITERS if delimiter is None else delimiter
            )
            taken = sorted(set(header) & set(_RESULT_COLUMNS))
            if taken:
                raise CliError(f"the input already has result columns: {', '.join(taken)}")

            summary = Summary()
            size = source.stat().st_size
            bar = Progress(size, enabled=progress, stream=sys.stderr)
            rows = csv.reader(text, delimiter=delimiter)
            with target.open("w", encoding=output_encoding, newline="") as output:
                writer = csv.writer(output, delimiter=delimiter)
                writer.writerow([*header, *_RESULT_COLUMNS])
                for row in parse_rows(rows, index, len(header), delimiter, summary):
                    writer.writerow(row)
                    bar.update(binary.tell(), summary.rows)
            bar.close(size, summary.rows)
    except (csv.Error, UnicodeError, LookupError) as error:
        raise CliError(f"could not convert {source}: {error}; try --encoding") from error
    except OSError as error:
        raise CliError(str(error)) from error
    return summary


def _run_parse(args: argparse.Namespace) -> int:
    address = parse(args.address)
    data = {**address.to_dict(), "adres": address.format()}
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def _run_parse_csv(args: argparse.Namespace) -> int:
    delimiter = "\t" if args.delimiter == r"\t" else args.delimiter
    summary = convert_csv(
        args.input,
        args.output,
        column=args.column,
        encoding=args.encoding,
        delimiter=delimiter,
        output_encoding=args.output_encoding,
        progress=sys.stderr.isatty() and not args.no_progress,
    )
    print(summary, file=sys.stderr)
    return 0


def _single_character(value: str) -> str:
    if value != r"\t" and len(value) != 1:
        raise argparse.ArgumentTypeError("must be one character")
    return value


def build_parser() -> argparse.ArgumentParser:
    """The argument parser of the ``tradres`` command."""
    parser = argparse.ArgumentParser(prog="tradres", description="Parse Turkish addresses.")
    parser.add_argument("--version", action="version", version=f"tradres {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    single = commands.add_parser("parse", help="parse one address and print JSON")
    single.add_argument("address", help="the address, in quotes")
    single.set_defaults(run=_run_parse)

    table = commands.add_parser("parse-csv", help="parse a column of a CSV file")
    table.add_argument("input", type=Path, help="input CSV file")
    table.add_argument("-o", "--output", type=Path, required=True, help="output CSV file")
    table.add_argument("--column", required=True, help="name of the address column")
    table.add_argument("--encoding", help="input encoding (default: detect)")
    table.add_argument(
        "--delimiter",
        type=_single_character,
        help=r"input delimiter, for example ';' or '\t' (default: detect)",
    )
    table.add_argument(
        "--output-encoding",
        default="utf-8-sig",
        help="output encoding (default: UTF-8 with a BOM, which Excel reads correctly)",
    )
    table.add_argument("--no-progress", action="store_true", help="do not show the progress bar")
    table.set_defaults(run=_run_parse_csv)
    return parser


def _use_utf8(stream: TextIO) -> None:
    """Print Turkish letters on any console, even one with an old code page."""
    if isinstance(stream, io.TextIOWrapper):
        stream.reconfigure(encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line and return its exit code."""
    _use_utf8(sys.stdout)
    _use_utf8(sys.stderr)
    args = build_parser().parse_args(argv)
    try:
        code: int = args.run(args)
    except CliError as error:
        print(f"tradres: error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ntradres: stopped; the output file is not complete", file=sys.stderr)
        return _INTERRUPTED
    return code
