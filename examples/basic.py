#!/usr/bin/env python3
"""Basic espyak usage: text -> phonemes.

    python examples/basic.py
"""
from espyak import G2P

# One translator per language — construct once, reuse.
g2p = G2P("en")

for word in ["hello", "world", "read", "phonemes", "2024"]:
    print(f"{word:12} -> {g2p.phonemize(word)}")

# A whole phrase (the last word carries the clause stress).
print()
print("the quick brown fox ->", g2p.phonemize("the quick brown fox"))
