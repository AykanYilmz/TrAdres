"""Official place names of Turkey: il -> ilçe -> mahalle (and köy).

The data is built from Wikidata by ``scripts/build_gazetteer.py`` and shipped
with the package as ``data/gazetteer.json.gz``; see DATA_SOURCES.md.

Lookups are exact on :func:`~tradres.normalization.ascii_key`, so case and
Turkish letters do not matter (``"cankaya"`` finds ``"Çankaya"``). Fuzzy
matching for typos is a separate step (``matching.py``).

Index: a plain ``dict`` from ASCII key to the places with that name. A lookup
is O(1). A trie would only help for prefix or fuzzy-candidate searches, which
we do not need yet.
"""

from __future__ import annotations

import gzip
import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import cache, cached_property
from importlib.resources import files
from typing import Any

from tradres.abbreviations import load_ascii_names
from tradres.matching import DEFAULT_CONFIG, MatchConfig, closest
from tradres.normalization import ascii_key

__all__ = [
    "Gazetteer",
    "GazetteerDataError",
    "Il",
    "Ilce",
    "Mahalle",
    "load_gazetteer",
]

_DATA_FILE = "gazetteer.json.gz"
_FORMAT_VERSION = 1


@dataclass(frozen=True)
class Il:
    """A province (il).

    Attributes:
        ad: Official name, e.g. ``"Şanlıurfa"``.
        plaka: Licence plate code, e.g. ``"63"``.
        diger_adlar: Other names people write, e.g. ``("Urfa",)``.
    """

    ad: str
    plaka: str
    diger_adlar: tuple[str, ...] = ()


@dataclass(frozen=True)
class Ilce:
    """A district (ilçe). ``il`` is the name of its province."""

    ad: str
    il: str
    diger_adlar: tuple[str, ...] = ()


@dataclass(frozen=True)
class Mahalle:
    """A neighbourhood (mahalle) or village (köy) inside a district.

    Wikidata does not reliably say which of the two a place is, so both are
    kept as ``Mahalle``.
    """

    ad: str
    ilce: str
    il: str


class GazetteerDataError(ValueError):
    """The gazetteer data is malformed or has an unsupported format."""


