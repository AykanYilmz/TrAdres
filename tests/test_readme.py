"""The examples in the README files must stay true."""

from __future__ import annotations

from pathlib import Path

import pytest

from tradres import parse

ROOT = Path(__file__).parent.parent


@pytest.mark.parametrize("name", ["README.md", "README.tr.md"])
def test_examples_match_the_parser(name: str) -> None:
    readme = (ROOT / name).read_text(encoding="utf-8")
    messy = parse("CANKAYA/ANKARA kizilay mah gmk bulvarı 12/8")
    assert messy.format() in readme
    assert f'"confidence": {messy.confidence:.2f}' in readme
    assert parse("ataturk mh 23nisan cd no 5 d 3 bolu merkez").format() in readme
