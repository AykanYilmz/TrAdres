"""The pipeline: text -> tokens -> numbers -> places -> streets -> Address."""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence

from tradres.abbreviations import load_country_names, load_description_words, lookup
from tradres.extractors.numbers import compact_number, extract_numbers
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
_MAX_PIECE_MAHALLE_WORDS = 3
_MAX_LOOSE_SITE_WORDS = 3
_CENTRE_WORD = "merkez"
_MIN_GLUED_WORDS = 2
_COMMAS = frozenset(",;")
#: Letters of a Google Plus Code: "8Q5V+2H".
_PLUS_CODE = re.compile(r"[23456789CFGHJMPQRVWX]{2,8}\+[23456789CFGHJMPQRVWX]{2,3}", re.IGNORECASE)


def country_word(tokens: Sequence[Token]) -> set[int]:
    """The country at either end: "Çankaya/Ankara, Türkiye" or "Türkiye, Çankaya/Ankara".

    At the start a separator must follow, because "Türkiye Sokak" is a street.
    """
    countries = load_country_names()
    words = [index for index, token in enumerate(tokens) if not token.is_separator]
    found = set()
    if words and tokens[words[-1]].key in countries:
        found.add(words[-1])
    if len(words) > 1 and tokens[words[0]].key in countries and tokens[words[0] + 1].is_separator:
        found.add(words[0])
    return found


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
    common = gazetteer.fuzzy_common_mahalle(name, config)
    if common is not None:
        return common, Origin.FUZZY
    return gazetteer.respell(name), Origin.UNVERIFIED


def district_of_mahalle(fields: Mapping[str, str], gazetteer: Gazetteer) -> tuple[str, str] | None:
    """The (il, ilçe) a mahalle fixes, when only one place has that name."""
    if "mahalle" not in fields or "ilce" in fields:
        return None
    matches = gazetteer.find_mahalle(fields["mahalle"], il=fields.get("il"))
    places = {(match.il, match.ilce) for match in matches}
    return places.pop() if len(places) == 1 else None


def mahalle_in_street(
    fields: Mapping[str, str], gazetteer: Gazetteer
) -> tuple[str, str, str] | None:
    """A mahalle glued to the street after it: (field, mahalle, street).

    "Etlik 512. Sokak" and "Kızılay Lale Sokak" have no comma or keyword after
    the mahalle. The first words must be a mahalle of the known district. A
    street name that is a place name itself stays whole: "Fatih Sultan Mehmet".
    """
    il, ilce = fields.get("il"), fields.get("ilce")
    if il is None or ilce is None or "mahalle" in fields:
        return None
    for field in ("bulvar", "cadde", "sokak"):
        words = fields.get(field, "").split()
        if len(words) < _MIN_GLUED_WORDS or gazetteer.find_mahalle(" ".join(words)):
            continue
        for size in range(len(words) - 1, 0, -1):
            head = " ".join(words[:size])
            if gazetteer.find_mahalle(head, il=il, ilce=ilce):
                return field, head, " ".join(words[size:])
    return None


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
            word.is_number
            or word.key in load_description_words()
            or street_keyword(word)
            or _PLUS_CODE.fullmatch(word.text)
            for word in words
        ):
            return run
        run = []
    return []


def before_number_word(tokens: Sequence[Token], run: Sequence[int]) -> bool:
    """True for "Kordon Boyu No:6": a street without a keyword, not an area name."""
    following = run[-1] + 1
    if following >= len(tokens):
        return False
    found = lookup(tokens[following].text)
    return found is not None and found.kind == "bina_no"


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


def centre_words(
    tokens: Sequence[Token],
    used: Collection[int],
    fields: Mapping[str, str],
    gazetteer: Gazetteer,
) -> set[int]:
    """ "Merkez" after the il or ilçe: "Van Merkez" is the centre of Van, not a mahalle.

    A district that really has a mahalle called Merkez gives no words here. The
    word stays in ``kalan``: it says something, but no field can hold it.
    """
    il, ilce = fields.get("il"), fields.get("ilce")
    if gazetteer.find_mahalle(_CENTRE_WORD, il=il, ilce=ilce):
        return set()
    names = {ascii_key(name) for name in (il, ilce) if name}
    return {
        index
        for index in range(1, len(tokens))
        if index not in used
        and tokens[index].key == _CENTRE_WORD
        and ascii_key(tokens[index - 1].text) in names
    }


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

    The result is always an :class:`Address`: text that makes no sense gives
    empty fields and goes to ``kalan``. It does not raise an error. ``config``
    sets how far a misspelled place name may be from the real one.

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
    used |= numbers.used | country_word(tokens)

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
            fields[field] = gazetteer.respell(fields[field], capitals=text.isupper())

    hidden = mahalle_in_street(fields, gazetteer)
    if hidden is not None:
        street, name, street_name = hidden
        fields["mahalle"] = name
        fields[street] = street_name
        origins["mahalle"] = Origin.KEYWORD

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
            free = used | centre_words(tokens, used, fields, gazetteer)
            loose = loose_words(tokens, free, max_words=_MAX_LOOSE_MAHALLE_WORDS) or loose_words(
                tokens, free, max_words=_MAX_PIECE_MAHALLE_WORDS, own_piece=True
            )
            if loose and not before_number_word(tokens, loose):
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
            fields["bina_no"] = compact_number(tokens[index].text.rstrip("."))
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
