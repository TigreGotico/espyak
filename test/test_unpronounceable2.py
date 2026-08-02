"""Unpronouncable2 (translateword.c:1187) parity cases.

For LOPT_UNPRONOUNCABLE==2 languages (en/de/es) the "should this word be spelled out
letter by letter?" decision is NOT the generic first-vowel-depth heuristic but a rerun of
the letter-to-sound rules under FLAG_UNPRON_TEST: only start-anchored rules (RULE_PRE_ATSTART)
may win, an explicit ``$unpron`` marker forces "unpronounceable", and a letter group that
matches no start-anchored rule aborts the whole word (dictionary.c:2270). A word is spelled
iff no start-anchored rule matched (end_flags == 0) or the winner was ``$unpron``.

Byte-exact against espeak-ng 1.52.0. Every case is a genuine adversarial pair:

* PRONOUNCEABLE -> translated by the rules, NOT spelled: en ``st`` matches ``_) st (`` -> "saint";
  de ``strand`` (``str`` cluster) stays whole.
* UNPRONOUNCEABLE -> spelled letter by letter: no start-anchored rule fires, so the word peels.

The regression risk this pins: a consonant-only cluster whose only rule is a NON-anchored plain
letter rule (en ``ph`` -> ``f`` via ``ph f``, or the silent-h ``_B) h``) must still be judged
UNpronounceable and spelled, because that plain rule cannot win under the test flag.
"""
import unicodedata

import pytest

from espyak.api import G2P

# (lang, word, expected_ipa)
CASES = [
    # --- PRONOUNCEABLE: a start-anchored rule matches -> translated, not spelled ---
    ("en", "st", "sˈənt"),          # _) st ( -> "saint"
    ("en", "street", "stɹˈiːt"),    # str cluster stays whole
    ("en", "strong", "stɹˈɒŋ"),
    ("en", "strengths", "stɹˈɛŋθs"),
    ("en", "photo", "fˈəʊtəʊ"),
    ("en", "phone", "fˈəʊn"),
    ("en", "graph", "ɡɹˈaf"),
    ("en", "psychology", "saɪkˈɒlədʒi"),
    ("en", "sphinx", "sfˈɪŋks"),
    ("de", "strand", "ʃtɾˈant"),
    ("de", "pfand", "pfˈant"),
    ("de", "tschechien", "tʃˈɛçɪən"),
    ("es", "dragón", "dɾaɣˈon"),
    ("es", "transporte", "tɾanspˈoɾte"),

    # --- UNPRONOUNCEABLE: no start-anchored rule -> spelled letter by letter ---
    # Consonant clusters whose only 'h'/plain rule is NOT start-anchored: must peel, NOT pronounce.
    ("en", "ph", "pˌiːˈeɪtʃ"),      # not the silent-h 'f'
    ("en", "phx", "pˌiːˌeɪtʃˈɛks"),
    ("en", "phz", "pˌiːˌeɪtʃzˈɛd"),
    ("en", "bh", "bˌiːˈeɪtʃ"),      # not 'b'
    ("en", "sh", "ˌɛsˈeɪtʃ"),       # not 'ʃ'
    ("en", "gh", "dʒˌiːˈeɪtʃ"),     # not 'ɡ'
    ("en", "kh", "kˌeɪˈeɪtʃ"),      # not 'k'
    # Peeled acronyms / vowel-less runs (limiting no-vowel case).
    ("en", "th", "tˌiːˈeɪtʃ"),
    ("en", "sk", "ˌɛskˈeɪ"),
    ("en", "nn", "ˌɛnˈɛn"),
    ("en", "tv", "tˌiːvˈiː"),
    ("en", "nth", "ˌɛntˌiːˈeɪtʃ"),
    ("en", "brrr", "bˌiːˌɑːɹˌɑːɹˈɑː"),
    ("de", "nvda", "(en)ˌɛnvˌiːdˌiːˈeɪ(de)"),
    # $unpron marker: es `_) d ($unpr` forces "dr" to spell despite the atstart 'd' rule.
    ("es", "dr", "dˌeˈɛre"),
    ("es", "d", "dˈe"),
    ("es", "pst", "pˌeˌesetˈe"),
]


@pytest.mark.parametrize("lang,word,expected", CASES)
def test_unpronounceable2(lang, word, expected):
    got = unicodedata.normalize("NFC", G2P(lang).phonemize(word))
    assert got == expected


@pytest.mark.parametrize("lang,word,expected", CASES)
def test_unpronounceable2_matches_oracle(oracle, lang, word, expected):
    got = unicodedata.normalize("NFC", oracle(word + "\n", lang, "ipa"))
    assert got == expected
