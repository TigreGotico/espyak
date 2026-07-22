"""$u (unstressed function/short word) promoted to the clause tonic: stress-conditioned
phoneme programs and voice `replace` directives that key off the vowel's stress must see the
word's NATURAL (un-tonic) level, because espeak-ng runs them BEFORE the intonation nucleus
promotes the chosen syllable's mark to primary.

Two mechanisms are exercised, both verified byte-exact against the espeak-ng 1.52 oracle:

* ru/zle voice `replace 03 a a#`: a word-final `a` in a NON-primary syllable is swapped to
  `a#` (renders `a`). могла is a $u2 dict entry (explicit syllable), so its final vowel is only
  secondary at SetWordStress time; the replace fires there and the later `a`->`ɑ` program is
  defeated. Rendering the word at PRIMARY(4) up front (the old order) would let the replace's
  `>3` guard skip and `a`->`ɑ` win (mʌɡɭˈɑ). Correct: mʌɡɭˈa.

* sd `i:` phoneme program `IF thisPh(isUnstressed) THEN ChangePhoneme(i)`: the long vowel
  shortens while unstressed and is only then promoted to the clause tonic (ٿي -> tʰˈi). Sindhi
  opts into this ordering (`unstress_u_nucleus`); most languages instead promote a $u nucleus to
  full stress BEFORE the program runs, so their stressed nucleus vowel keeps its full form — the
  bg guards below (nˈa, not nˈɐ) and ru `для` (dɭʲˈɑ) pin that majority behaviour.
"""
import pytest

from espyak.api import G2P


CASES = [
    # ru voice-replace re-evaluation at natural stress ($u2 nucleus)
    ("ru", "могла", "mʌɡɭˈa"),
    ("ru", "смогла", "smʌɡɭˈa"),
    ("ru", "побыла", "pʌbyɭˈa"),
    # sd stress-conditioned length reduction at natural stress (plain $u nucleus)
    ("sd", "ٿي", "tʰˈi"),
    # --- regression guards: languages that PROMOTE a $u nucleus before its program runs ---
    # bg keeps the stressed `a` full (a->ɐ only when unstressed), so the nucleus stays `a`
    ("bg", "на", "nˈa"),
    ("bg", "за", "zˈa"),
    ("bg", "заради", "zarˈadiː"),
    ("bg", "окажа", "okˈaʒɐ"),
    # ru promotes plain $u words to full stress (no unstress_u_nucleus); для keeps ˈɑ
    ("ru", "для", "dɭʲˈɑ"),
    # a plain $u monosyllable whose vowel has no stress-conditioned program is unchanged
    ("ht", "mwen", "mwˈen"),
    ("fr", "quoique", "kwˈak"),
]


@pytest.mark.parametrize("lang,word,expected", CASES)
def test_u_nucleus_matches_oracle(oracle, lang, word, expected):
    assert G2P(lang).phonemize(word) == expected
    assert oracle(word + "\n", lang, "ipa") == expected
