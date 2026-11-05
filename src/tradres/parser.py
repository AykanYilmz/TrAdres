"""The pipeline: text -> tokens -> numbers -> places -> streets -> Address."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence

from tradres.abbreviations import load_description_words
from tradres.extractors.numbers import extract_numbers
from tradres.extractors.places import extract_places, free_windows
from tradres.extractors.streets import extract_streets
from tradres.gazetteer import Gazetteer, load_gazetteer
from tradres.matching import DEFAULT_CONFIG, MatchConfig
from tradres.models import Address
from tradres.normalization import ascii_key, tr_title
from tradres.scoring import Origin, score_address
from tradres.tokenizer import Token, street_keyword, tokenize

__all__ = ["parse"]

_NAME_FIELDS = ("bulvar", "cadde", "sokak", "site", "bina_adi")
_MAX_LOOSE_MAHALLE_WORDS = 2
_MAX_LOOSE_SITE_WORDS = 3
_COMMAS = frozenset(",;")


def official_mahalle(
    name: str,
    fields: Mapping[str, str],
    gazetteer: Gazetteer,
    config: MatchConfig = DEFAULT_CONFIG,
) -> tuple[str, Origin]:
    """Official spelling of a mahalle, and how far we can trust it.

    Search the same district, the same province, and then everywhere. A name
    that exists somewhere is a real name, not a typo, so a typo inside the
    district comes last. If nothing fits, the name stays as written.
    """
    il, ilce = fields.get("il"), fields.get("ilce")
    for filters in ({"il": il, "ilce": ilce}, {"il": il}, {}):
        matches = gazetteer.find_mahalle(name, **filters)
        if matches:
            trusted = filters.get("il") is not None or il is None
            return matches[0].ad, Origin.EXACT if trusted else Origin.UNVERIFIED
    if il is not None and ilce is not None:
        corrected = gazetteer.fuzzy_mahalle(name, il=il, ilce=ilce, config=config)
        if corrected is not None:
            return corrected.ad, Origin.FUZZY
    return gazetteer.respell(name), Origin.UNVERIFIED


def district_of_mahalle(fields: Mapping[str, str], gazetteer: Gazetteer) -> tuple[str, str] | None:
    """The (il, ilçe) a mahalle fixes, when only one place has that name."""
    if "mahalle" not in fields or "ilce" in fields:
        return None
    matches = gazetteer.find_mahalle(fields["mahalle"], il=fields.get("il"))
    places = {(match.il, match.ilce) for match in matches}
    return places.pop() if len(places) == 1 else None


def mahalle_without_keyword(
    tokens: Sequence[Token],
    used: Collection[int],
    fields: Mapping[str, str],
    gazetteer: Gazetteer,
) -> tuple[str, range] | None:
    """Free words that name a mahalle of the known district: "Hassa Yukarıkarafakılı"."""
    il, ilce = fields.get("il"), fields.get("ilce")
    if il is None or ilce is None:
        return None
    windows = sorted(
        free_windows(tokens, used),
        key=lambda window: window.end - window.start,
        reverse=True,
    )
    for window in windows:
        matches = gazetteer.find_mahalle(window.text, ilce=ilce, il=il)
        if matches:
            return matches[0].ad, range(window.start, window.end)
    return None


def _in_own_piece(tokens: Sequence[Token], run: Sequence[int]) -> bool:
    """True if commas or the ends of the text mark off these tokens."""
    first, last = run[0], run[-1]
    before = first == 0 or tokens[first - 1].text in _COMMAS
    after = last == len(tokens) - 1 or tokens[last + 1].text in _COMMAS
    return before and after


def loose_words(
    tokens: Sequence[Token],
    used: Collection[int],
    *,
    max_words: int,
    own_piece: bool = False,
) -> list[int]:
    """Words standing alone, which may name a place we have no list for.

    "Yenimahalle Ankara, Batıkent, 1923. Cadde": il and ilçe are known and
    "Batıkent" is a separate piece. Numbers, keywords and directions ("okul
    yanı") do not count. With ``own_piece``, commas must mark off the words.
    """
    run: list[int] = []
    for index, token in enumerate([*tokens, None]):
        if token is not None and index not in used and not token.is_separator:
            run.append(index)
            continue
        words = [tokens[i] for i in run]
        fits = 0 < len(run) <= max_words and (not own_piece or _in_own_piece(tokens, run))
        if fits and not any(
            word.is_number or word.key in load_description_words() or street_keyword(word)
            for word in words
        ):
            return run
        run = []
    return []


def repeated_places(
    tokens: Sequence[Token],
    used: Collection[int],
    fields: Mapping[str, str],
    gazetteer: Gazetteer,
) -> set[int]:
    """Words that repeat the known il or ilçe: "Bolu Merkez/Bolu" says Bolu twice."""
    repeated: set[int] = set()
    il, ilce = fields.get("il"), fields.get("ilce")
    for window in free_windows(tokens, used):
        province = gazetteer.find_il(window.text)
        same_il = province is not None and province.ad == il
        same_ilce = ilce is not None and ascii_key(window.text) == ascii_key(ilce)
        if same_il or same_ilce:
            repeated.update(range(window.start, window.end))
    return repeated


def description(tokens: Sequence[Token], used: Collection[int]) -> list[int]:
    """Free words up to a word that ends a direction: "D 100 karayolu üzeri".

    Only the first direction is kept. A field holds one value, and any other
    free text stays in ``kalan``.
    """
    ends = load_description_words()
    run: list[int] = []
    for index, token in enumerate([*tokens, None]):
        if token is not None and index not in used and not token.is_separator:
            run.append(index)
            continue
        last = [position for position, i in enumerate(run) if tokens[i].key in ends]
        if last:
            return run[: last[-1] + 1]
        run = []
    return []


def number_after_keyword(tokens: Sequence[Token], used: Collection[int]) -> int | None:
    """A bare number right after a street keyword: "Gazi Cad. 15"."""
    for index in range(1, len(tokens)):
        if index not in used and tokens[index].is_number and street_keyword(tokens[index - 1]):
            return index
    return None


def parse(text: str, *, config: MatchConfig = DEFAULT_CONFIG) -> Address:
    """Split a Turkish address into its parts.

    ``config`` sets how far a misspelled place name may be from the real one.

    >>> address = parse("Kızılay Mah. Gül Sk. No:5/3 Çankaya/Ankara")
    >>> address.il, address.ilce, address.mahalle, address.sokak
    ('Ankara', 'Çankaya', 'Kızılay', 'Gül')
    >>> address.bina_no, address.daire
    ('5', '3')
    """
    gazetteer = load_gazetteer()
    tokens = tokenize(text)
    fields: dict[str, str] = {}
    origins: dict[str, Origin] = {}
    used: set[int] = set()

    numbers = extract_numbers(tokens)
    fields.update(numbers.fields)
    origins.update(dict.fromkeys(numbers.fields, Origin.EXACT), **numbers.origins)
    used |= numbers.used

    places = extract_places(tokens, used, gazetteer, config)
    fields.update(places.fields)
    origins.update(places.origins)
    used |= places.used

    streets = extract_streets(tokens, used)
    fields.update(streets.fields)
    origins.update(streets.origins)
    used |= streets.used

    used |= repeated_places(tokens, used, fields, gazetteer)

    for field in _NAME_FIELDS:
        if field in fields:
            fields[field] = gazetteer.respell(fields[field])

    if "mahalle" in fields:
        fields["mahalle"], origins["mahalle"] = official_mahalle(
            fields["mahalle"], fields, gazetteer, config
        )
    else:
        found = mahalle_without_keyword(tokens, used, fields, gazetteer)
        if found is not None:
            fields["mahalle"] = found[0]
            origins["mahalle"] = Origin.EXACT
            used.update(found[1])
        elif "il" in fields and "ilce" in fields:
            loose = loose_words(tokens, used, max_words=_MAX_LOOSE_MAHALLE_WORDS)
            if loose:
                name = tr_title(" ".join(tokens[index].text for index in loose))
                fields["mahalle"] = gazetteer.respell(name)
                origins["mahalle"] = Origin.UNVERIFIED
                used.update(loose)

    place = district_of_mahalle(fields, gazetteer)
    if place is not None:
        fields["ilce"] = place[1]
        origins["ilce"] = Origin.INFERRED
        if "il" not in fields:
            fields["il"] = place[0]
            origins["il"] = Origin.INFERRED

    if "bina_no" not in fields:
        index = number_after_keyword(tokens, used)
        if index is not None:
            fields["bina_no"] = tokens[index].text.rstrip(".")
            origins["bina_no"] = Origin.KEYWORD
            used.add(index)

    directions = description(tokens, used)
    if directions:
        fields["tarif"] = " ".join(tokens[index].text for index in directions)
        origins["tarif"] = Origin.KEYWORD
        used.update(directions)

    if "mahalle" in fields and "site" not in fields:
        loose = loose_words(tokens, used, max_words=_MAX_LOOSE_SITE_WORDS, own_piece=True)
        if loose:
            name = tr_title(" ".join(tokens[index].text for index in loose))
            fields["site"] = gazetteer.respell(name)
            origins["site"] = Origin.UNVERIFIED
            used.update(loose)

    rest = [
        token.text
        for index, token in enumerate(tokens)
        if index not in used and not token.is_separator
    ]
    words = sum(not token.is_separator for token in tokens)
    scores = score_address(origins, total_words=words, leftover_words=len(rest))
    return Address(
        **fields,
        kalan=" ".join(rest) or None,
        confidence=scores.overall,
        field_confidence=scores.fields,
    )
