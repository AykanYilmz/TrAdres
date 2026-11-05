"""Build the bundled gazetteer (il -> ilçe -> mahalle/köy) from Wikidata.

Usage:
    uv run python scripts/build_gazetteer.py            # download + build
    uv run python scripts/build_gazetteer.py --offline  # rebuild from cached raw data

Steps:
    1. fetch:     run SPARQL queries against query.wikidata.org and cache the raw
                  JSON responses in data/raw/ (git-ignored).
    2. transform: clean labels, merge duplicates, apply reviewed corrections
                  (scripts/gazetteer_corrections.json) and resolve the hierarchy.
                  These are pure functions, unit-tested in tests/test_build_gazetteer.py.
    3. write:     src/tradres/data/gazetteer.json.gz (compact and deterministic:
                  the same input always gives byte-identical output).

Only the standard library is used, so the script runs without extra installs.
Wikidata content is CC0 (public domain); see DATA_SOURCES.md.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tradres.normalization import ascii_key  # noqa: E402  (needs the sys.path line above)

RAW_DIR = ROOT / "data" / "raw"
CORRECTIONS = Path(__file__).resolve().parent / "gazetteer_corrections.json"
ADDITIONS = Path(__file__).resolve().parent / "gazetteer_additions.json"
OUTPUT = ROOT / "src" / "tradres" / "data" / "gazetteer.json.gz"

ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "tradres-build/0.1 (https://github.com/AykanYilmz/TrAdres)"
FORMAT_VERSION = 1

# Wikidata classes
PROVINCE = "Q48336"  # province of Turkey
DISTRICT = "Q1147395"  # district of Turkey
MAHALLE = "Q17051044"  # mahalle
VILLAGE = "Q1529096"  # village of Turkey

#: Label languages in order of preference. Wikidata moves names that are the
#: same in many languages to "mul", so "tr" alone misses some districts.
LABEL_LANGUAGES = ("tr", "mul", "en", "az", "de", "ceb", "es", "it")

# --------------------------------------------------------------------------- #
# 1. Fetch
# --------------------------------------------------------------------------- #
# Notes on the queries:
# * wdt: returns only "best rank" statements, so deprecated values are skipped.
# * P131 = located in the administrative territorial entity (parent unit).
# * P576 = dissolved date; P582 on the P31 statement = "no longer this class"
#   (e.g. a village that became a mahalle in 2012-2014).
# * Labels: Turkish first, English as a fallback for items with no Turkish label.

QUERIES: dict[str, str] = {
    "provinces": f"""
SELECT ?item ?label ?plate WHERE {{
  ?item wdt:P31 wd:{PROVINCE} .
  OPTIONAL {{ ?item rdfs:label ?label FILTER(LANG(?label) = "tr") }}
  OPTIONAL {{ ?item wdt:P395 ?plate }}
}}""",
    "districts": """
