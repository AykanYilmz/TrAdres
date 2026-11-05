"""İl and ilçe, found with the gazetteer."""

from __future__ import annotations

from collections.abc import Collection, Iterator, Sequence
from dataclasses import dataclass

from tradres.extractors import Extraction
from tradres.gazetteer import Gazetteer, Il, Ilce
from tradres.tokenizer import Token, street_keyword

__all__ = ["extract_places", "free_windows"]

_MAX_NAME_WORDS = 3  # "Karadeniz Ereğli", "Kahramanmaraş" ... no name is longer
_DISTRICT_WORDS = frozenset({"ilce", "ilcesi"})  # "Pınarbaşı ilçesi"


@dataclass(frozen=True)
class Window:
    """Consecutive free tokens that may form one name."""

    start: int
    end: int  # exclusive
    text: str


def free_windows(tokens: Sequence[Token], used: Collection[int]) -> Iterator[Window]:
    """Every run of up to three free tokens that can be a place name.

    A name right before a keyword is skipped: in "Van Cad." or "Fatih Mah."
    the word names the street or the neighbourhood, not the province.
    """
    for start in range(len(tokens)):
        for end in range(start + 1, min(start + _MAX_NAME_WORDS, len(tokens)) + 1):
            last = tokens[end - 1]
            if end - 1 in used or last.is_separator or street_keyword(last):
                break
            following = tokens[end] if end < len(tokens) else None
            if following is not None and (street_keyword(following) or following.key == "nolu"):
                continue
            yield Window(start, end, " ".join(token.text for token in tokens[start:end]))


@dataclass(frozen=True)
class _Found:
    il: tuple[Window, Il] | None = None
    ilce: tuple[Window, Ilce] | None = None


def _overlap(left: Window, right: Window) -> bool:
    return left.start < right.end and right.start < left.end


def _choose(tokens: Sequence[Token], used: Collection[int], gazetteer: Gazetteer) -> _Found:
    iller: list[tuple[Window, Il]] = []
    ilceler: list[tuple[Window, list[Ilce]]] = []
    for window in free_windows(tokens, used):
        il = gazetteer.find_il(window.text)
        if il is not None:
            iller.append((window, il))
        matches = gazetteer.find_ilce(window.text)
        if matches:
            ilceler.append((window, matches))

    # Best: a province and one of its districts, next to each other, late in the text.
    best: tuple[tuple[bool, int, int], _Found] | None = None
    for il_window, il in iller:
        for ilce_window, matches in ilceler:
            ilce = next((item for item in matches if item.il == il.ad), None)
            if ilce is None or _overlap(il_window, ilce_window):
                continue
            adjacent = il_window.end == ilce_window.start or ilce_window.end == il_window.start
            end = max(il_window.end, ilce_window.end)
            size = (il_window.end - il_window.start) + (ilce_window.end - ilce_window.start)
            score = (adjacent, end, size)
            if best is None or score > best[0]:
                best = (score, _Found((il_window, il), (ilce_window, ilce)))
    if best is not None:
        return best[1]

    if iller:
        return _Found(il=iller[-1])
    # No province written: a district name used by only one province is enough.
    unique = [(window, matches[0]) for window, matches in ilceler if len(matches) == 1]
    return _Found(ilce=unique[-1]) if unique else _Found()


def extract_places(
    tokens: Sequence[Token], used: Collection[int], gazetteer: Gazetteer
) -> Extraction:
    """Find il and ilçe among the free tokens.

    >>> from tradres.gazetteer import load_gazetteer
    >>> from tradres.tokenizer import tokenize
    >>> extract_places(tokenize("Van Cad. Kadıköy"), (), load_gazetteer()).fields
    {'il': 'İstanbul', 'ilce': 'Kadıköy'}
    """
    found = _choose(tokens, used, gazetteer)
    fields: dict[str, str] = {}
    taken: set[int] = set()
    if found.il is not None:
        window, il = found.il
        fields["il"] = il.ad
        taken.update(range(window.start, window.end))
    if found.ilce is not None:
        window, ilce = found.ilce
        fields["il"] = ilce.il
        fields["ilce"] = ilce.ad
        taken.update(range(window.start, window.end))
        if window.end < len(tokens) and tokens[window.end].key in _DISTRICT_WORDS:
            taken.add(window.end)
    return Extraction(fields=fields, used=frozenset(taken))
