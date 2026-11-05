"""İl and ilçe, found with the gazetteer."""

from __future__ import annotations

from collections.abc import Collection, Iterator, Sequence
from dataclasses import dataclass, replace

from tradres.extractors import Extraction
from tradres.gazetteer import Gazetteer, Il, Ilce
from tradres.matching import DEFAULT_CONFIG, MatchConfig
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


def _best_pair(
    iller: Sequence[tuple[Window, Il]], ilceler: Sequence[tuple[Window, list[Ilce]]]
) -> _Found | None:
    """A province and one of its districts, best next to each other and late in the text."""
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
    return best[1] if best is not None else None


def _with_fuzzy_ilce(
    found: _Found,
    windows: Sequence[Window],
    gazetteer: Gazetteer,
    config: MatchConfig,
) -> _Found:
    """Look for a misspelled district of the known province."""
    assert found.il is not None
    il_window, il = found.il
    for window in reversed(windows):
        if _overlap(window, il_window) or gazetteer.find_mahalle(window.text, il=il.ad):
            continue
        ilce = gazetteer.fuzzy_ilce(window.text, il=il.ad, config=config)
        if ilce is not None:
            return replace(found, ilce=(window, ilce))
    return found


def _choose(
    tokens: Sequence[Token],
    used: Collection[int],
    gazetteer: Gazetteer,
    config: MatchConfig,
) -> _Found:
    windows = list(free_windows(tokens, used))
    iller: list[tuple[Window, Il]] = []
    ilceler: list[tuple[Window, list[Ilce]]] = []
    for window in windows:
        il = gazetteer.find_il(window.text)
        if il is not None:
            iller.append((window, il))
        matches = gazetteer.find_ilce(window.text)
        if matches:
            ilceler.append((window, matches))

    pair = _best_pair(iller, ilceler)
    if pair is not None:
        return pair
    if iller:
        return _with_fuzzy_ilce(_Found(il=iller[-1]), windows, gazetteer, config)

    # No province as written: a misspelled one, then a one-province district name.
    misspelled: list[tuple[Window, Il]] = []
    for window in windows:
        il = gazetteer.fuzzy_il(window.text, config) if window.end - window.start == 1 else None
        if il is not None and not gazetteer.find_ilce(window.text):
            misspelled.append((window, il))
    pair = _best_pair(misspelled, ilceler)
    if pair is not None:
        return pair

    unique = [(window, matches[0]) for window, matches in ilceler if len(matches) == 1]
    if unique:
        return _Found(ilce=unique[-1])
    if misspelled:
        return _with_fuzzy_ilce(_Found(il=misspelled[-1]), windows, gazetteer, config)
    for window in reversed(windows):
        ilce = gazetteer.fuzzy_ilce(window.text, config=config)
        if ilce is not None:
            return _Found(ilce=(window, ilce))
    return _Found()


def extract_places(
    tokens: Sequence[Token],
    used: Collection[int],
    gazetteer: Gazetteer,
    config: MatchConfig = DEFAULT_CONFIG,
) -> Extraction:
    """Find il and ilçe among the free tokens.

    >>> from tradres.gazetteer import load_gazetteer
    >>> from tradres.tokenizer import tokenize
    >>> extract_places(tokenize("Van Cad. Kadıköy"), (), load_gazetteer()).fields
    {'il': 'İstanbul', 'ilce': 'Kadıköy'}
    """
    found = _choose(tokens, used, gazetteer, config)
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
