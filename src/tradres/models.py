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
    "tarif",
)

#: Fields written as "<value> <word>", in output order.
_NAMED_PARTS: tuple[tuple[str, str], ...] = (
    ("mahalle", "Mah."),
    ("bulvar", "Blv."),
    ("cadde", "Cad."),
    ("sokak", "Sk."),
    ("site", "Sit."),
    ("bina_adi", "Apt."),
    ("blok", "Blok"),
)

#: Fields written as "<label><value>", in output order.
_NUMBER_PARTS: tuple[tuple[str, str], ...] = (
    ("bina_no", "No:"),
    ("kat", "K:"),
    ("daire", "D:"),
)


@dataclass(frozen=True)
class Address:
    """A parsed address. A part that was not found is ``None``.

    Names have no type word: ``cadde`` is ``"23 Nisan"``, not ``"23 Nisan Cad."``.
    Köy names are stored in ``mahalle``. ``tarif`` holds directions as written
    ("okul yanı"). Numbers are strings because values such
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
    tarif: str | None = None
    kalan: str | None = None
    confidence: float = 0.0
    field_confidence: Mapping[str, float] = field(default_factory=dict, hash=False)

    def format(self) -> str:
        """One standard spelling of the address.

        The order is always the same: mahalle, street, building, numbers,
        directions, postal code, ilçe/il. ``kalan`` is left out because it is
        not a known part of an address; read it from the field.

        >>> Address(il="Bolu", ilce="Merkez", mahalle="Atatürk", bina_no="5", daire="3").format()
        'Atatürk Mah. No:5 D:3 Merkez/Bolu'
        """
        parts = [
            f"{getattr(self, name)} {word}" for name, word in _NAMED_PARTS if getattr(self, name)
        ]
        parts += [
            f"{label}{getattr(self, name)}" for name, label in _NUMBER_PARTS if getattr(self, name)
        ]
        parts += [value for value in (self.tarif, self.posta_kodu) if value]
        place = "/".join(value for value in (self.ilce, self.il) if value)
        if place:
            parts.append(place)
        return " ".join(parts)

    def to_dict(self) -> dict[str, object]:
        """All parts and scores as a plain dictionary, ready for JSON."""
        data: dict[str, object] = {item.name: getattr(self, item.name) for item in fields(self)}
        data["field_confidence"] = dict(self.field_confidence)
        return data
