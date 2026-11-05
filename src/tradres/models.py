"""The result of parsing an address."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, fields

__all__ = ["FIELDS", "Address"]

#: Address parts, from the largest place to the smallest detail.
FIELDS: tuple[str, ...] = (
    "il",
    "ilce",
    "mahalle",
    "bulvar",
    "cadde",
    "sokak",
    "site",
    "bina_adi",
    "blok",
    "bina_no",
    "kat",
    "daire",
    "posta_kodu",
)


@dataclass(frozen=True)
class Address:
    """A parsed address. A part that was not found is ``None``.

    Names have no type word: ``cadde`` is ``"23 Nisan"``, not ``"23 Nisan Cad."``.
    Köy names are stored in ``mahalle``. Numbers are strings because values such
    as ``"5A"`` are common. ``kalan`` keeps the text that could not be understood,
    so nothing from the input is lost.

    ``confidence`` (0.0-1.0) scores the whole address and ``field_confidence``
    each field that was found. See :mod:`tradres.scoring`.
    """

    il: str | None = None
    ilce: str | None = None
    mahalle: str | None = None
    bulvar: str | None = None
    cadde: str | None = None
    sokak: str | None = None
    site: str | None = None
    bina_adi: str | None = None
    blok: str | None = None
    bina_no: str | None = None
    kat: str | None = None
    daire: str | None = None
    posta_kodu: str | None = None
    kalan: str | None = None
    confidence: float = 0.0
    field_confidence: Mapping[str, float] = field(default_factory=dict, hash=False)

    def to_dict(self) -> dict[str, object]:
        """All parts and scores as a plain dictionary, ready for JSON."""
        data: dict[str, object] = {item.name: getattr(self, item.name) for item in fields(self)}
        data["field_confidence"] = dict(self.field_confidence)
        return data
