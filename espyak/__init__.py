"""espyak — pure-Python reimplementation of espeak-ng's grapheme-to-phoneme engine.

Public entrypoint:

    >>> from espyak import G2P
    >>> G2P("en").phonemize("hello world")
    'həlˈəʊ wˈɜːld'
"""
from espyak.api import G2P

__all__ = ["G2P"]
