"""The pipeline: text -> tokens -> numbers -> places -> streets -> Address."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence

from tradres.extractors.numbers import extract_numbers
from tradres.extractors.places import extract_places, free_windows
from tradres.extractors.streets import extract_streets
from tradres.gazetteer import Gazetteer, load_gazetteer
from tradres.models import Address
from tradres.tokenizer import Token, street_keyword, tokenize

__all__ = ["parse"]


def official_mahalle(name: str, fields: Mapping[str, str], gazetteer: Gazetteer) -> str:
    """Official spelling of a mahalle: same district first, then anywhere.

    If the gazetteer does not know the name, it stays as written.
    """
    il, ilce = fields.get("il"), fields.get("ilce")
    for filters in ({"il": il, "ilce": ilce}, {"il": il}, {}):
        matches = gazetteer.find_mahalle(name, **filters)
        if matches:
            return matches[0].ad
    return name


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


def number_after_keyword(tokens: Sequence[Token], used: Collection[int]) -> int | None:
    """A bare number right after a street keyword: "Gazi Cad. 15"."""
    for index in range(1, len(tokens)):
        if index not in used and tokens[index].is_number and street_keyword(tokens[index - 1]):
            return index
    return None


def parse(text: str) -> Address:
    """Split a Turkish address into its parts.

    >>> address = parse("Kızılay Mah. Gül Sk. No:5/3 Çankaya/Ankara")
    >>> address.il, address.ilce, address.mahalle, address.sokak
    ('Ankara', 'Çankaya', 'Kızılay', 'Gül')
    >>> address.bina_no, address.daire
    ('5', '3')
    """
    gazetteer = load_gazetteer()
    tokens = tokenize(text)
    fields: dict[str, str] = {}
    used: set[int] = set()

    numbers = extract_numbers(tokens)
    fields.update(numbers.fields)
    used |= numbers.used

    places = extract_places(tokens, used, gazetteer)
    fields.update(places.fields)
    used |= places.used

    streets = extract_streets(tokens, used)
    fields.update(streets.fields)
    used |= streets.used

    if "mahalle" in fields:
        fields["mahalle"] = official_mahalle(fields["mahalle"], fields, gazetteer)
    else:
        found = mahalle_without_keyword(tokens, used, fields, gazetteer)
        if found is not None:
            fields["mahalle"] = found[0]
            used.update(found[1])

    if "bina_no" not in fields:
        index = number_after_keyword(tokens, used)
        if index is not None:
            fields["bina_no"] = tokens[index].text.rstrip(".")
            used.add(index)

    rest = [
        token.text
        for index, token in enumerate(tokens)
        if index not in used and not token.is_separator
    ]
    return Address(**fields, kalan=" ".join(rest) or None)
