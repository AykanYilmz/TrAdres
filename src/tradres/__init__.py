"""TrAdres: parse, normalize and validate Turkish addresses."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("tradres")
except PackageNotFoundError:  # pragma: no cover - only when running from a raw checkout
    __version__ = "0.0.0"

__all__ = ["__version__"]
