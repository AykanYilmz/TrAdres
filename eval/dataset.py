"""Load and validate the hand-labelled addresses in ``eval/addresses/*.yaml``."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

from tradres.gazetteer import Gazetteer, load_gazetteer
from tradres.models import FIELDS

ADDRESSES_DIR = Path(__file__).parent / "addresses"
#: The locked test set: the parser is never tuned on these addresses.
HOLDOUT_DIR = Path(__file__).parent / "holdout"

#: ``kalan`` documents the text that should stay unparsed. It is not scored.
LABEL_KEYS = frozenset(FIELDS) | {"kalan"}

#: Set by the loader, never by hand. The expected mahalle is missing from the
#: gazetteer, or it is there but spelled differently (such as "Firat" for "Fırat").
MISSING_TAG = "gazetteer_disi"
SPELLING_TAG = "gazetteer_yazim_farki"
AUTO_TAGS = frozenset({MISSING_TAG, SPELLING_TAG})

#: Tags split the report into groups. A fixed list catches typos in the data.
TAGS = frozenset(
    {
        "temiz",  # tidy, complete address
        "ascii",  # typed without Turkish letters
        "buyuk_harf",  # ALL CAPS
        "kisaltma",  # abbreviated keywords (mh, cd, sk ...)
        "birlesik",  # missing spaces (23nisan, no5)
        "yazim_hatasi",  # typing mistakes (Kzılay)
        "sira",  # unusual order (il/ilçe first, mahalle last ...)
        "il_eksik",  # province not written
        "ilce_eksik",  # district not written
        "mahalle_eksik",  # neighbourhood not written
        "noktalama",  # no punctuation or odd punctuation
        "no_bolu",  # building/flat written as 5/3
        "bina_adi",  # named building
        "site",  # housing estate, often with a block
        "koy",  # village address
        "tarif",  # directions ("... karşısı") that stay in kalan
        "posta_kodu",  # has a postal code
        "tuzak",  # looks like one thing but is another (D 100 = a road)
    }
)


class DatasetError(ValueError):
    """A labelled address breaks the format rules (see eval/README.md)."""


@dataclass(frozen=True)
class Case:
    """One labelled address."""

    id: str
    girdi: str
    beklenen: Mapping[str, str]
    etiketler: frozenset[str]


def load_cases(
    directory: Path = ADDRESSES_DIR, *, gazetteer: Gazetteer | None = None
) -> list[Case]:
    """Read every YAML file in ``directory``, validated and sorted by id."""
    gaz = gazetteer or load_gazetteer()
    cases: dict[str, Case] = {}
    for path in sorted(directory.glob("*.yaml")):
        entries = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(entries, list):
            raise DatasetError(f"{path.name}: the file must be a YAML list")
        for entry in entries:
            case = parse_entry(entry, gaz, where=path.name)
            if case.id in cases:
                raise DatasetError(f"{path.name}: duplicate id {case.id!r}")
            cases[case.id] = case
    return [cases[key] for key in sorted(cases)]


def parse_entry(entry: object, gaz: Gazetteer, *, where: str = "entry") -> Case:
    """Check one YAML entry and turn it into a :class:`Case`."""
    if not isinstance(entry, dict):
        raise DatasetError(f"{where}: every entry must be a mapping, got {entry!r}")
    case_id = entry.get("id")
    if not isinstance(case_id, str) or not case_id:
        raise DatasetError(f"{where}: 'id' must be a quoted string, got {case_id!r}")
    where = f"{where} [{case_id}]"

    girdi = entry.get("girdi")
    if not isinstance(girdi, str) or not girdi.strip():
        raise DatasetError(f"{where}: 'girdi' must be a non-empty string")

    unknown = set(entry) - {"id", "girdi", "beklenen", "etiketler", "not"}
    if unknown:
        raise DatasetError(f"{where}: unknown keys {sorted(unknown)}")

    beklenen = _check_labels(entry.get("beklenen"), where)
    etiketler = _check_tags(entry.get("etiketler", []), where)
    etiketler |= _check_places(beklenen, gaz, where)
    return Case(id=case_id, girdi=girdi, beklenen=beklenen, etiketler=etiketler)


def _check_labels(labels: object, where: str) -> dict[str, str]:
    if not isinstance(labels, dict) or not labels:
        raise DatasetError(f"{where}: 'beklenen' must be a non-empty mapping")
    unknown = set(labels) - LABEL_KEYS
    if unknown:
        raise DatasetError(f"{where}: unknown fields {sorted(map(str, unknown))}")
    for key, value in labels.items():
        # An unquoted 5 is an int in YAML, and "5A" would be a string: keep one type.
        if not isinstance(value, str) or not value.strip():
            raise DatasetError(f"{where}: {key} must be a quoted string, got {value!r}")
    return dict(labels)


def _check_tags(tags: object, where: str) -> frozenset[str]:
    if not isinstance(tags, list):
        raise DatasetError(f"{where}: 'etiketler' must be a list")
    automatic = AUTO_TAGS.intersection(map(str, tags))
    if automatic:
        raise DatasetError(f"{where}: {sorted(automatic)} are set automatically, do not write them")
    unknown = set(map(str, tags)) - TAGS
    if unknown:
        raise DatasetError(f"{where}: unknown tags {sorted(unknown)}")
    return frozenset(map(str, tags))


def _check_places(labels: Mapping[str, str], gaz: Gazetteer, where: str) -> frozenset[str]:
    """Check il and ilçe spelling. Return the automatic tags for the mahalle."""
    il, ilce, mahalle = labels.get("il"), labels.get("ilce"), labels.get("mahalle")
    if il is not None:
        found = gaz.find_il(il)
        if found is None or found.ad != il:
            raise DatasetError(f"{where}: il {il!r} is not an official name")
    if ilce is not None:
        names = {i.ad for i in gaz.find_ilce(ilce, il=il)}
        if ilce not in names:
            raise DatasetError(f"{where}: ilce {ilce!r} is not an official name in il {il!r}")
    if mahalle is None:
        return frozenset()
    matches = gaz.find_mahalle(mahalle, ilce=ilce, il=il)
    if not matches:
        return frozenset({MISSING_TAG})
    if mahalle not in {m.ad for m in matches}:
        return frozenset({SPELLING_TAG})
    return frozenset()


def tag_counts(cases: Iterable[Case]) -> dict[str, int]:
    """How many cases carry each tag."""
    counts: dict[str, int] = {}
    for case in cases:
        for tag in case.etiketler:
            counts[tag] = counts.get(tag, 0) + 1
    return dict(sorted(counts.items()))
