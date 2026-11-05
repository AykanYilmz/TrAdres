"""TrAdres: parse, normalize and validate Turkish addresses.

>>> from tradres import parse
>>> address = parse("ataturk mh 23nisan cd no 5 d 3 bolu merkez")
>>> address.il, address.mahalle, address.cadde
('Bolu', 'Atatürk', '23 Nisan')
>>> address.format()
'Atatürk Mah. 23 Nisan Cad. No:5 D:3 Merkez/Bolu'
>>> address.confidence > 0.9
True
"""

from importlib.metadata import PackageNotFoundError, version

from tradres.matching import MatchConfig
from tradres.models import Address
from tradres.normalization import normalize
from tradres.parser import parse

try:
    __version__ = version("tradres")
except PackageNotFoundError:  # pragma: no cover - only when running from a raw checkout
    __version__ = "0.0.0"

__all__ = ["Address", "MatchConfig", "__version__", "normalize", "parse"]
