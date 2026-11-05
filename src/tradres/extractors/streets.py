"""Named parts: mahalle, bulvar, cadde, sokak, site, bina adı and blok.

In Turkish the name comes first and the keyword closes it: "Gazi Mustafa Kemal
Bulvarı". So we walk from left to right, collect free words, and give them to
the next keyword. A separator, or a token an earlier step used, starts over.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence

from tradres.abbreviations import load_description_words, load_name_words
from tradres.extractors import Extraction
from tradres.normalization import tr_title, tr_upper
from tradres.scoring import Origin
from tradres.tokenizer import Token, street_keyword

__all__ = ["extract_streets"]

_FIELD_OF_KIND = {"apartman": "bina_adi"}  # the other kinds have the field's own name
_NUMBER_WORDS = frozenset({"nolu", "numarali"})  # "1 Nolu Sokak" -> "1"
# They work like "Sitesi", but they stay in the name: "Öğretmen Lojmanları".
_SITE_NAME_ENDS = frozenset(
    {"bolgesi", "konutlari", "lojman", "lojmani", "lojmanlar", "lojmanlari"}
)
# The same for one building: "Mavi İş Merkezi".
_BUILDING_NAME_ENDS = frozenset({"merkezi"})
_MIN_BLOCK_WORD_LENGTH = 3  # "A", "C3" are codes; "Batı" is a word


def _name(tokens: Sequence[Token]) -> str:
    words = [token for token in tokens if token.key not in _NUMBER_WORDS]
    if len(words) == 1 and words[0].is_number:
        return words[0].text.rstrip(".")  # "1923. Cadde" -> "1923"
    name_words = load_name_words()
    texts = [name_words.get(token.key, token.text) for token in words]
    if words and words[-1].is_number:
        texts[-1] = texts[-1].rstrip(".")  # "Lale Bey 4. Sok." -> "Lale Bey 4"
    return tr_title(" ".join(texts))


def _block_name(text: str) -> str:
    name = text.rstrip(".")
    return (
        tr_title(name) if name.isalpha() and len(name) >= _MIN_BLOCK_WORD_LENGTH else tr_upper(name)
    )


def _after_description(names: Sequence[int], tokens: Sequence[Token]) -> list[int]:
    """A building name starts after a direction: "karayolu üzeri Güneş Apt." -> "Güneş".

    Such words are real parts of street names ("Cami Yanı Sokak"), so this rule
    is for buildings and estates only.
    """
    ends = load_description_words()
    for position in range(len(names) - 1, -1, -1):
        if tokens[names[position]].key in ends:
            return list(names[position + 1 :])
    return list(names)


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
        after = tokens[index + 1] if index + 1 < len(tokens) else None
        closing = (
            "site"
            if token.key in _SITE_NAME_ENDS
            else "bina_adi"
            if token.key in _BUILDING_NAME_ENDS
            else None
        )
        closes_name = closing is not None and closing not in fields
        if keyword is None and closing and closes_name and not (after and street_keyword(after)):
            names = _after_description(pending, tokens)
            pending = []
            if names:
                fields[closing] = _name([tokens[i] for i in [*names, index]])
                taken.update([*names, index])
            continue
        names_a_landmark = (
            keyword is not None
            and keyword.kind in ("site", "apartman")
            and after is not None
            and after.key in load_description_words()
        )
        if keyword is None or names_a_landmark:  # "Sanayi Sitesi yanı" is a direction
            pending.append(index)
            continue

        field = _FIELD_OF_KIND.get(keyword.kind, keyword.kind)
        names = pending
        pending = []
        if field in fields:
            continue
        if field in ("bina_adi", "site"):
            names = _after_description(names, tokens)
        if field == "blok":
            names = names[-1:]  # a block is one piece: "Kardelen C Blok"
            following = index + 1
            has_next = following < len(tokens) and following not in used
            if not names and has_next and not tokens[following].is_separator:
                names = [following]  # "Blok A2"
            if names:
                fields[field] = _block_name(tokens[names[0]].text)
        elif names:
            fields[field] = _name([tokens[i] for i in names])
        if field in fields:
            taken.update(names)
            taken.add(index)

    return Extraction(
        fields=fields, used=frozenset(taken), origins=dict.fromkeys(fields, Origin.KEYWORD)
    )