SELECT ?item ?label ?otherLabel ?otherLang ?parent ?parentLabel ?grandparent
       ?dissolved ?ended WHERE {{
  ?item p:P31 ?st . ?st ps:P31 wd:{district} .
  OPTIONAL {{ ?st pq:P582 ?ended }}
  OPTIONAL {{ ?item rdfs:label ?label FILTER(LANG(?label) = "tr") }}
  OPTIONAL {{
    ?item rdfs:label ?otherLabel
    BIND(LANG(?otherLabel) AS ?otherLang)
    FILTER(?otherLang IN ({langs}) && ?otherLang != "tr")
  }}
  OPTIONAL {{
    ?item wdt:P131 ?parent .
    OPTIONAL {{ ?parent rdfs:label ?parentLabel FILTER(LANG(?parentLabel) = "tr") }}
    OPTIONAL {{ ?parent wdt:P131 ?grandparent }}
  }}
  OPTIONAL {{ ?item wdt:P576 ?dissolved }}
}}""",
}

# Settlements are split per class: one big query hits the 60 s server limit.
# No English label fallback here for the same reason (only ~24 items lack "tr").
_SETTLEMENT_QUERY = """
SELECT ?item ?label ?parent ?parentLabel ?grandparent ?dissolved ?ended WHERE {{
  ?item p:P31 ?st . ?st ps:P31 wd:{cls} .
  OPTIONAL {{ ?st pq:P582 ?ended }}
  OPTIONAL {{ ?item rdfs:label ?label FILTER(LANG(?label) = "tr") }}
  OPTIONAL {{
    ?item wdt:P131 ?parent .
    OPTIONAL {{ ?parent rdfs:label ?parentLabel FILTER(LANG(?parentLabel) = "tr") }}
    OPTIONAL {{ ?parent wdt:P131 ?grandparent }}
  }}
  OPTIONAL {{ ?item wdt:P576 ?dissolved }}
}}"""
QUERIES["districts"] = QUERIES["districts"].format(
    district=DISTRICT, langs=", ".join(f'"{lang}"' for lang in LABEL_LANGUAGES)
)
QUERIES["mahalleler"] = _SETTLEMENT_QUERY.format(cls=MAHALLE)
QUERIES["koyler"] = _SETTLEMENT_QUERY.format(cls=VILLAGE)

Row = dict[str, str]


def fetch(name: str, query: str, *, retries: int = 3) -> list[Row]:  # pragma: no cover
    """Run one SPARQL query and return rows as ``{variable: plain value}``."""
    url = ENDPOINT + "?" + urllib.parse.urlencode({"query": query})
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/sparql-results+json", "User-Agent": USER_AGENT},
    )
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                payload = json.load(response)
            break
        except OSError as error:  # network errors, timeouts, HTTP 5xx
            if attempt == retries:
                raise
            wait = 10 * attempt
            print(f"  {name}: {error}; retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)
    prefix = "http://www.wikidata.org/entity/"
    return [
        {var: cell["value"].removeprefix(prefix) for var, cell in binding.items()}
        for binding in payload["results"]["bindings"]
    ]


def load_raw(offline: bool) -> dict[str, list[Row]]:  # pragma: no cover
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw: dict[str, list[Row]] = {}
    for name, query in QUERIES.items():
        path = RAW_DIR / f"{name}.json"
        if offline:
            if not path.exists():
                sys.exit(f"--offline: {path} is missing; run once without --offline first")
            raw[name] = json.loads(path.read_text(encoding="utf-8"))
            print(f"  {name}: {len(raw[name])} rows (cached)")
            continue
        print(f"  {name}: querying Wikidata...")
        raw[name] = fetch(name, query)
        path.write_text(json.dumps(raw[name], ensure_ascii=False), encoding="utf-8")
        print(f"  {name}: {len(raw[name])} rows")
    return raw


# --------------------------------------------------------------------------- #
# 2. Transform (pure functions)
# --------------------------------------------------------------------------- #

# "Mengen (ilçe)", "Edremit (Balıkesir) ilçesi", "Yeşilköy (Kaş)" -> drop "(...)".
_PARENTHESIS = re.compile(r"\s*\([^)]*\)")
# Generic prefixes some languages put before the name.
_LABEL_PREFIX = re.compile(r"^(Distretto di|Distrito de|District de|Landkreis)\s+")
# "Mudurnu ilçesi", "Gerede İlçesi", "Polatlı District"
_DISTRICT_SUFFIX = re.compile(r"\s+(ilçesi|İlçesi|ilçe|İlçe|district|District)$")
# "Diyadin'in", "Tillo'nun", "Şirvan'ın" (left after removing "ilçesi")
_POSSESSIVE = re.compile(r"['\u2019]n?[ıiuü]n$")
# "Kızılay Mahallesi", "Alpağut Köyü"
_SETTLEMENT_SUFFIX = re.compile(r"\s+(mahallesi|Mahallesi|Mahalle|mahalle|köyü|Köyü|köy|Köy)$")


def _strip_common(label: str) -> str:
    label = _PARENTHESIS.sub("", label.strip())
    label = label.split(",")[0]  # "Güzelyurt, Aksaray" style disambiguation
    return _LABEL_PREFIX.sub("", label.strip()).strip()


def clean_district_label(label: str) -> str:
    """``"Mudurnu ilçesi"`` -> ``"Mudurnu"``, ``"Diyadin'in ilçesi"`` -> ``"Diyadin"``."""
    label = _DISTRICT_SUFFIX.sub("", _strip_common(label))
    return _POSSESSIVE.sub("", label).strip()


def clean_settlement_label(label: str) -> str:
    """``"Yeşilköy (Kaş)"`` -> ``"Yeşilköy"``, ``"Kızılay Mahallesi"`` -> ``"Kızılay"``."""
    return _SETTLEMENT_SUFFIX.sub("", _strip_common(label)).strip()


@dataclass
class Corrections:
    """Hand-reviewed fixes for known Wikidata problems (see the JSON file)."""

    district_names: dict[str, str] = field(default_factory=dict)  # QID -> correct name
    district_aliases: dict[str, list[str]] = field(default_factory=dict)  # QID -> other names
    extra_districts: dict[str, str] = field(default_factory=dict)  # QID -> province name
    drop_districts: set[str] = field(default_factory=set)  # QIDs to ignore
    province_aliases: dict[str, list[str]] = field(default_factory=dict)  # QID -> other names

    @classmethod
    def from_json(cls, data: Mapping[str, object]) -> Corrections:
        def section(key: str) -> dict[str, dict[str, object]]:
            value = data.get(key, {})
            if not isinstance(value, dict) or not all(isinstance(v, dict) for v in value.values()):
                raise ValueError(f"corrections: {key!r} must map QIDs to objects")
            for qid, entry in value.items():
                if not re.fullmatch(r"Q\d+", qid) or not entry.get("reason"):
                    raise ValueError(f"corrections: {key}.{qid} needs a QID key and a 'reason'")
            return value

        corrections = cls(drop_districts=set(section("drop_districts")))
        for qid, entry in {**section("district_names"), **section("extra_districts")}.items():
            if "name" in entry:
                corrections.district_names[qid] = str(entry["name"])
            aliases = entry.get("aliases", [])
            assert isinstance(aliases, list)
            corrections.district_aliases[qid] = [str(a) for a in aliases]
        for qid, entry in section("extra_districts").items():
            corrections.extra_districts[qid] = str(entry["il"])
        for qid, entry in section("province_aliases").items():
            aliases = entry.get("aliases", [])
            assert isinstance(aliases, list)
            corrections.province_aliases[qid] = [str(a) for a in aliases]
        return corrections


@dataclass
class District:
    name: str
    qids: set[str] = field(default_factory=set)
    aliases: set[str] = field(default_factory=set)
    settlements: set[str] = field(default_factory=set)


@dataclass
class Province:
    name: str
    qid: str
    plate: str
    aliases: list[str] = field(default_factory=list)
    districts: dict[str, District] = field(default_factory=dict)  # ascii key -> District


@dataclass
class BuildReport:
    """Numbers printed after a build so data changes are visible in review."""

    districts_dropped_no_province: list[str] = field(default_factory=list)
    districts_merged: list[str] = field(default_factory=list)
    districts_stale_merkez: list[str] = field(default_factory=list)
    settlements_unresolved: int = 0
    settlements_inactive: int = 0


def build_provinces(rows: Iterable[Row], corrections: Corrections) -> dict[str, Province]:
    """QID -> Province. Rows may repeat an item (one row per plate code)."""
    provinces: dict[str, Province] = {}
    for row in rows:
        qid = row["item"]
        if qid not in provinces:
            provinces[qid] = Province(
                name=row["label"],
                qid=qid,
                plate=row.get("plate", ""),
                aliases=sorted(corrections.province_aliases.get(qid, [])),
            )
    return provinces


def _group_rows(rows: Iterable[Row]) -> dict[str, list[Row]]:
    grouped: dict[str, list[Row]] = defaultdict(list)
    for row in rows:
        grouped[row["item"]].append(row)
    return grouped


def _is_active(rows: list[Row]) -> bool:
    """Active = not dissolved and at least one class statement without an end date."""
    if any("dissolved" in row for row in rows):
        return False
    return any("ended" not in row for row in rows)


def _label(rows: list[Row]) -> str:
    """Turkish label if there is one, else the best "otherLabel" by language."""
    for row in rows:
        if row.get("label"):
            return row["label"]
    others = {row["otherLang"]: row["otherLabel"] for row in rows if row.get("otherLabel")}
    for lang in LABEL_LANGUAGES:
        if lang in others:
            return others[lang]
    return ""


#: Provinces with a metropolitan municipality (Law 6360 of 2012, and Ordu by
#: Law 6447 of 2013). They have no "Merkez" district: the old central
#: district was split up, so a district item named like the province is stale.
METROPOLITAN = frozenset(
    ascii_key(name)
    for name in (
        "Adana", "Ankara", "Antalya", "Aydın", "Balıkesir", "Bursa", "Denizli",
        "Diyarbakır", "Erzurum", "Eskişehir", "Gaziantep", "Hatay", "İstanbul",
        "İzmir", "Kahramanmaraş", "Kayseri", "Kocaeli", "Konya", "Malatya",
        "Manisa", "Mardin", "Mersin", "Muğla", "Ordu", "Sakarya", "Samsun",
        "Şanlıurfa", "Tekirdağ", "Trabzon", "Van",
    )
)  # fmt: skip


def _province_of(
    rows: list[Row], provinces: Mapping[str, Province], by_key: Mapping[str, str]
) -> set[str]:
    """Province QIDs of a district: its parent, else its grandparent, else a
    parent whose label is a province name (e.g. the city item "İstanbul")."""
    for column in ("parent", "grandparent"):
        found = {row[column] for row in rows if row.get(column) in provinces}
        if found:
            return found
    return {
        by_key[ascii_key(row["parentLabel"])]
        for row in rows
        if ascii_key(row.get("parentLabel", "")) in by_key
    }


def add_districts(
    provinces: dict[str, Province],
    rows: Iterable[Row],
    corrections: Corrections,
    report: BuildReport,
) -> dict[str, District]:
    """Attach districts to provinces. Returns district QID -> District.

    * The central district of a non-metropolitan province has the province's
      name on Wikidata ("Bolu"); addresses write it as "Merkez", so we do too.
      In metropolitan provinces such an item is a stale, split-up district.
    * Several items with the same cleaned name in one province (a town item
      and a district item, for example) are merged into one district.
    """
    by_key = {ascii_key(p.name): qid for qid, p in provinces.items()}
    by_qid: dict[str, District] = {}
    grouped = _group_rows(rows)
    for qid, extra_province in corrections.extra_districts.items():
        grouped.setdefault(qid, [{"item": qid}])
        grouped[qid] = [
            {**row, "parent": by_key[ascii_key(extra_province)]} for row in grouped[qid]
        ]

    for qid, item_rows in sorted(grouped.items()):
        if qid in corrections.drop_districts or not _is_active(item_rows):
            continue
        parents = _province_of(item_rows, provinces, by_key)
        if len(parents) != 1:
            report.districts_dropped_no_province.append(f"{qid} {_label(item_rows)!r}")
            continue
        province = provinces[parents.pop()]
        name = corrections.district_names.get(qid) or clean_district_label(_label(item_rows))
        if not name:
            report.districts_dropped_no_province.append(f"{qid} (no label)")
            continue
        if ascii_key(name) in (ascii_key(province.name), "merkez"):
            if ascii_key(province.name) in METROPOLITAN:
                report.districts_stale_merkez.append(f"{province.name}: {qid} {name!r}")
                continue
            name = "Merkez"
        key = ascii_key(name)
        if key in province.districts:
            report.districts_merged.append(f"{province.name}/{name}: {qid}")
        district = province.districts.setdefault(key, District(name=name))
        district.qids.add(qid)
        district.aliases.update(corrections.district_aliases.get(qid, []))
        by_qid[qid] = district
    return by_qid


def _district_by_town(row: Row, provinces: Mapping[str, Province]) -> District | None:
    """Parent is a town item placed directly in a province ("Ergani" in
    Diyarbakır): use the province's district with the same name."""
    province = provinces.get(row.get("grandparent", ""))
    label = row.get("parentLabel", "")
    if province is None or not label:
        return None
    key = ascii_key(clean_district_label(label))
    if key == ascii_key(province.name):
        key = "merkez"
    return province.districts.get(key)


