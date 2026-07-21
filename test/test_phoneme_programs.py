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
# A predicate that points at a neighbour (nextPh/prevPh/next2Ph...) must evaluate a
# position-relative feature (isWordEnd, isFinalVowel, ...) against THAT phoneme's own
# position, not thisPh's. The tr `e` phoneme opens to `&` (æ) before a word-final
# rhotic/nasal/lateral: `ben` -> `bˈæn` relies on `nextPh(isWordEnd)` being true for the
# word-final `n`. A word-internal `e` before the same nasal but NOT at word end keeps its
# mid quality (`beni` -> the first e stays ɛ), so the feature must be genuinely
# position-sensitive, not a blanket "always word-end".
TR_WORD_END_CASES = [
    ("ben", "bˈæn"),      # e -> & : next phoneme (n) is word-final nasal
    ("sen", "sˈæn"),
    ("eln", "ˈæln"),      # e -> & : next phoneme (l) is a lateral, next2 (n) in-word
    ("beni", "benˈɪ"),    # e stays mid (ɛ): the n after it is NOT word-final
]


def test_next_ph_is_word_end():
    g = G2P("tr", force_compat=True)
    for word, ipa in TR_WORD_END_CASES:
        assert g.phonemize(word) == ipa, word
