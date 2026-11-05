"""Pipeline steps. Each one reads the tokens and returns an :class:`Extraction`."""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["Extraction"]


@dataclass(frozen=True)
class Extraction:
    """What a step found.

    Attributes:
        fields: Address field -> value.
        used: Indexes of the tokens the step consumed. Later steps skip them,
            and what no step uses ends up in ``kalan``.
    """

    fields: dict[str, str] = field(default_factory=dict)
    used: frozenset[int] = frozenset()