def _unique_district(row: Row, unique: Mapping[str, District]) -> District | None:
    """Parent is an unlinked item whose name only one district has ("Çankaya")."""
    label = row.get("parentLabel", "")
    return unique.get(ascii_key(clean_district_label(label))) if label else None


def add_settlements(
    provinces: Mapping[str, Province],
    districts: Mapping[str, District],
    rows: Iterable[Row],
    report: BuildReport,
) -> None:
    """Attach mahalle/köy items to their district.

    Tried in order: the parent is a district; the parent is a belde (small
    municipality) whose parent is a district; the parent is a town directly in
    a province with the same name as one of its districts; the parent's name
    belongs to exactly one district in the whole country ("Çankaya").
    """
    names: dict[str, list[District]] = defaultdict(list)
    for province in provinces.values():
        for key, district in province.districts.items():
            names[key].append(district)
    unique = {key: found[0] for key, found in names.items() if len(found) == 1}

    for _qid, item_rows in sorted(_group_rows(rows).items()):
        if not _is_active(item_rows):
            report.settlements_inactive += 1
            continue
        name = clean_settlement_label(_label(item_rows))
        targets = [districts[r["parent"]] for r in item_rows if r.get("parent") in districts]
        if not targets:
            targets = [
                districts[r["grandparent"]] for r in item_rows if r.get("grandparent") in districts
            ]
        if not targets:
            targets = [d for r in item_rows if (d := _district_by_town(r, provinces)) is not None]
        if not targets:
            targets = [d for r in item_rows if (d := _unique_district(r, unique)) is not None]
        if not targets or not name:
            report.settlements_unresolved += 1
            continue
        for district in targets:
            district.settlements.add(name)


