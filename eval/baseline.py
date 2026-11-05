"""A deliberately simple parser: the score any real parser must beat.

It uses regular expressions for labelled numbers, takes the word before a
keyword as the name, and looks up single words in the gazetteer. It has no
ordering logic, no multi-word names and no typo handling. It also shows that
the evaluation works before the real parser exists.
"""

from __future__ import annotations

import itertools
import re

from tradres.abbreviations import lookup
from tradres.gazetteer import load_gazetteer
from tradres.normalization import normalize, tr_title

_NUMBERS = {
    "bina_no": re.compile(r"\bno[:.]?\s*(\d+[a-z]?)"),
    "kat": re.compile(r"\b(?:kat|k)[:.]?\s*(\d+)"),
    "daire": re.compile(r"\b(?:daire|d)[:.]?\s*(\d+)"),
}
_POSTAL_CODE = re.compile(r"\b(\d{5})\b")
_KEYWORD_FIELDS = {"mahalle", "cadde", "sokak", "bulvar"}


def parse(text: str) -> dict[str, str]:
    """Return the fields this simple approach can find."""
    normalized = normalize(text)
    result: dict[str, str] = {}
    for name, pattern in _NUMBERS.items():
        match = pattern.search(normalized)
        if match:
            result[name] = match.group(1)
    postal = _POSTAL_CODE.search(normalized)
    if postal:
        result["posta_kodu"] = postal.group(1)

    words = [word.strip(",.:;/()") for word in normalized.split()]
    words = [word for word in words if word]
    for previous, word in itertools.pairwise(words):
        keyword = lookup(word)
        if keyword is not None and keyword.kind in _KEYWORD_FIELDS:
            result[keyword.kind] = tr_title(previous)

    gazetteer = load_gazetteer()
    for word in reversed(words):
        il = gazetteer.find_il(word)
        if il is not None:
            result["il"] = il.ad
            break
    for word in words:
        ilceler = gazetteer.find_ilce(word, il=result.get("il"))
        if len(ilceler) == 1:
            result["ilce"] = ilceler[0].ad
            result.setdefault("il", ilceler[0].il)
            break
    return result
