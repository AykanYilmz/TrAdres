# Contributing to TrAdres

Thank you for helping. Most useful contributions here are small: a missing
abbreviation, or one address that TrAdres reads wrong. You do not need to know
the whole code for these.

Türkçe yazabilirsiniz: issues and pull requests are welcome in Turkish too.

## Privacy first

**Never share a real person's address** in an issue, a pull request, a test or
the evaluation set. Turkish law (KVKK) protects this data, and git history is
hard to clean.

If a real address fails, keep the pattern and change the rest: use another
street, building and numbers. A real mahalle, ilçe and il are fine because they
are public place names.

## Set up

You need [uv](https://docs.astral.sh/uv/getting-started/installation/). It also
installs the right Python version.

```bash
git clone https://github.com/AykanYilmz/TrAdres.git
cd TrAdres
uv sync
uv run pre-commit install    # checks your code on every commit
```

## Run the tests

```bash
uv run pytest                # all tests, coverage must stay at 90% or more
uv run ruff check .          # lint
uv run ruff format .         # format
uv run mypy                  # types, in strict mode
uv run python -m eval --min-f1 0.98 --min-exact 0.95   # accuracy
```

CI runs the same commands on Python 3.10 to 3.13.

To try an address by hand:

```bash
uv run tradres parse "ataturk mh 23nisan cd no 5 d 3 bolu merkez"
uv run python -m demo        # small web page on http://127.0.0.1:8000
```

## Add a new abbreviation

Abbreviations are data, not code. Open
[`src/tradres/data/abbreviations.json`](src/tradres/data/abbreviations.json) and
add the new form to the `aliases` list of the right kind:

```json
"cadde": {
  "short": "Cad.",
  "long": "Caddesi",
  "aliases": ["cad", "cd", "cadde", "caddesi", "cadd", "your-new-form"]
}
```

- Write one word, in correct Turkish. Matching ignores case, Turkish letters,
  dots and colons, so `Sokağı`, `SOKAGI` and `sokagi.` are the same alias.
- Do not add a form with two meanings. For example `da` could be many things.
- Run `uv run pytest tests/test_abbreviations.py`.
- Add an address that uses the new form to the evaluation set (see below).

The other small lists work in the same way:

| File in `src/tradres/data/` | What it holds |
|---|---|
| `name_words.json` | Short words inside names: `gmk`, `prof` |
| `description_words.json` | Words that end a direction: `yanı`, `karşısı` |
| `ascii_names.json` | Names that must keep plain letters: `Can` is not `Çan` |
| `country_names.json` | The country at the end of an address |

## Add a wrongly parsed address to the evaluation set

The evaluation set shows if a change really helps. Every accuracy change needs
numbers from it, before and after.

1. Remove all personal data (see [Privacy first](#privacy-first)).
2. Add the case to the end of
   [`eval/addresses/katkilar.yaml`](eval/addresses/katkilar.yaml):

   ```yaml
   - id: "p100"               # unique, quoted
     girdi: "Lale Mah. Gül Sk. No:5/3 Konak/İzmir"
     beklenen:                # what a perfect parser returns
       il: İzmir
       ilce: Konak
       mahalle: Lale
       sokak: Gül
       bina_no: "5"
       daire: "3"
     etiketler: [temiz]
   ```

   Names have no type word (`Gül`, not `Gül Sk.`). Numbers are in quotes. The
   allowed tags are in [`eval/dataset.py`](eval/dataset.py), and
   [`eval/README.md`](eval/README.md) explains the format.
3. Check the labels and see the failure:

   ```bash
   uv run python -m eval --check
   uv run python -m eval --failures 20
   ```

4. Fix the parser if you can. If not, you can still send the failing case: open
   a "Wrongly parsed address" issue and we will take it from there.

**Do not read or change `eval/holdout/` and `eval/holdout2/`.** These locked
test sets measure addresses the rules were not tuned on. If we tune on them,
their score means nothing. `python -m eval --holdout` shows totals only.

## Fix or add a place

Place data comes from Wikidata. The best fix is on Wikidata, so everyone gets
it. [`DATA_SOURCES.md`](DATA_SOURCES.md) explains how to fix a wrong or missing
place in this project.

## Pull requests

- Keep a pull request small: one fix or one feature.
- Use [Conventional Commits](https://www.conventionalcommits.org/):
  `feat:`, `fix:`, `test:`, `docs:`, `chore:`.
- Tests must pass in every commit.
- If you change accuracy, write the before and after numbers.
- Think twice before you add a dependency. The core library should stay small.

By contributing, you agree that your work uses the [MIT License](LICENSE).
This project follows our [Code of Conduct](CODE_OF_CONDUCT.md).
