"""Clause-position stress on prefix words (LOPT_PREFIXES languages).

An unstressed rule prefix (nl be-/ge-/ver-, de ge-/ver-) must not cost the stem
its primary stress when the word is not clause-final: espeak's stem demotion
(translateword.c SetWordStress(stem, 3)) runs only when the prefix carries a
stress mark or the word had dictionary flags, so plain prefix words keep their
lexical primary in any clause position.
"""
import pytest

from espyak.api import G2P

CLAUSE_CASES = [
    # non-final prefix words keep primary stress
    ("nl", "het bestand is opgeslagen", "hət bəstˈɑnt ɪs ˈɔpɣəslˌaːɣən"),
    ("nl", "ik wil dit bericht bewerken", "ɪk ʋɪl dɪt bərˈɪxt bəʋˈɛrkən"),
    ("nl", "we hebben het gevonden vandaag", "ʋə hˌɛbən hət ɣəvˈɔndən vɑndˈaːx"),
    ("de", "ich habe es verstanden heute", "ɪç hɑːbə ɛs fɛɾʃtˈandən hˈɔøtə"),
    # stress-marked prefix still takes the word primary (demotion path intact)
    ("de", "die aufgabe ist wichtig", "diː ˈaʊfɡˌɑːbə ɪst vˈɪçtɪç"),
    # words stressed on the first syllable are unaffected either way
    ("nl", "de nieuwe kamer is klaar", "də nˈiwə kˈaːmər ɪs klˈaːr"),
]

ISOLATED = [
    ("nl", "bestand"),
    ("nl", "bewerken"),
    ("nl", "bericht"),
    ("nl", "gevonden"),
    ("nl", "opgeslagen"),
    ("de", "verstanden"),
    ("de", "aufgabe"),
]


@pytest.mark.parametrize("lang,text,expected", CLAUSE_CASES)
def test_clause_stress(oracle, lang, text, expected):
    assert G2P(lang, force_compat=True).phonemize(text) == expected
    assert expected == oracle(text, lang, "ipa")


@pytest.mark.parametrize("lang,word", ISOLATED)
def test_isolated_word_matches_oracle(oracle, lang, word):
    assert G2P(lang, force_compat=True).phonemize(word) == oracle(word, lang, "ipa")


# A NON-LOPT_PREFIXES language (ro) with a dictionary stress-position flag ($N) on a
# prefix word: espeak assembles prefix+stem into one buffer and runs a single SetWordStress,
# so the $N counts syllables from the WORD start, not the suffix-stripped stem
# (translateword.c:573-576, "stress position affects the whole word, including prefix").
# reacţiona is `reacţiona $3`: primary on the 3rd vowel (o) of the whole word, not the stem
# acţiona's 3rd vowel (its final a).
NONLOPT_PREFIX = [
    ("ro", "reacţiona", "rˌeaktsjˈona"),
    ("ro", "realiza", "rˌealizˈa"),
    ("ro", "reci", "rˈetʃʲ"),  # prefix discarded on the suffix-stripped stem (unchanged)
]


@pytest.mark.parametrize("lang,word,expected", NONLOPT_PREFIX)
def test_nonlopt_prefix_whole_word_stress(oracle, lang, word, expected):
    assert G2P(lang, force_compat=True).phonemize(word) == expected
    assert expected == oracle(word, lang, "ipa")