def to_payload(provinces: Mapping[str, Province], retrieved: str) -> dict[str, object]:
    """The JSON structure written to the package (sorted for stable output)."""
    iller = []
    for province in sorted(provinces.values(), key=lambda p: ascii_key(p.name)):
        ilceler = [
            {
                "ad": district.name,
                "wikidata": sorted(district.qids),
                "diger_adlar": sorted(district.aliases),
                "mahalleler": sorted(district.settlements, key=lambda s: (ascii_key(s), s)),
            }
            for district in sorted(province.districts.values(), key=lambda d: ascii_key(d.name))
        ]
        iller.append(
            {
                "ad": province.name,
                "plaka": province.plate,
                "wikidata": province.qid,
                "diger_adlar": province.aliases,
                "ilceler": ilceler,
            }
        )
    return {
        "format": FORMAT_VERSION,
        "source": "Wikidata (https://www.wikidata.org), CC0 1.0",
        "retrieved": retrieved,
        "iller": iller,
    }


def _district_of(provinces: Mapping[str, Province], entry: Mapping[str, str]) -> District:
    for province in provinces.values():
        if province.name == entry["il"]:
            for district in province.districts.values():
                if district.name == entry["ilce"]:
                    return district
    raise ValueError(f"additions: no district {entry['il']}/{entry['ilce']}")


