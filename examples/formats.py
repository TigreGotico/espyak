#!/usr/bin/env python3
"""Output formats: IPA vs Kirshenbaum, separators and ties.

    python examples/formats.py
"""
from espyak import G2P

g2p = G2P("en")
word = "phonemes"

print("IPA (default)      ", g2p.phonemize(word))
print("Kirshenbaum (-x)   ", g2p.phonemize(word, ipa=False))
print("separator '_'      ", g2p.phonemize(word, separator="_"))
print("tie '͡'           ", g2p.phonemize(word, tie="͡"))
