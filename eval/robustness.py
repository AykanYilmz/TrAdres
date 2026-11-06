"""How much does each kind of mess cost? ``python -m eval.robustness``.

Real files are messier than hand-written test addresses. This tool takes the
labelled addresses, damages the text in one known way and scores the parser
again. The labels stay the same, so a lower score is the price of that damage.

The damage is random but repeatable: the same address gets the same typo every
time, so two runs can be compared.

Some of the loss cannot be recovered. ``tarif`` keeps the text as written, so
without Turkish letters it can never equal its label, and a removed dot in
"75. Yıl" is gone. Read the numbers as a lower limit.
"""

from __future__ import annotations

import argparse
import random
import re
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import replace

from eval.dataset import ADDRESSES_DIR, HOLDOUT_2_DIR, HOLDOUT_DIR, Case, load_cases
from eval.metrics import Report, evaluate
from tradres import parse
from tradres.models import FIELDS
from tradres.normalization import tr_lower, tr_upper

_ASCII_LETTERS = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
_MIN_TYPO_LENGTH = 6
_PLACE_FIELDS = ("il", "ilce", "mahalle")
_LOWER_LETTERS = "abcdefghijklmnoprstuvyz"

Noise = Callable[[Case], str]


def no_turkish_letters(case: Case) -> str:
    """Typed on a keyboard without Turkish letters."""
    return case.girdi.translate(_ASCII_LETTERS)


def all_caps(case: Case) -> str:
    """Old systems often store text in capitals."""
    return tr_upper(case.girdi)


def all_lower(case: Case) -> str:
    return tr_lower(case.girdi)


def no_punctuation(case: Case) -> str:
    """No dots, colons or commas: "Mah Gül Sk No 5"."""
    return " ".join(re.sub(r"[.:,;]", " ", case.girdi).split())


def no_spaces_after_punctuation(case: Case) -> str:
    """ "Gül Sk.No:5,Bolu"."""
    return re.sub(r"([.:,;])\s+", r"\1", case.girdi)


def extra_spaces(case: Case) -> str:
    return case.girdi.replace(" ", "   ")


def _typo(word: str, rng: random.Random) -> str:
    """One edit inside a word. The first letter stays, as in most real typos."""
    position = rng.randrange(1, len(word) - 1)
    kind = rng.choice(("drop", "swap", "replace"))
    if kind == "drop":
        return word[:position] + word[position + 1 :]
    if kind == "swap":
        return word[:position] + word[position + 1] + word[position] + word[position + 2 :]
    return word[:position] + rng.choice(_LOWER_LETTERS) + word[position + 1 :]


def typo_in_place(case: Case) -> str:
    """One typing mistake in the il, ilçe or mahalle, if the name is long enough."""
    rng = random.Random(case.id)  # the same address always gets the same typo
    names = [case.beklenen[name] for name in _PLACE_FIELDS if name in case.beklenen]
    words = [word for name in names for word in name.split() if len(word) >= _MIN_TYPO_LENGTH]
    found = [word for word in words if word in case.girdi]
    if not found:
        return case.girdi
    word = rng.choice(found)
    return case.girdi.replace(word, _typo(word, rng), 1)


def place_first(case: Case) -> str:
    """Move the last piece to the front: "Gül Sk. 5, Bolu" -> "Bolu, Gül Sk. 5"."""
    pieces = [piece.strip() for piece in case.girdi.split(",")]
    if len(pieces) > 1:
        return ", ".join([pieces[-1], *pieces[:-1]])
    head, _, tail = case.girdi.rpartition(" ")
    return f"{tail} {head}" if head and "/" in tail else case.girdi


def everything_at_once(case: Case) -> str:
    """The worst common export: lower case, plain letters, no punctuation."""
    damaged = replace(case, girdi=no_turkish_letters(case))
    damaged = replace(damaged, girdi=no_punctuation(damaged))
    return all_lower(damaged)


NOISES: Mapping[str, Noise] = {
    "no_turkish_letters": no_turkish_letters,
    "all_caps": all_caps,
    "all_lower": all_lower,
    "no_punctuation": no_punctuation,
    "no_spaces_after_punctuation": no_spaces_after_punctuation,
    "extra_spaces": extra_spaces,
    "typo_in_place": typo_in_place,
    "place_first": place_first,
    "everything_at_once": everything_at_once,
}


def predict(text: str) -> Mapping[str, object]:
    address = parse(text)
    return {name: getattr(address, name) for name in FIELDS}


def score_noise(cases: Iterable[Case], noise: Noise) -> Report:
    """Score the parser on the damaged text of ``cases``."""
    return evaluate([replace(case, girdi=noise(case)) for case in cases], predict)


def format_table(clean: Report, reports: Mapping[str, Report]) -> str:
    lines = [f"{'noise':<30}{'exact':>7}{'total':>7}{'rate':>8}{'f1':>8}{'lost':>8}"]
    for name, report in {"(none)": clean, **reports}.items():
        lost = clean.exact_rate - report.exact_rate
        lines.append(
            f"{name:<30}{report.exact:>7}{report.total:>7}{report.exact_rate:>8.1%}"
            f"{report.overall.f1:>8.3f}{lost:>8.1%}"
        )
    return "\n".join(lines)


def format_failures(report: Report, limit: int) -> str:
    lines = []
    for failure in report.failures[:limit]:
        lines.append(f"[{failure.case.id}] {failure.case.girdi}")
        for name, (want, got) in failure.wrong.items():
            lines.append(f"    {name}: expected {want!r}, got {got!r}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m eval.robustness", description="Score the parser on damaged addresses."
    )
    parser.add_argument(
        "--holdout", type=int, choices=(1, 2), help="use a locked set (totals only)"
    )
    parser.add_argument("--failures", choices=sorted(NOISES), help="show failures of this noise")
    parser.add_argument("--limit", type=int, default=30, help="failures to show")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to a legacy code page
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    if args.holdout and args.failures:
        print("--holdout shows totals only: no --failures", file=sys.stderr)
        return 2
    directory = {None: ADDRESSES_DIR, 1: HOLDOUT_DIR, 2: HOLDOUT_2_DIR}[args.holdout]
    cases = load_cases(directory)
    clean = evaluate(cases, predict)
    reports = {name: score_noise(cases, noise) for name, noise in NOISES.items()}
    print(format_table(clean, reports))
    if args.failures:
        print("\n" + format_failures(reports[args.failures], args.limit))
    return 0


if __name__ == "__main__":
    sys.exit(main())
