"""pt `pròs` — reproduce espeak's remove_accent + final-`s` buffer bug under force_compat.

A non-native grave-accented vowel (`ò`) that reaches espeak's remove_accent restart leaves
the buffer malformed so a trailing `-s` RULE_ENDING survives: espeak strips the `-s`,
re-translates the accented stem in isolation, and re-appends `s#`. force_compat reproduces
this byte-for-byte; the DEFAULT engine keeps the linguistically-correct full word.
"""
import unicodedata

import pytest

from espyak.api import G2P


def _nfc(s):
    return unicodedata.normalize("NFC", s)


COMPAT_CASES = [
    ("pt", "pròs", "pɹˈuʃ"),
    ("pt", "tòs", "tˈoʃ"),
]

# Native-accent and plain -s words must be untouched in BOTH modes.
UNAFFECTED = [
    ("pt", "pros"), ("pt", "após"), ("pt", "três"), ("pt", "país"),
    ("pt", "avós"), ("pt", "nós"), ("pt", "livros"), ("pt", "casas"),
    ("es", "anís"), ("es", "vals"), ("ca", "Berlinès"), ("fr", "très"),
]


@pytest.mark.parametrize("lang,word,ipa", COMPAT_CASES)
def test_force_compat_reproduces_bug(oracle, lang, word, ipa):
    assert _nfc(G2P(lang, force_compat=True).phonemize(word)) == ipa
    assert _nfc(G2P(lang, force_compat=True).phonemize(word)) == _nfc(oracle(word + "\n", lang, "ipa"))


def test_default_engine_keeps_correct_vowel():
    # pròs default -> pɹˈʊʃ (= plain `pros`), the linguistically-correct lax vowel.
    assert G2P("pt").phonemize("pròs") == "pɹˈʊʃ"


@pytest.mark.parametrize("lang,word", UNAFFECTED)
def test_native_accent_and_plain_s_unaffected(oracle, lang, word):
    fc = _nfc(G2P(lang, force_compat=True).phonemize(word))
    assert fc == _nfc(oracle(word + "\n", lang, "ipa"))
