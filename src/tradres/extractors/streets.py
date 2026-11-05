"""Named parts: mahalle, bulvar, cadde, sokak, site, bina adı and blok.

In Turkish the name comes first and the keyword closes it: "Gazi Mustafa Kemal
Bulvarı". So we walk from left to right, collect free words, and give them to
the next keyword. A separator, or a token an earlier step used, starts over.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence

from tradres.extractors import Extraction
from tradres.normalization import tr_title, tr_upper
from tradres.tokenizer import Token, street_keyword

__all__ = ["extract_streets"]

_FIELD_OF_KIND = {"apartman": "bina_adi"}  # the other kinds have the field's own name
_NUMBER_WORDS = frozenset({"nolu", "numarali"})  # "1 Nolu Sokak" -> "1"


def _name(tokens: Sequence[Token]) -> str:
    words = [token for token in tokens if token.key not in _NUMBER_WORDS]
    if len(words) == 1 and words[0].is_number:
        return words[0].text.rstrip(".")  # "1923. Cadde" -> "1923"
    return tr_title(" ".join(token.text for token in words))


def extract_streets(tokens: Sequence[Token], used: Collection[int]) -> Extraction:
    """Give the free words before each keyword to that keyword's field.

    >>> from tradres.tokenizer import tokenize
    >>> extract_streets(tokenize("Kızılay Mah. Gazi Mustafa Kemal Blv."), ()).fields
    {'mahalle': 'Kızılay', 'bulvar': 'Gazi Mustafa Kemal'}
    """
    fields: dict[str, str] = {}
    taken: set[int] = set()
    pending: list[int] = []

    for index, token in enumerate(tokens):
        if index in used or index in taken or token.is_separator:
            pending = []
            continue
        keyword = street_keyword(token)
        if keyword is None:
            pending.append(index)
            continue

        field = _FIELD_OF_KIND.get(keyword.kind, keyword.kind)
        names = pending
        pending = []
        if field in fields:
            continue
        if field == "blok":
            names = names[-1:]  # a block is one piece: "Kardelen C Blok"
            following = index + 1
            has_next = following < len(tokens) and following not in used
            if not names and has_next and not tokens[following].is_separator:
                names = [following]  # "Blok A2"
            if names:
                fields[field] = tr_upper(tokens[names[0]].text.rstrip("."))
        elif names:
            fields[field] = _name([tokens[i] for i in names])
        if field in fields:
            taken.update(names)
            taken.add(index)

    return Extraction(fields=fields, used=frozenset(taken))
