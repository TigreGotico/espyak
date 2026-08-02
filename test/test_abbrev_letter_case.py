"""Abbreviation / letter-name / dotted-abbrev / dict-key-case parity cases.

Byte-exact against espeak-ng 1.52.0. These pin three mechanisms that the headword
audit surfaced:

* ``$text`` abbreviation expansion folds only a LEADING capital of the replacement
  (es ``aprox`` -> ``Aproximadamente``), never a medial one (mt ``$textmode`` entries
  whose value carries a medial capital render nothing, matching espeak).
* CheckDottedAbbrev spells a lone ``<letter>.`` token as its letter name (es ``d.``).
* Dict keys are bucketed by case: a lowercase whole-word lookup never borrows an
  uppercase-keyed entry (ca ``t`` vs Greek ``T``; en ``lbs`` vs ``LBS``).
"""
import unicodedata

import pytest

from espyak.api import G2P

# (lang, word, expected_ipa)
CASES = [
    # $text abbreviation expansion — leading capital of the replacement is folded.
    ("es", "aprox", "ˌapɾoksimˈaðamˈente"),
    ("es", "ej", "exˈemplo"),
    # CheckDottedAbbrev: a single letter followed by a dot spells its letter name.
    ("es", "d.", "dˈe"),
    ("es", "d. c", "dˈe θˈe"),
    # Medial capital in a $textmode replacement is NOT folded -> word yields nothing.
    ("mt", "cm", ""),
    ("mt", "eċċ", ""),
    # ...but all-lowercase $textmode replacements still expand.
    ("mt", "km", "kˌiːlomˈetɹɪ"),
    # Case-bucketed dict keys: lowercase query must not match an uppercase-keyed entry.
    ("ca", "t", "tˈe"),        # not the Greek `T t'Eta` (theta)
    ("ca", "st", "ˌesətˈe"),
    ("en", "lbs", "pˈaʊndz"),  # not the uppercase `LBS $abbrev` (spelled letters)
    # Uppercase queries still reach the uppercase/all-caps spelling path.
    ("en", "LBS", "ˌɛlbˌiːˈɛs"),
    ("en", "USA", "jˌuːˌɛsˈeɪ"),
    # Regression guards: $text replacements that were already lowercase are unchanged.
    ("de", "matthias", "matˈiːɑːs"),
    ("de", "jonathan", "jˈoːnatˌɑːn"),
    # fo geminating uppercase letter names still bucket by case.
    ("fo", "l", "ˈɛl"),
    ("fo", "L", "ˈɛll"),
]


@pytest.mark.parametrize("lang,word,expected", CASES)
def test_abbrev_letter_case(lang, word, expected):
    g = G2P(lang, force_compat=True)
    assert unicodedata.normalize("NFC", g.phonemize(word)) == expected


@pytest.mark.parametrize("lang,word,expected", CASES)
def test_abbrev_letter_case_matches_oracle(oracle, lang, word, expected):
    got = unicodedata.normalize("NFC", oracle(word + "\n", lang, "ipa"))
    assert got == expected


# An all-uppercase dict key compiles with an implicit $allcaps (compiledict.c:601-617), so it
# only matches an all-caps source word; a first-capital key (pt Braille, ?2 Gmail) carries no
# case flag and is just the lowercase entry.
ALLCAPS_KEY_CASES = [
    ("en", "lbs", "pˈaʊndz"),      # lowercase entry wins; the LBS $abbrev key needs all-caps
    ("en", "LBS", "ˌɛlbˌiːˈɛs"),   # all-caps LBS spells out
    ("pt", "Braille", "bːɹˈailɨ"), # first-capital key: lowercase entry matches
    ("pt", "braille", "bːɹˈailɨ"),
    ("pt", "Gmail", "ɡˌemˈeɪl"),
    ("fo", "l", "ˈɛl"),
    ("fo", "L", "ˈɛll"),           # all-caps key geminates
]


@pytest.mark.parametrize("lang,word,ipa", ALLCAPS_KEY_CASES)
def test_allcaps_key_case_matching(oracle, lang, word, ipa):
    g = G2P(lang, force_compat=True)
    assert unicodedata.normalize("NFC", g.phonemize(word)) == ipa
    assert unicodedata.normalize("NFC", oracle(word + "\n", lang, "ipa")) == ipa
