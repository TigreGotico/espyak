"""Clause punctuation attached to a word must not be spoken.

espeak's clause reader (readclause.c) consumes `. , ; : ! ?` and the bracket/quote
pairs before a token reaches dictionary lookup. espyak split on whitespace only, so
the punctuation stayed glued to the word, missed the dictionary and fell through to
the letter rules -- which spell the symbol out ("yes." -> jes+dot).
"""
import pytest

from espyak.api import G2P


@pytest.fixture(scope="module")
def en():
    return G2P("en")


# Trailing clause punctuation: silent in every case.
TRAILING = ["yes.", "yes,", "yes;", "yes:", "yes!", "yes?", "yes...",
            "(yes)", '"yes"', "yes)", "(yes"]


@pytest.mark.parametrize("text", TRAILING)
def test_trailing_punctuation_matches_oracle(en, oracle, text):
    assert en.phonemize(text) == oracle(text, "en")


@pytest.mark.parametrize("text", TRAILING)
def test_trailing_punctuation_not_spoken(en, text):
    """Guard that runs without the oracle binary: no punctuation name may appear."""
    got = en.phonemize(text)
    for spelled in ("d\u0252t", "k\u0259\u028al\u0259n", "k\u02c8\u0259\u028al\u0259n",
                    "k\u02cc\u0259\u028al\u0259n", "k\u0252m\u0259",
                    "\u026akskl\u0259m\u02cce\u026a\u0283\u0259n",
                    "kw\u02c8\u025bst\u0283\u0259n"):
        assert spelled not in got, "punctuation spoken in %r: %r" % (text, got)


# A punctuation character STANDING ALONE keeps its normal behaviour: espeak speaks the
# ones that have a name (`:` colon, `%` percent, `&` and) and stays silent for the pure
# clause terminators (`.` `,` -> '').
@pytest.mark.parametrize("text", [".", ",", ";", "!", "?", ":", "%", "&"])
def test_lone_punctuation_matches_oracle(en, oracle, text):
    assert en.phonemize(text) == oracle(text, "en")


# Sentences: every word survives and no symbol name is inserted. Compared word-wise --
# espeak emits a newline at a clause break, espyak's tokenizer only knows word breaks.
SENTENCES = [
    ("en", "yes."),
    ("en", "one. two. three."),
    ("en", "Warning: disk full"),
    ("en", "stop! go?"),
    ("en", "First item, second item, third item"),
    ("nl", "Weet je het zeker?"),
]


@pytest.mark.parametrize("lang,text", SENTENCES)
def test_sentence_words_match_oracle(oracle, lang, text):
    assert G2P(lang).phonemize(text).split() == oracle(text, lang).split()


# Abbreviations rely on their interior dots and must NOT be split apart.
@pytest.mark.parametrize("text", ["e.g.", "U.S.A.", "Mr.", "i.e."])
def test_dotted_abbreviations_still_work(en, oracle, text):
    assert en.phonemize(text) == oracle(text, "en")


# An apostrophe inside a word is part of the word, not boundary punctuation.
@pytest.mark.parametrize("text", ["don't", "it's", "O'Brien"])
def test_internal_apostrophe_preserved(en, oracle, text):
    assert en.phonemize(text) == oracle(text, "en")


# The apostrophe is not blanket clause punctuation: it can be part of the word. A quote
# apostrophe around a word peels (en 'hello'), but a word-final one that makes a dictionary
# headword stays (eo `l'` is the _list entry for "la"), and a word-internal one always stays
# (en don't, fr l'eau). qu strips its boundary apostrophe via strip_boundary_apostrophe.
APOSTROPHE_CASES = [
    ("en", "'hello'", "həlˈəʊ"),
    ("en", "don't", "dˈəʊnt"),
    ("en", "'tis", "tˈɪz"),
    ("eo", "l'", "lˈa"),
    ("eo", "dank'", "dˈank"),
    ("fr", "l'eau", "lˈo"),
    ("qu", "k'", "kˈaː"),
]


@pytest.mark.parametrize("lang,text,ipa", APOSTROPHE_CASES)
def test_apostrophe_word_vs_quote(lang, text, ipa):
    import unicodedata
    assert unicodedata.normalize("NFC", G2P(lang, force_compat=True).phonemize(text)) == ipa
