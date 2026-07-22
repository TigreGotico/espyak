"""Word-translate stress/prefix fixes verified byte-exact against the espeak-ng oracle.

Each case exercises a distinct mechanism in the letter-to-sound / prefix / spelling-stress
path where espyak previously diverged from espeak-ng 1.52:

* ca unpronounceable spelling: SetSpellingStress spells a leading letter and the rule-translated
  remainder is a SEPARATE stress domain, so S_FIRST_PRIMARY (dictionary.c:1321-1328) must NOT
  reduce the remainder's primary across the spelled-prefix boundary (Mgfca -> ˈeməkfkˈa). A `||`
  multi-word dict entry is one domain and is still collapsed by SetWordStress (ccoo).
* de confirm_prefix (translateword.c:341-364): when the suffix-stripped stem still matches a
  prefix, espeak reassigns end_type to the STEM's (possibly shorter) prefix and strips THAT from
  the whole word (umgehen: umge -> um, translate `gehen`), not the original longer prefix.
* it SetLetterVowel(tr,'y') (tr_languages.c:1081): y joins vowel group A so a CACA vowel
  right-context spans a trailing `…Cy`, opening a stressed o to ɔ (montgomery).
"""
import pytest

from espyak.api import G2P


CASES = [
    # ca spelling-stress: remainder primary survives, but || dict entries still collapse
    ("ca", "Mgfca", "ˈeməkfkˈa"),
    ("ca", "Mgfcab", "ˈeməkfkˈap"),
    ("ca", "ccoo", "cumisiˈonz uβɾˌeɾəs"),
    ("ca", "gfca", "kfkˈa"),
    # de confirm_prefix stem-prefix reassignment
    ("de", "umgehen", "ʊmɡˈeːˌən"),
    # de regression guards: prefix genuinely discarded / genuinely kept
    ("de", "unserer", "ˈʊnzərɜ"),
    ("de", "umgang", "ˈʊmɡˌaŋ"),
    # it y-as-vowel opens the stressed o via `o (CACA_ -> O`
    ("it", "montgomery", "montɡˈɔmerɪ"),
    # it regression guards: y-initial and unstressed-o words unchanged
    ("it", "yoga", "jˈɔɡa"),
    ("it", "gomery", "ɡomˈɛrɪ"),
]


@pytest.mark.parametrize("lang,word,expected", CASES)
def test_word_matches_oracle(oracle, lang, word, expected):
    assert G2P(lang, force_compat=True).phonemize(word) == expected
    assert oracle(word, lang, "ipa") == expected
