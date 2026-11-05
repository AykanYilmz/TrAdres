"""Confidence scores: how much to trust each field and the whole address.

These are rules, not probabilities. Each field gets a score from how it was
found (its :class:`Origin`). The address score is the weighted mean of the field
scores, where a missing il, ilçe or mahalle counts as 0, reduced by the share of
words that stayed in ``kalan``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

__all__ = ["Origin", "Scores", "score_address"]


class Origin(Enum):
    """How a value was found. The value of each member is its confidence."""

    EXACT = 1.0  # same as the official name, or a labelled number
    KEYWORD = 0.9  # closed by a keyword, but there is no list to check it against
    INFERRED = 0.8  # not written: worked out from another field
    FUZZY = 0.75  # a typo was corrected
    UNVERIFIED = 0.6  # the gazetteer does not confirm it, which also happens to real names
    MISMATCH = 0.3  # il, ilçe or mahalle do not belong together


_PLACE_WEIGHTS: Mapping[str, float] = {"il": 3.0, "ilce": 2.0, "mahalle": 2.0}
_OTHER_WEIGHT = 1.0
_MAX_LEFTOVER_PENALTY = 0.5


@dataclass(frozen=True)
class Scores:
    """The result of :func:`score_address`."""

    overall: float
    fields: Mapping[str, float]


def score_address(
    origins: Mapping[str, Origin], *, total_words: int, leftover_words: int
) -> Scores:
    """Score the fields that were found.

    >>> origins = {"il": Origin.EXACT, "ilce": Origin.EXACT, "mahalle": Origin.EXACT}
    >>> score_address(origins, total_words=4, leftover_words=0).overall
    1.0
    >>> score_address({"il": Origin.EXACT}, total_words=1, leftover_words=0).overall
    0.429
    """
    if not origins:
        return Scores(overall=0.0, fields={})
    per_field = {field: origin.value for field, origin in origins.items()}

    weight = sum(_PLACE_WEIGHTS.values())  # a missing place lowers the mean
    total = 0.0
    for field, score in per_field.items():
        field_weight = _PLACE_WEIGHTS.get(field)
        if field_weight is None:
            field_weight = _OTHER_WEIGHT
            weight += field_weight
        total += field_weight * score

    share = leftover_words / total_words if total_words else 0.0
    overall = total / weight * (1 - _MAX_LEFTOVER_PENALTY * share)
    return Scores(overall=round(overall, 3), fields=per_field)
