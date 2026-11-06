# Changelog

All notable changes to this project are in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `parse`: split a Turkish address into il, ilçe, mahalle, bulvar, cadde, sokak,
  site, bina adı, blok, bina no, kat, daire, posta kodu and tarif. Text that
  cannot be read stays in `kalan`.
- `normalize`, with Turkish case rules and cleaning of spaces and punctuation.
- Checks against a place list of 81 il, 973 ilçe and about 46,000 mahalle and
  köy from Wikidata (CC0). The data comes with the package.
- Fuzzy matching of misspelled place names, with `MatchConfig` for the limits.
- A confidence score for the address and for each field.
- `Address.format()` for one standard spelling and `Address.to_dict()` for JSON.
- Command line: `tradres parse` and `tradres parse-csv`, with encoding and
  delimiter detection for CSV files from Turkish Excel.
- Type hints and a `py.typed` file.
