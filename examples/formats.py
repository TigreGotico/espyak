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

# force_compat: True (default) = bit-identical to espeak-ng, bugs included.
#               False          = opt into the documented fixes in docs/divergences.md.
print()
print("force_compat=True  ", G2P("en", force_compat=True).phonemize(word))
print("force_compat=False ", G2P("en", force_compat=False).phonemize(word))
