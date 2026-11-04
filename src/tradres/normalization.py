"""Text normalization for Turkish addresses.

Everything here is a pure function (no state, no I/O), so each step can be
tested on its own.

Three ideas live in this module:

* **Turkish casing** (:func:`tr_lower`, :func:`tr_upper`, :func:`tr_title`).
  Python's ``str.lower`` follows English rules: ``"I".lower() == "i"``. In
  Turkish the dotless and dotted i are different letters: ``I -> ı`` and
  ``İ -> i``.
* **ASCII key** (:func:`ascii_key`). People often type without Turkish
  letters (``cankaya`` for ``Çankaya``). We match names on a key where
  ``ç/c``, ``ş/s``, ``ı/i``... are the same, and we always *show* the
  correct Turkish spelling from our data.
* **Cleaning** (:func:`clean`, :func:`normalize`). Unify odd Unicode
  characters, put spaces in predictable places (``No:5`` -> ``No: 5``,
  ``23nisan`` -> ``23 nisan``) and collapse whitespace.
"""

from __future__ import annotations

import re
import unicodedata

__all__ = [
    "ascii_key",
    "clean",
    "normalize",
    "tr_lower",
    "tr_title",
    "tr_upper",
]

# --------------------------------------------------------------------------- #
# Turkish casing
# --------------------------------------------------------------------------- #

_TR_LOWER_SPECIAL = str.maketrans({"I": "ı", "İ": "i"})
_TR_UPPER_SPECIAL = str.maketrans({"i": "İ", "ı": "I"})


def tr_lower(text: str) -> str:
    """Lowercase ``text`` with Turkish rules (``I -> ı``, ``İ -> i``).

    >>> tr_lower("KIZILAY İSTANBUL")
    'kızılay istanbul'
    """
    # NFC first: "İ" can arrive decomposed as "I" + U+0307 (combining dot).
    # Composing it back makes the special mapping below see a single "İ".
    text = unicodedata.normalize("NFC", text)
    return unicodedata.normalize("NFC", text.translate(_TR_LOWER_SPECIAL).lower())


def tr_upper(text: str) -> str:
    """Uppercase ``text`` with Turkish rules (``i -> İ``, ``ı -> I``).

    >>> tr_upper("kızılay istanbul")
    'KIZILAY İSTANBUL'
    """
    text = unicodedata.normalize("NFC", text)
    return unicodedata.normalize("NFC", text.translate(_TR_UPPER_SPECIAL).upper())


def tr_title(text: str) -> str:
    """Capitalize the first letter of each space-separated word, Turkish rules.

    Only the first *letter* of a word is uppercased, so numbers and
    punctuation at the start are kept: ``"23 nisan"`` -> ``"23 Nisan"``,
    ``"(merkez)"`` -> ``"(Merkez)"``.

    >>> tr_title("İSTANBUL ışıklar caddesi")
    'İstanbul Işıklar Caddesi'
    """
    return " ".join(_title_word(word) for word in tr_lower(text).split(" "))


def _title_word(word: str) -> str:
    for i, char in enumerate(word):
        if char.isalpha():
            return word[:i] + tr_upper(char) + word[i + 1 :]
    return word


# --------------------------------------------------------------------------- #
# ASCII key
# --------------------------------------------------------------------------- #

# Letters that Unicode does NOT decompose into "base letter + accent".
# "ı" is its own letter in Unicode, so stripping accents would keep it;
# we map it by hand. (ç, ş, ğ, ö, ü, â, î, û all decompose, but listing the
# Turkish ones explicitly makes the intent obvious.)
_ASCII_FOLD = str.maketrans(
    {"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u", "â": "a", "î": "i", "û": "u"}
)
# Look-alike characters are written as code points so readers can tell them apart.
_DASHES = "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"  # hyphen ... em dash, minus sign
_SINGLE_QUOTES = "\u2018\u2019`\u00b4\u02bc"  # curly quotes, backtick, acute, modifier apostrophe
_DOUBLE_QUOTES = "\u201c\u201d\u201e\u00ab\u00bb"  # curly double quotes, guillemets
_APOSTROPHES = re.compile("['" + _SINGLE_QUOTES + "]")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def ascii_key(text: str) -> str:
    """Return a matching key: lowercase ASCII letters, digits and single spaces.

    Two spellings of the same name produce the same key, no matter the case or
    whether Turkish letters were used:

    >>> ascii_key("ÇANKAYA") == ascii_key("cankaya") == ascii_key("Çankaya")
    True
    >>> ascii_key("Atatürk'ün  Bulvarı.")
    'ataturkun bulvari'

    Never show this key to users; it is only for lookups.
    """
    text = tr_lower(text).translate(_ASCII_FOLD)
    if not text.isascii():
        # Remove remaining accents (é -> e): decompose, then drop combining marks.
        # Skipped when possible: it is the slowest step, and after the Turkish
        # letters are mapped most names are already plain ASCII.
        text = "".join(
            char for char in unicodedata.normalize("NFKD", text) if not unicodedata.combining(char)
        )
    text = _APOSTROPHES.sub("", text)  # "Atatürk'ün" -> "ataturkun", not "ataturk un"
    return _NON_ALNUM.sub(" ", text).strip()


