"""Command line for the evaluation: ``python -m eval``."""

from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import cast

from eval.dataset import (
    ADDRESSES_DIR,
    HOLDOUT_DIR,
    MISSING_TAG,
    SPELLING_TAG,
    DatasetError,
    load_cases,
    tag_counts,
)
from eval.metrics import Predict, Report, evaluate
from tradres.models import FIELDS

DEFAULT_PARSER = "tradres:parse"
EXIT_OK, EXIT_BELOW_THRESHOLD, EXIT_ERROR = 0, 1, 2


def load_parser(spec: str) -> Predict:
    """Turn ``"package.module:function"`` into a text -> fields function."""
    module_name, _, attribute = spec.partition(":")
    function = getattr(importlib.import_module(module_name), attribute)

    def predict(text: str) -> Mapping[str, object]:
        return as_fields(function(text))

    return predict


def as_fields(result: object) -> Mapping[str, object]:
    """Accept a mapping or an object with one attribute per field."""
    if isinstance(result, Mapping):
        return cast("Mapping[str, object]", result)
    return {name: getattr(result, name, None) for name in FIELDS}


def format_text(report: Report, *, groups: bool = True) -> str:
    lines = [f"{'field':<12}{'precision':>10}{'recall':>9}{'f1':>8}{'support':>9}"]
    rows = [*report.fields.items(), ("TOTAL", report.overall)]
    for name, score in rows:
        lines.append(
            f"{name:<12}{score.precision:>10.3f}{score.recall:>9.3f}"
            f"{score.f1:>8.3f}{score.support:>9}"
        )
    lines += ["", f"exact addresses: {report.exact}/{report.total} = {report.exact_rate:.1%}"]
    if report.crashes:
        lines.append(f"CRASHES: {report.crashes}")
    if groups:
        lines += ["", f"{'tag':<16}{'exact':>7}{'total':>7}{'rate':>8}"]
        for tag, group in sorted(report.groups.items()):
            lines.append(f"{tag:<16}{group.exact:>7}{group.total:>7}{group.rate:>8.1%}")
    return "\n".join(lines)


def format_markdown(report: Report) -> str:
    """The accuracy table for the README."""
    lines = ["| Field | Precision | Recall | F1 | Addresses |", "|---|---:|---:|---:|---:|"]
    for name, score in [*report.fields.items(), ("**All fields**", report.overall)]:
        lines.append(
            f"| {name} | {score.precision:.3f} | {score.recall:.3f} "
            f"| {score.f1:.3f} | {score.support} |"
        )
    lines += ["", f"Exact addresses: **{report.exact_rate:.1%}** of {report.total}."]
    return "\n".join(lines)


def format_failures(report: Report, limit: int) -> str:
    lines = []
    for failure in report.failures[:limit]:
        lines.append(f"[{failure.case.id}] {failure.case.girdi}")
        for name, (want, got) in failure.wrong.items():
            lines.append(f"    {name}: expected {want!r}, got {got!r}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m eval", description="Score a parser.")
    parser.add_argument("--parser", default=DEFAULT_PARSER, help="module:function to score")
    parser.add_argument("--check", action="store_true", help="only validate the labels")
    parser.add_argument(
        "--holdout", action="store_true", help="score the locked test set (totals only)"
    )
    parser.add_argument("--tag", help="score only the addresses with this tag")
    parser.add_argument("--failures", type=int, default=0, metavar="N", help="show N failures")
    parser.add_argument("--markdown", action="store_true", help="print the README table")
    parser.add_argument("--min-f1", type=float, default=0.0, help="fail below this overall F1")
    parser.add_argument("--min-exact", type=float, default=0.0, help="fail below this exact rate")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    loader: Callable[[str], Predict] = load_parser,
) -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to a legacy code page
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)

    if args.holdout and (args.failures or args.tag):
        # Reading these failures would turn the test set into training data.
        print("--holdout shows totals only: no --failures or --tag", file=sys.stderr)
        return EXIT_ERROR

    try:
        cases = load_cases(HOLDOUT_DIR if args.holdout else ADDRESSES_DIR)
    except DatasetError as error:
        print(f"invalid labels: {error}", file=sys.stderr)
        return EXIT_ERROR

    if args.check:
        counts = tag_counts(cases)
        print(f"{len(cases)} addresses are valid.")
        print(f"not in the gazetteer: {counts.get(MISSING_TAG, 0)}")
        print(f"spelled differently in the gazetteer: {counts.get(SPELLING_TAG, 0)}")
        print("\n".join(f"  {tag}: {count}" for tag, count in counts.items()))
        return EXIT_OK

    if args.tag:
        cases = [case for case in cases if args.tag in case.etiketler]
    try:
        predict = loader(args.parser)
    except (ImportError, AttributeError) as error:
        print(f"cannot load parser {args.parser!r}: {error}", file=sys.stderr)
        print("try: python -m eval --parser eval.baseline:parse", file=sys.stderr)
        return EXIT_ERROR

    report = evaluate(cases, predict)
    text = (
        format_markdown(report) if args.markdown else format_text(report, groups=not args.holdout)
    )
    print(text)
    if args.holdout:
        print(f"locked test set: {len(cases)} addresses")
    if args.failures:
        print("\n" + format_failures(report, args.failures))

    if report.overall.f1 < args.min_f1 or report.exact_rate < args.min_exact:
        print(
            f"below threshold: f1={report.overall.f1:.3f} (min {args.min_f1}), "
            f"exact={report.exact_rate:.3f} (min {args.min_exact})",
            file=sys.stderr,
        )
        return EXIT_BELOW_THRESHOLD
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
