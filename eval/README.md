# Evaluation set

Hand-labelled addresses that measure how well TrAdres parses Turkish
addresses. We wrote this set before the parser, so every change can be
measured with numbers.

```bash
uv run python -m eval                            # score tradres.parse
uv run python -m eval --parser eval.baseline:parse   # score the simple baseline
uv run python -m eval --failures 20              # also show wrong addresses
uv run python -m eval --tag ascii                # only one group
uv run python -m eval --markdown                 # table for the README
uv run python -m eval --check                    # only validate the labels
```

## Messy data

`python -m eval.robustness` damages the same addresses in one known way (no
Turkish letters, no punctuation, typos, changed order) and scores them again.
The labels stay the same, so each row shows the price of that mess. Use
`--failures no_punctuation` to see the failures of one row.

## Privacy (KVKK)

**Never add a real person's address.** Places are real and public, but
building, floor and flat numbers, street and building names are made up.
If you found a bug with a real address, change everything except the
pattern that fails.

## Format

Each file in `addresses/` is a YAML list. Add new cases to `katkilar.yaml`.

```yaml
- id: "k0001"                # unique, quoted
  girdi: "ataturk mh 23nisan cd no 5 d 3 bolu merkez"
  beklenen:                  # the fields a perfect parser returns
    il: Bolu
    ilce: Merkez
    mahalle: Atatürk
    cadde: 23 Nisan
    bina_no: "5"
    daire: "3"
  etiketler: [ascii, kisaltma, birlesik]
  not: "Optional. Why this case is hard."
```

### Rules for `beklenen`

- **Fields:** `il`, `ilce`, `mahalle`, `bulvar`, `cadde`, `sokak`, `site`,
  `bina_adi`, `blok`, `bina_no`, `kat`, `daire`, `posta_kodu`. Leave out
  fields that the address does not have. Köy names go in `mahalle`.
- **`il` is filled in when it follows from the text.** If the address says
  only `Kadıköy`, write `il: İstanbul`. If it says only `Merkez`, leave it out.
- **`ilce` too:** if `ilce` is not written but the mahalle exists in only one
  district of that il in the gazetteer, fill it in. Otherwise leave it out.
- **Official spelling** for `il`, `ilce` and `mahalle`. The loader checks
  `il` and `ilce` against the gazetteer and stops on a wrong spelling. A mahalle
  that is missing from the gazetteer gets the tag `gazetteer_disi`
  automatically, and one spelled differently there (`Firat` for `Fırat`) gets
  `gazetteer_yazim_farki`. Keep the official spelling in the label.
- **No type words in names:** `cadde: 23 Nisan`, not `23 Nisan Cad.`;
  `bina_adi: Gül`, not `Gül Apartmanı`; `site: Güneş`, not `Güneş Sitesi`.
- **Numbers are quoted strings:** `"5"`, `"5A"`, `"1923"`. In YAML an
  unquoted `5` is a number, and the loader rejects it.
- **`kalan`** (optional) is the text that should stay unparsed, such as
  directions. It is documentation for now and is not scored.

### Tags

Tags split the report into groups, so we can see for example how well
ASCII-typed addresses do. The list is in `dataset.py`. The most useful are
`ascii`, `kisaltma`, `yazim_hatasi`, `sira`, `il_eksik` and `tuzak` (the text
looks like one thing but is another, such as `D 100`, a road and not flat 100).

## How scoring works

For each field, a value counts as correct if it equals the expected value,
ignoring upper/lower case and extra spaces. **Turkish letters must be right**:
`Cankaya` is wrong when `Çankaya` is expected. A wrong value counts against
both precision and recall.

*Exact addresses* is the share of addresses with every field correct.

`eval/baseline.py` is a very simple parser. The real parser has to beat it.

## Where the place names come from

The set must also measure what happens when a mahalle is missing from our
gazetteer, so its place names are **not** taken from the gazetteer. They are a
random sample, weighted by the square root of population, from a public list
of mahalle and köy names (see [DATA_SOURCES.md](../DATA_SOURCES.md)). Street
names, building names and all numbers are invented.

## The locked test set

`eval/addresses/` is the development set: we read its failures and improve the
rules with them. That makes its score optimistic, because the rules know it.

`eval/holdout/test.yaml` is the test set. Its 100 addresses use places that are
not in the development set, and they were written before Phase 5 started. Run
it with:

```bash
python -m eval --holdout
```

This prints totals only and refuses `--failures` and `--tag`. Do not tune the
parser on these addresses. Measure rarely, because every look leaks a little
information. When a release is out, new addresses replace it.
