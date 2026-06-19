#!/usr/bin/env python3
"""The same idea across many languages and scripts.

    python examples/multilingual.py

espyak bundles 117 languages — Latin, Cyrillic, Greek, Indic, Arabic, Hebrew, Korean,
Armenian, and more. Construct a G2P per language code.
"""
from espyak import G2P

SAMPLES = [
    ("en", "hello"),
    ("es", "buenos días"),
    ("de", "straße"),
    ("fr", "bonjour"),
    ("pt", "obrigado"),
    ("ru", "привет"),
    ("el", "καλημέρα"),
    ("hi", "नमस्ते"),
    ("ar", "مرحبا"),
    ("he", "שלום"),
    ("ko", "안녕하세요"),
    ("hy", "բարև"),
]

for lang, text in SAMPLES:
    try:
        out = G2P(lang).phonemize(text)
    except Exception as exc:  # unknown voice code, etc.
        out = f"<error: {exc}>"
    print(f"{lang:4} {text:14} -> {out}")
