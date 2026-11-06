# Ideas for good first issues

Drafts to open as issues with the `good first issue` label. Each one is small
and needs little knowledge of the code. Before opening one, check that it is
still true.

1. **Add building words.** `Plaza`, `Han`, `Pasaj` and `Rezidans` are not read
   as building names yet. Add them, with cases in `eval/addresses/katkilar.yaml`.
   See `_BUILDING_NAME_ENDS` in `src/tradres/extractors/streets.py`.
2. **Add more titles to `name_words.json`.** For example `Av.`, `Op.`, `Müh.`,
   `Yzb.`, `Alb.`. Add only forms with one clear meaning.
3. **Add more direction words to `description_words.json`.** For example other
   forms of `yakını` and `köşesi`.
4. **Add more names to `ascii_names.json`.** Find names that change their meaning
   when `respell` adds Turkish letters, as `Can` does with `Çan`.
5. **Read `Küme Evleri`.** Village addresses use `Merkez Küme Evleri`, which now
   stays in `kalan`. Propose which field it should use.
6. **Add `Sinir` to the word list.** `sinir cd` should give `Sınır`. Find out why
   it does not, and how a small list could fix it.
7. **Add 20 new test addresses.** Use tags with few cases. Run
   `uv run python -m eval --check` to see the counts.
8. **Translate error messages of the CLI into Turkish.** First open an issue to
   discuss how the language should be chosen.
9. **Fix a missing mahalle on Wikidata.** Central districts have the biggest gaps
   (see "Known gaps" in `DATA_SOURCES.md`). This helps every Wikidata user too.
