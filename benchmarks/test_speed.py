"""Speed of the parser. Run with ``uv run pytest benchmarks --benchmark-only --no-cov``.

These are not part of the normal test run: timing depends on the machine, so
they report numbers and do not pass or fail.
"""

from __future__ import annotations

import csv
from itertools import cycle, islice
from pathlib import Path

import pytest
from pytest_benchmark.fixture import BenchmarkFixture

from eval.dataset import load_cases
from tradres import parse
from tradres.cli import convert_csv
from tradres.gazetteer import load_gazetteer

BATCH_SIZE = 10_000
TIDY_ADDRESS = "Kızılay Mah. Gül Sk. No:5/3 Çankaya/Ankara"
MISSPELLED_ADDRESS = "Kzılay Mah. Gül Sk. No:5/3 Çankya/Ankra"


@pytest.fixture(scope="module")
def addresses() -> list[str]:
    """10,000 addresses, made by repeating the development set."""
    texts = [case.girdi for case in load_cases()]
    return list(islice(cycle(texts), BATCH_SIZE))


def test_first_load_of_the_place_list(benchmark: BenchmarkFixture) -> None:
    def load_again() -> None:
        load_gazetteer.cache_clear()
        load_gazetteer()

    benchmark.pedantic(load_again, rounds=5)  # type: ignore[no-untyped-call]


def test_one_tidy_address(benchmark: BenchmarkFixture) -> None:
    load_gazetteer()
    benchmark(parse, TIDY_ADDRESS)


def test_one_misspelled_address(benchmark: BenchmarkFixture) -> None:
    load_gazetteer()
    benchmark(parse, MISSPELLED_ADDRESS)


def test_10000_addresses(benchmark: BenchmarkFixture, addresses: list[str]) -> None:
    load_gazetteer()

    def parse_all() -> None:
        for text in addresses:
            parse(text)

    benchmark.pedantic(parse_all, rounds=3)  # type: ignore[no-untyped-call]


def test_10000_csv_rows(benchmark: BenchmarkFixture, addresses: list[str], tmp_path: Path) -> None:
    source = tmp_path / "in.csv"
    with source.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["adres"])
        writer.writerows([text] for text in addresses)

    def convert() -> None:
        convert_csv(source, tmp_path / "out.csv", column="adres")

    benchmark.pedantic(convert, rounds=3)  # type: ignore[no-untyped-call]