# --------------------------------------------------------------------------- #
# Cleaning
# --------------------------------------------------------------------------- #

_PUNCT_UNIFY = str.maketrans(
    {
        **dict.fromkeys(_DASHES, "-"),
        **dict.fromkeys(_SINGLE_QUOTES, "'"),
        **dict.fromkeys(_DOUBLE_QUOTES, '"'),
    }
)

_LETTER = r"[^\W\d_]"  # any Unicode letter (word char that is not a digit or "_")

# Each rule is (pattern, replacement). Order matters; see clean().
_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    # "No:5" / "No :5" / "a ,b" -> "No: 5" / "a, b"
    (re.compile(r"\s*([,;:])\s*"), r"\1 "),
    # "Kızılay(Merkez)" -> "Kızılay (Merkez)"
    (re.compile(r"\s*\(\s*"), " ("),
    (re.compile(r"\s*\)\s*"), ") "),
    # "Merkez/Bolu" -> "Merkez / Bolu" (numbers are fixed by the next rule)
    (re.compile(r"\s*/\s*"), " / "),
    # "5 / 3" -> "5/3": between two digits a slash is "building/flat"
    (re.compile(r"(?<=\d) / (?=\d)"), "/"),
    # "Cad.No" / "Sk.5" -> "Cad. No" / "Sk. 5": after a word of 2+ letters.
    # Initials like "P.K." stay together.
    (re.compile(rf"(?<={_LETTER}{{2}})\.(?=\w)"), ". "),
    # "1923.Cadde" -> "1923. Cadde" (ordinal number), but "5.3" is kept.
    (re.compile(rf"(?<=\d)\.(?={_LETTER})"), ". "),
    # "23nisan" -> "23 nisan", "no5" -> "no 5".
    # Needs 2+ letters, so "5A" (building 5A) and "B3" (block B3) are kept.
    (re.compile(rf"(?<=\d)(?={_LETTER}{{2}})"), " "),
    (re.compile(rf"(?<={_LETTER}{{2}})(?=\d)"), " "),
)
_WHITESPACE = re.compile(r"\s+")


def clean(text: str) -> str:
    """Tidy ``text`` without changing letter case.

    * Unicode compatibility forms are unified (NFKC): full-width ``\uff2e\uff4f`` -> ``No``.
    * Invisible characters (zero-width space, control characters) are removed.
    * Different dashes and quotes become ``-``, ``'`` and ``"``.
    * Spaces are put in predictable places (see the rules above).
    * Whitespace is collapsed to single spaces and trimmed.

    >>> clean("Atatürk Mah.23nisan Cad.No:5/3 Merkez/Bolu")
    'Atatürk Mah. 23 nisan Cad. No: 5/3 Merkez / Bolu'
    """
    text = unicodedata.normalize("NFKC", text)
    text = "".join(_clean_char(char) for char in text)
    text = text.translate(_PUNCT_UNIFY)
    text = _WHITESPACE.sub(" ", text)
    for pattern, replacement in _RULES:
        text = pattern.sub(replacement, text)
    return _WHITESPACE.sub(" ", text).strip()


def _clean_char(char: str) -> str:
    category = unicodedata.category(char)
    if category == "Cf":  # format chars: zero-width space, BOM, soft hyphen...
        return ""
    if category in ("Cc", "Zl", "Zp", "Zs"):  # control chars and all space kinds
        return " "
    return char


def normalize(text: str) -> str:
    """Clean ``text`` and lowercase it with Turkish rules.

    This is the canonical form the parser works on. It is idempotent:
    ``normalize(normalize(x)) == normalize(x)``.

    >>> normalize("ÇANKAYA/ANKARA Kızılay Mah.No:12")
    'çankaya / ankara kızılay mah. no: 12'
    """
    # clean() first: NFKC can turn some symbols into capitals ("\u210c" -> "H"),
    # so lowercasing must come after it.
    return tr_lower(clean(text))