def apply_additions(provinces: Mapping[str, Province], additions: Mapping[str, Any]) -> None:
    """Apply gazetteer_additions.json. An entry that is no longer needed is an error."""
    for entry in [*additions.get("renames", []), *additions.get("mahalleler", [])]:
        if not entry.get("source"):
            raise ValueError(f"additions: {entry} needs a 'source'")
    for entry in additions.get("renames", []):
        district = _district_of(provinces, entry)
        if entry["from"] not in district.settlements or entry["to"] in district.settlements:
            raise ValueError(f"additions: stale rename {entry['from']} -> {entry['to']}")
        district.settlements.remove(entry["from"])
        district.settlements.add(entry["to"])
    for entry in additions.get("mahalleler", []):
        district = _district_of(provinces, entry)
        if entry["ad"] in district.settlements:
            raise ValueError(f"additions: {entry['ad']} is already in the data, remove it")
        district.settlements.add(entry["ad"])


def build(
    raw: Mapping[str, list[Row]],
    corrections: Corrections,
    retrieved: str,
    additions: Mapping[str, Any] | None = None,
) -> tuple[dict[str, object], BuildReport]:
    report = BuildReport()
    provinces = build_provinces(raw["provinces"], corrections)
    districts = add_districts(provinces, raw["districts"], corrections, report)
    add_settlements(provinces, districts, raw["mahalleler"] + raw["koyler"], report)
    apply_additions(provinces, additions or {})
    return to_payload(provinces, retrieved), report


