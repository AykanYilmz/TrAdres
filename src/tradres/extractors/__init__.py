"""Pipeline steps. Each one reads the tokens and returns an :class:`Extraction`."""

from __future__ import annotations

from dataclasses import dataclass, field

from tradres.scoring import Origin

__all__ = ["Extraction"]


@dataclass(frozen=True)
class Extraction:
    """What a step found.

    Attributes:
        fields: Address field -> value.
        used: Indexes of the tokens the step consumed. Later steps skip them,
            and what no step uses ends up in ``kalan``.
        origins: How a value was found, for fields that differ from the
            step's usual way.
    """

    fields: dict[str, str] = field(default_factory=dict)
    used: frozenset[int] = frozenset()
    origins: dict[str, Origin] = field(default_factory=dict)
