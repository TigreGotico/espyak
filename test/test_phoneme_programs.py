"""Phoneme-program (P1b) tests: context-dependent ChangePhoneme.

These cases only pass once the phoneme-program interpreter runs between the matcher
output and the renderer (English linking-r r->r/, Spanish intervocalic spirantization
d->ð / b->β / g->ɣ). Verified vs espeak-ng 1.52.0.
"""
import pytest

from espyak.api import G2P

EN_CASES = [
    ("car", "kˈɑː"),
    ("for", "fˈɔː"),
    ("here", "hˈiə"),
    ("water", "wˈɔːtə"),
    ("world", "wˈɜːld"),
]

ES_CASES = [
    ("lado", "lˈaðo"),
    ("cada", "kˈaða"),
    ("agua", "ˈaɣwa"),
    ("bardem", "baɾðˈem"),
    ("freedom", "fɾˈiðom"),
    ("google", "ɡˈuɣəl"),
]


@pytest.mark.parametrize("lang,cases", [("en", EN_CASES), ("es", ES_CASES)])
def test_phoneme_programs(oracle, lang, cases):
    g = G2P(lang)
    for word, ipa in cases:
        assert g.phonemize(word) == ipa
        assert g.phonemize(word) == oracle(word, lang, "ipa")