# --------------------------------------------------------------------------- #
# 3. Write
# --------------------------------------------------------------------------- #


def write(payload: Mapping[str, object], path: Path) -> int:  # pragma: no cover
    """Write gzip-compressed JSON. ``mtime=0`` keeps the bytes reproducible."""
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with path.open("wb") as file, gzip.GzipFile(fileobj=file, mode="wb", mtime=0) as gz:
        gz.write(data)
    return path.stat().st_size


def print_summary(payload: Mapping[str, object], report: BuildReport) -> None:  # pragma: no cover
    iller = payload["iller"]
    assert isinstance(iller, list)
    ilce_count = sum(len(il["ilceler"]) for il in iller)
    mahalle_count = sum(len(ilce["mahalleler"]) for il in iller for ilce in il["ilceler"])
    merkez = sum(1 for il in iller for ilce in il["ilceler"] if ilce["ad"] == "Merkez")
    print(
        f"  il: {len(iller)}  ilçe: {ilce_count} (Merkez: {merkez})  mahalle/köy: {mahalle_count}"
    )
    print(f"  districts merged (duplicates): {len(report.districts_merged)}")
    print(
        f"  stale Merkez districts in metropolitan provinces: {len(report.districts_stale_merkez)}"
    )
    print(f"  districts dropped (no single province): {len(report.districts_dropped_no_province)}")
    for line in report.districts_dropped_no_province:
        print(f"    - {line}")
    print(f"  settlements inactive: {report.settlements_inactive}")
    print(f"  settlements unresolved (no district): {report.settlements_unresolved}")


def main(argv: Iterable[str] | None = None) -> None:  # pragma: no cover
    if hasattr(sys.stdout, "reconfigure"):  # Windows consoles default to a legacy code page
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--offline", action="store_true", help="use cached raw data")
    args = parser.parse_args(list(argv) if argv is not None else None)

    print("fetch")
    raw = load_raw(args.offline)
    retrieved = date.fromtimestamp((RAW_DIR / "mahalleler.json").stat().st_mtime).isoformat()

    print("transform")
    corrections = Corrections.from_json(json.loads(CORRECTIONS.read_text(encoding="utf-8")))
    additions = json.loads(ADDITIONS.read_text(encoding="utf-8"))
    payload, report = build(raw, corrections, retrieved, additions)
    print_summary(payload, report)

    print("write")
    size = write(payload, OUTPUT)
    print(f"  {OUTPUT.relative_to(ROOT)}: {size / 1024:.0f} KiB")


if __name__ == "__main__":
    main()
