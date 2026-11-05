# Data sources

TrAdres ships two data files inside the package. No internet connection is
needed at install time or at run time.

| File | What it is | Source | License |
|---|---|---|---|
| `src/tradres/data/gazetteer.json.gz` | Official place names: il → ilçe → mahalle/köy | [Wikidata](https://www.wikidata.org) | [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) |
| `src/tradres/data/abbreviations.json` | Address keywords and abbreviations (Mah., Cad., No …) | Written by the TrAdres contributors | MIT (same as the code) |

## Gazetteer (`gazetteer.json.gz`)

### Source and license

All place names come from Wikidata, which publishes its structured data
under **CC0 1.0** (public domain). This means the data can be used,
changed and redistributed without conditions, including inside an
MIT-licensed package. We still credit Wikidata here because it is the
right thing to do.

- Retrieved: **2026-11-04** (also stored in the file as `retrieved`)
- Endpoint: <https://query.wikidata.org/sparql>
- Wikidata classes used:
  [province of Turkey (Q48336)](https://www.wikidata.org/wiki/Q48336),
  [district of Turkey (Q1147395)](https://www.wikidata.org/wiki/Q1147395),
  [mahalle (Q17051044)](https://www.wikidata.org/wiki/Q17051044),
  [village of Turkey (Q1529096)](https://www.wikidata.org/wiki/Q1529096)

### Contents and coverage

| Level | In TrAdres | Official count | Coverage |
|---|---:|---:|---:|
| İl | 81 | 81 | 100% |
| İlçe | 973 | 973 | 100% |
| Mahalle + köy | 46,112 | ~50,400 | ~88.6%* |

\* Share of official mahalle/köy names that we find under the **same
district**. We measured this once, locally, against a public list built
from TÜİK and PTT data; that list is **not** included in TrAdres because
its license is unclear.

Among the names we do find, 99.7% have the same spelling as the official
list. Most of the rest are small format differences (`100. Yıl` and
`100.Yıl`); a few are real spelling errors on Wikidata (`Firat` for `Fırat`).

Mahalle and köy are stored together. Wikidata does not mark reliably which
one a place is (many villages became mahalles in 2012–2014), so TrAdres
does not try to tell them apart.

### How the file is built

`scripts/build_gazetteer.py` (standard library only):

1. **Fetch** — runs SPARQL queries and caches the raw answers in
   `data/raw/` (not committed to git).
2. **Transform** — cleans labels (`"Mudurnu ilçesi"` → `"Mudurnu"`,
   `"Yeşilköy (Kaş)"` → `"Yeşilköy"`), merges duplicate items, names the
   central district of the 51 non-metropolitan provinces `Merkez` (as
   addresses do), drops stale `Merkez` items of the 30 metropolitan
   provinces, and links each mahalle/köy to its district (directly, through
   a belde, or through a town item).
3. **Apply corrections** — `scripts/gazetteer_corrections.json` holds a
   small, reviewed list of fixes for known Wikidata errors (wrong or old
   names, missing links, items that are not districts). Every entry names
   the Wikidata item (QID) and a reason. It also adds common other names
   such as `Urfa`, `Afyon`, `Kazan`, `Eyüp`.
4. **Write** — compact gzip JSON. The output is deterministic: the same
   input always gives a byte-identical file, so git diffs show real data
   changes only.

To rebuild:

```bash
uv run python scripts/build_gazetteer.py            # download fresh data and build
uv run python scripts/build_gazetteer.py --offline  # rebuild from data/raw/
```

The script prints a report (merged duplicates, dropped items, mahalle/köy
that could not be linked to a district). Please paste it into your pull
request when you update the data.

### Known gaps

- About 11% of mahalle/köy names are missing because they are not on
  Wikidata or are not linked to a district there. Rural districts with
  many villages (for example Viranşehir and Akçakale in Şanlıurfa) have
  the largest gaps.
- Some names may be out of date (mahalle merges and renames happen every
  year).
- Neighbourhood *areas* that are not official mahalles (for example
  `Batıkent` in Ankara or `Moda` in İstanbul) are not in the list.

### How to fix a wrong or missing place

1. **Best:** fix it on Wikidata (anyone can edit). The next rebuild picks
   it up, and every other Wikidata user benefits too.
2. **Missing or misspelled mahalle:** add an entry to
   `scripts/gazetteer_additions.json` with a public source page. One name at a
   time; do not copy from bulk lists. The build fails when an entry is no
   longer needed.
3. **Quick:** add an entry to `scripts/gazetteer_corrections.json` with
   the item's QID and a short reason, rebuild, and open a pull request.
   When Wikidata is fixed, the entry can be removed.

## Evaluation set (`eval/addresses/`)

The evaluation set is a development tool and is not part of the package.
It uses about 300 real place names, chosen by random sampling from the
public mahalle and köy list mentioned above, because a sample taken from our
own gazetteer could not show what is missing from it. Single place names are
public facts. All street names, building names and numbers are invented, and
no address belongs to a real person.

## Package size

Measured on 2026-11-04 with `uv build`:

| Artifact | Size |
|---|---:|
| Wheel (`.whl`) | 228 KiB |
| `gazetteer.json.gz` | 194 KiB (626 KiB unpacked) |
| Loaded in memory | ~17 MB |
| First load time (index build) | ~0.3 s, once per process |
