"""Smoke tests: the package is importable and ships its type marker."""

from importlib.resources import files

import tradres


def test_version_is_a_non_empty_string() -> None:
    assert isinstance(tradres.__version__, str)
    assert tradres.__version__


def test_py_typed_marker_is_shipped() -> None:
    assert files("tradres").joinpath("py.typed").is_file()
