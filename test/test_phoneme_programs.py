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


# The Malayalam k/t/p phonemes voice to g/d/b at word end only when NOT the first
# vowel of the word (ph_malayalam), where isFirstVowel means CountVowelPosition==1
# (synthdata.c:454/635) - i.e. it also holds for a consonant after the 1st vowel.
# The chillu letter names `_ik` (single vowel i then final k) must keep k, not voice
# to g, because the k counts one preceding vowel so isFirstVowel is true there.
ML_VOICING_CASES = [
    ("ൿ", "ˈik"),   # U+0D7F chillu-k, name `_ik`
    ("കൎ", "ˈik"),  # ka + unofficial chillu virama, same `_ik` name
]


@pytest.mark.parametrize("word,ipa", ML_VOICING_CASES)
def test_ml_letter_name_no_final_voicing(oracle, word, ipa):
    g = G2P("ml", force_compat=True)
    assert g.phonemize(word) == ipa
    assert g.phonemize(word) == oracle(word, "ml", "ipa")
