"""Pilot-language end-to-end tests (eo, es) — validates multilingual config.

Expected values from espeak-ng 1.52.0; re-verified vs the live binary.
"""
import pytest

from espyak.api import G2P

EO_CASES = [
    ('anst', 'anstˈataʊ'),
    ('apud', 'ˈapud'),
    ('post', 'pˈost'),
    ('plej', 'plˈeɪ'),
    ('ilia', 'ilˈia'),
    ('miaj', 'mˈiaɪ'),
    ('ciaj', 'tsˈiaɪ'),
    ('liaj', 'lˈiaɪ'),
    ('niaj', 'nˈiaɪ'),
    ('viaj', 'vˈiaɪ'),
    ('iliaj', 'ilˈiaɪ'),
    ('siaj', 'sˈiaɪ'),
    ('esti', 'ˈesti'),
    ('estas', 'ˈestas'),
    ('estis', 'ˈestis'),
    ('estos', 'ˈestos'),
    ('estus', 'ˈestus'),
    ('povas', 'pˈovas'),
]

ES_CASES = [
    ('nuestro', 'nwˈestɾo'),
    ('nuestros', 'nwˈestɾos'),
    ('nuestra', 'nwˈestɾa'),
    ('nuestras', 'nwˈestɾas'),
    ('vuestro', 'bwˈestɾo'),
    ('vuestros', 'bwˈestɾos'),
    ('vuestra', 'bwˈestɾa'),
    ('vuestras', 'bwˈestɾas'),
    ('tras', 'tɾˈas'),
    ('ante', 'ˈante'),
    ('para', 'pˈaɾa'),
    ('entre', 'ˈɛntɾe'),
    ('sobre', 'sˈoβɾe'),
    ('bajo', 'bˈaxo'),
    ('desde', 'dˈesðe'),
    ('hasta', 'ˈasta'),
    ('hacia', 'ˈaθja'),
    ('aunque', 'ˈaʊnke'),
]

@pytest.mark.parametrize("lang,cases", [("eo", EO_CASES), ("es", ES_CASES)])
def test_pilot_language(oracle, lang, cases):
    g = G2P(lang)
    for word, ipa in cases:
        assert g.phonemize(word) == ipa
        assert g.phonemize(word) == oracle(word, lang, "ipa")


# Icelandic letter groups: group B (LETTERGP_B) is overridden to the voiceless consonants,
# so `B) n -> hn#` (pre-aspirated n) fires only after a voiceless letter, not after voiced g;
# group F=kpst and H=jvr are re-set after ResetLetterBits(0x18); group C stays the default
# all-consonants set so the `e (CC` vowel-shortening rule still matches across a gn cluster.
IS_CASES = [
    ("vegna", "ʋˈɛɡna"),    # no hn# leak after g; ɛ stays short before the cluster
    ("gegnum", "ɟˈɛɡnym"),
    ("varðst", "ʋˈarðsd"),  # ð stays voiced before s
    ("afn", "ˈabhn#"),      # hn# DOES fire: n after voiceless f
    ("akn", "ˈaɡhn#"),      # hn# after voiceless k
]


def test_icelandic_letter_groups(oracle):
    g = G2P("is", force_compat=True)
    for word, ipa in IS_CASES:
        assert g.phonemize(word) == ipa, word


# A lengthened vowel that carries an explicit `ipa` string is rendered by REPEATING that
# string, not by appending ː: espeak writes the length phoneme with the vowel's own plist
# (dictionary.c:656) and in IPA mode re-runs the vowel's program, emitting its ipa a second
# time. This holds for the CLOSING diphthong eI (ipa ɛɪ) just as for monophthongs and
# centring diphthongs — af `charmaine`/`cliché` copy ɛɪ -> ɛɪɛɪ. A vowel with NO ipa string
# (the closing diphthong aI defines none) instead takes ː. The copy is gated on the vowel
# actually being lengthened AND carrying an explicit ipa string.
AF_LENGTHEN_CASES = [
    ("charmaine", "ʃɑːmˈɛɪɛɪn"),   # lengthened closing diphthong eI (ipa ɛɪ) copied, not ɛɪː
    ("cliché", "kliʃˈɛɪɛɪ"),       # same, word-final
    ("brei", "brˈɛɪ"),             # unlengthened eI stays single (no spurious copy)
    ("baan", "bˈɑːn"),             # ordinary long vowel unaffected by the copy path
]


def test_afrikaans_lengthened_vowel_copy(oracle):
    g = G2P("af", force_compat=True)
    for word, ipa in AF_LENGTHEN_CASES:
        assert g.phonemize(word) == ipa, word
        assert oracle(word, "af", "ipa") == ipa, word