class Gazetteer:
    """Place names with lookup indexes. Build it with :func:`load_gazetteer`."""

    def __init__(self, data: Mapping[str, object]) -> None:
        if data.get("format") != _FORMAT_VERSION:
            raise GazetteerDataError(f"unsupported gazetteer format: {data.get('format')!r}")
        self.source = str(data.get("source", ""))
        self.retrieved = str(data.get("retrieved", ""))

        self._iller: dict[str, Il] = {}  # ascii key of the official name -> Il
        self._il_index: dict[str, Il] = {}  # ascii key of every name -> Il
        self._ilceler: dict[str, list[Ilce]] = defaultdict(list)  # il key -> its districts
        self._ilce_index: dict[str, list[Ilce]] = defaultdict(list)
        self._mahalleler: dict[tuple[str, str], list[Mahalle]] = defaultdict(list)
        self._mahalle_index: dict[str, list[Mahalle]] = defaultdict(list)

        try:
            for il_data in _as_list(data["iller"]):
                self._add_il(il_data)
        except (KeyError, TypeError) as error:
            raise GazetteerDataError(f"malformed gazetteer data: {error!r}") from error

    def _add_il(self, data: Mapping[str, object]) -> None:
        il = Il(ad=str(data["ad"]), plaka=str(data["plaka"]), diger_adlar=_names(data))
        il_key = ascii_key(il.ad)
        self._iller[il_key] = il
        for name in (il.ad, *il.diger_adlar):
            self._il_index[ascii_key(name)] = il
        for ilce_data in _as_list(data["ilceler"]):
            ilce = Ilce(ad=str(ilce_data["ad"]), il=il.ad, diger_adlar=_names(ilce_data))
            self._ilceler[il_key].append(ilce)
            for name in {ascii_key(n) for n in (ilce.ad, *ilce.diger_adlar)}:
                self._ilce_index[name].append(ilce)
            mahalleler = self._mahalleler[(il_key, ascii_key(ilce.ad))]
            for mahalle_name in _as_list(ilce_data["mahalleler"]):
                mahalle = Mahalle(ad=str(mahalle_name), ilce=ilce.ad, il=il.ad)
                mahalleler.append(mahalle)
                self._mahalle_index[ascii_key(mahalle.ad)].append(mahalle)

    # ------------------------------------------------------------------ #
    # Listing
    # ------------------------------------------------------------------ #

    @property
    def iller(self) -> tuple[Il, ...]:
        """All provinces, sorted by name."""
        return tuple(self._iller.values())

    def ilceleri(self, il: str) -> tuple[Ilce, ...]:
        """Districts of a province (any accepted spelling of its name)."""
        found = self.find_il(il)
        return tuple(self._ilceler[ascii_key(found.ad)]) if found else ()

    def mahalleleri(self, il: str, ilce: str) -> tuple[Mahalle, ...]:
        """Neighbourhoods and villages of one district."""
        found = self.find_ilce(ilce, il=il)
        if len(found) != 1:
            return ()
        return tuple(self._mahalleler[(ascii_key(found[0].il), ascii_key(found[0].ad))])

    # ------------------------------------------------------------------ #
    # Lookups
    # ------------------------------------------------------------------ #

    def find_il(self, name: str) -> Il | None:
        """The province with this name, or ``None``.

        >>> load_gazetteer().find_il("SANLIURFA").ad
        'Şanlıurfa'
        >>> load_gazetteer().find_il("Urfa").ad
        'Şanlıurfa'
        """
        return self._il_index.get(ascii_key(name))

    def find_ilce(self, name: str, *, il: str | None = None) -> list[Ilce]:
        """Districts with this name, optionally only in province ``il``.

        Several provinces can have a district with the same name ("Merkez",
        "Ereğli"), so the result is a list.

        >>> [i.il for i in load_gazetteer().find_ilce("cankaya")]
        ['Ankara']
        """
        found = self._ilce_index.get(ascii_key(name), [])
        if il is None:
            return list(found)
        il_found = self.find_il(il)
        return [i for i in found if il_found is not None and i.il == il_found.ad]

    def find_mahalle(
        self, name: str, *, ilce: str | None = None, il: str | None = None
    ) -> list[Mahalle]:
        """Neighbourhoods/villages with this name, optionally filtered.

        >>> len(load_gazetteer().find_mahalle("Atatürk")) > 100  # a very common name
        True
        """
        found = self._mahalle_index.get(ascii_key(name), [])
        il_found = self.find_il(il) if il is not None else None
        if il is not None and il_found is None:
            return []
        ilce_keys = (
            {ascii_key(i.ad) for i in self.find_ilce(ilce, il=il)} if ilce is not None else None
        )
        return [
            m
            for m in found
            if (il_found is None or m.il == il_found.ad)
            and (ilce_keys is None or ascii_key(m.ilce) in ilce_keys)
        ]

    def provinces_of_district(self, name: str) -> list[Il]:
        """Provinces that have a district with this name.

        If the list has one element, a missing province in an address can be
        filled in from the district alone.

        >>> [il.ad for il in load_gazetteer().provinces_of_district("Kadıköy")]
        ['İstanbul']
        """
        return [self._iller[ascii_key(i.il)] for i in self.find_ilce(name)]

    # ------------------------------------------------------------------ #
    # Fuzzy lookups (typos)
    # ------------------------------------------------------------------ #

    def fuzzy_il(self, name: str, config: MatchConfig = DEFAULT_CONFIG) -> Il | None:
        """The province a misspelled name most likely means.

        >>> load_gazetteer().fuzzy_il("Malatay").ad
        'Malatya'
        """
        key = ascii_key(name)
        if len(key) < config.min_length:
            return None
        hit = closest(key, self._il_index, config)
        return self._il_index[hit] if hit is not None else None

    @cached_property
    def _single_province_districts(self) -> dict[str, Ilce]:
        return {key: found[0] for key, found in self._ilce_index.items() if len(found) == 1}

    def fuzzy_ilce(
        self, name: str, *, il: str | None = None, config: MatchConfig = DEFAULT_CONFIG
    ) -> Ilce | None:
        """The district a misspelled name most likely means.

        Without ``il``, only district names used by one province are searched.

        >>> load_gazetteer().fuzzy_ilce("Çankya", il="Ankara").ad
        'Çankaya'
        """
        key = ascii_key(name)
        if len(key) < config.min_length:
            return None
        pool = (
            {ascii_key(n): i for i in self.ilceleri(il) for n in (i.ad, *i.diger_adlar)}
            if il is not None
            else self._single_province_districts
        )
        hit = closest(key, pool, config)
        return pool[hit] if hit is not None else None

    def fuzzy_mahalle(
        self, name: str, *, il: str, ilce: str, config: MatchConfig = DEFAULT_CONFIG
    ) -> Mahalle | None:
        """The mahalle of one district that a misspelled name most likely means."""
        key = ascii_key(name)
        if len(key) < config.min_mahalle_length:
            return None
        pool = {ascii_key(m.ad): m for m in self.mahalleleri(il, ilce)}
        hit = closest(key, pool, config)
        return pool[hit] if hit is not None else None

    # ------------------------------------------------------------------ #
    # Spelling
    # ------------------------------------------------------------------ #

    @cached_property
    def _word_spellings(self) -> dict[str, str]:
        """ASCII key -> the most common spelling among all place-name words."""
        counts: dict[str, Counter[str]] = defaultdict(Counter)
        names = [
            *(il.ad for il in self.iller),
            *(i.ad for ilceler in self._ilceler.values() for i in ilceler),
            *(m.ad for mahalleler in self._mahalleler.values() for m in mahalleler),
        ]
        for name in names:
            for word in name.split():
                if word.isalpha():
                    counts[ascii_key(word)][word] += 1
        keep = load_ascii_names()
        return {key: found.most_common(1)[0][0] for key, found in counts.items() if key not in keep}

    def respell(self, name: str) -> str:
        """Bring back the Turkish letters of words typed in plain ASCII.

        Place names are the best word list we have: "Atatürk", "Kurtuluş" and
        "Şehit" are in thousands of them. Words that already have Turkish
        letters are left alone, and so are words we do not know.

        >>> load_gazetteer().respell("19 Mayis")
        '19 Mayıs'
        >>> load_gazetteer().respell("Ataturk Bulvarı")
        'Atatürk Bulvarı'
        """
        spellings = self._word_spellings
        words = name.split()
        return " ".join(
            spellings.get(ascii_key(word), word) if word.isascii() else word for word in words
        )

    def __repr__(self) -> str:
        counts = (
            f"{len(self._iller)} il, {sum(map(len, self._ilceler.values()))} ilçe, "
            f"{sum(map(len, self._mahalleler.values()))} mahalle"
        )
        return f"<Gazetteer {counts}, retrieved {self.retrieved}>"


def _as_list(value: object) -> list[Any]:
    if not isinstance(value, list):
        raise TypeError(f"expected a list, got {type(value).__name__}")
    return value


def _names(data: Mapping[str, object]) -> tuple[str, ...]:
    value: object = data.get("diger_adlar", [])
    if not isinstance(value, Iterable):
        raise TypeError("diger_adlar must be a list")
    return tuple(str(name) for name in value)


@cache
def load_gazetteer() -> Gazetteer:
    """Load the bundled gazetteer once (lazy) and reuse it afterwards (cached)."""
    raw = (files("tradres") / "data" / _DATA_FILE).read_bytes()
    data = json.loads(gzip.decompress(raw))
    if not isinstance(data, dict):
        raise GazetteerDataError("gazetteer data must be a JSON object")
    return Gazetteer(data)
