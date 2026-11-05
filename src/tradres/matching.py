"""Fuzzy matching: find the name a misspelled word most likely stands for.

We use OSA distance (optimal string alignment): the number of edits between two
words, where an edit adds, removes or replaces a letter, or swaps two letters
next to each other. A swap ("Malatay") is one of the most common typing mistakes
and costs 1 here, but 2 in plain Levenshtein distance.

Words are compared by their ASCII keys, so "Çankya" and "cankya" are the same.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from rapidfuzz import process
from rapidfuzz.distance import OSA

__all__ = ["DEFAULT_CONFIG", "MatchConfig", "closest"]


@dataclass(frozen=True)
class MatchConfig:
    """How far a word may be from a name. Pass your own to ``parse``.

    Attributes:
        min_length: Shorter words are never corrected: "Van" and "Yan" are one
            edit apart, so short words carry too little evidence.
        min_mahalle_length: The same for mahalle names. Some real mahalle are
            missing from our data, and a missing "Çınar" must not become "Pınar".
        short_edits: Edits allowed in a word shorter than ``long_length``.
        long_edits: Edits allowed from ``long_length`` letters on.
        long_length: The length where a word counts as long.
    """

    min_length: int = 4
    min_mahalle_length: int = 6
    short_edits: int = 1
    long_edits: int = 2
    long_length: int = 8

    def allowed_edits(self, key: str) -> int:
        """Edits allowed for this word."""
        return self.long_edits if len(key) >= self.long_length else self.short_edits


DEFAULT_CONFIG = MatchConfig()


def closest(key: str, choices: Iterable[str], config: MatchConfig = DEFAULT_CONFIG) -> str | None:
    """The single closest choice within the allowed edits, or ``None``.

    A tie returns ``None``: when two names fit equally well, guessing one of
    them would hide the doubt.

    >>> closest("malatay", ["malatya", "manisa"])
    'malatya'
    >>> closest("kalo", ["kale", "kala"]) is None  # one edit from both
    True
    """
    limit = config.allowed_edits(key)
    found = process.extract(key, list(choices), scorer=OSA.distance, score_cutoff=limit, limit=2)
    if not found:
        return None
    if len(found) == 2 and found[0][1] == found[1][1]:
        return None
    return str(found[0][0])
