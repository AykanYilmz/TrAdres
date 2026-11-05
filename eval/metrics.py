"""Scoring: precision, recall and F1 per field, and the exact-address rate.

For each field of each address there are three possible counts:

* true positive (TP): the parser gave the expected value.
* false positive (FP): the parser gave a value, but it is wrong or unexpected.
* false negative (FN): a value was expected, but the parser did not give it.

A wrong value counts as both FP and FN, the usual rule for extraction tasks.

* precision = TP / (TP + FP): "when it answers, how often is it right?"
* recall    = TP / (TP + FN): "how many of the real values does it find?"
* F1 is the harmonic mean of the two; it is high only when both are high.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

from eval.dataset import FIELDS, Case
from tradres.normalization import tr_lower

#: A parser for scoring: address text in, field name -> value out.
Predict = Callable[[str], Mapping[str, object]]


def canonical(value: object) -> str:
    """Comparison form: ignores case and extra spaces, keeps Turkish letters.

    ``"Cankaya"`` and ``"Çankaya"`` stay different on purpose: returning the
    correct Turkish spelling is part of the job.

    >>> canonical(" KIZILAY  Sokak ") == canonical("kızılay sokak")
    True
    >>> canonical("Cankaya") == canonical("Çankaya")
    False
    """
    if value is None:
        return ""
    return " ".join(tr_lower(str(value)).split())


@dataclass
class FieldScore:
    """TP/FP/FN counts for one field (or for all fields together)."""

    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0

    @property
    def f1(self) -> float:
        total = self.precision + self.recall
        return 2 * self.precision * self.recall / total if total else 0.0

    @property
    def support(self) -> int:
        """How many addresses have this field in the labels."""
        return self.tp + self.fn

    def add(self, other: FieldScore) -> None:
        self.tp += other.tp
        self.fp += other.fp
        self.fn += other.fn


def score_field(expected: object, predicted: object) -> FieldScore:
    """Counts for one field of one address."""
    want, got = canonical(expected), canonical(predicted)
    if want and got == want:
        return FieldScore(tp=1)
    return FieldScore(fp=1 if got else 0, fn=1 if want else 0)


@dataclass(frozen=True)
class Failure:
    """One address that was not parsed exactly right."""

    case: Case
    wrong: Mapping[str, tuple[str, str]]  # field -> (expected, predicted)


@dataclass
class GroupScore:
    """Exact-address rate for one tag."""

    exact: int = 0
    total: int = 0

    @property
    def rate(self) -> float:
        return self.exact / self.total if self.total else 0.0


@dataclass
class Report:
    """The result of scoring a parser on a list of cases."""

    fields: dict[str, FieldScore] = field(default_factory=dict)
    groups: dict[str, GroupScore] = field(default_factory=dict)
    failures: list[Failure] = field(default_factory=list)
    exact: int = 0
    total: int = 0
    crashes: int = 0

    @property
    def overall(self) -> FieldScore:
        """Micro average: all fields counted together."""
        result = FieldScore()
        for score in self.fields.values():
            result.add(score)
        return result

    @property
    def exact_rate(self) -> float:
        return self.exact / self.total if self.total else 0.0


def evaluate(cases: Iterable[Case], predict: Predict) -> Report:
    """Run ``predict`` on every case and score the output.

    A parser that raises is scored as an empty result and counted in
    ``crashes``: one bad address must not hide the rest of the report.
    """
    report = Report(fields={name: FieldScore() for name in FIELDS})
    for case in cases:
        try:
            predicted = predict(case.girdi)
        except Exception:
            report.crashes += 1
            predicted = {}

        wrong: dict[str, tuple[str, str]] = {}
        for name in FIELDS:
            want, got = case.beklenen.get(name), predicted.get(name)
            score = score_field(want, got)
            report.fields[name].add(score)
            if score.fp or score.fn:
                wrong[name] = (str(want or ""), str(got or ""))

        report.total += 1
        report.exact += not wrong
        if wrong:
            report.failures.append(Failure(case=case, wrong=wrong))
        for tag in case.etiketler:
            group = report.groups.setdefault(tag, GroupScore())
            group.total += 1
            group.exact += not wrong
    return report
