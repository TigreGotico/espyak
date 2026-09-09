"""A symbol with a spoken name is its own word.

espeak's clause reader isolates such a symbol, so "#1" reads "hash one" and "a@b"
reads "a at b". espyak kept it glued to its neighbours, so the token missed the
dictionary and rendered as nothing, or the symbol was silently swallowed.
"""
import pytest

from espyak.api import G2P


@pytest.fixture(scope="module")
def en():
    return G2P("en")


@pytest.fixture(scope="module")
def nl():
    return G2P("nl")


# Symbols English names. Each must survive and be spoken as a separate word.
# "x"/"b" rather than "a": a lone "a" is the article, which espeak reduces to ɐ while
# espyak spells the letter name (ˈeɪ) -- a separate clause-stress issue, not symbol
# isolation. Compared word-wise since espeak sometimes emits a double space at a break.
EN_CASES = ["#1", "#42", "x@b", "user@host", "x&b", "x=y", "1/2", "x*b"]


@pytest.mark.parametrize("text", EN_CASES)
def test_english_symbol_is_its_own_word(en, oracle, text):
    assert en.phonemize(text).split() == oracle(text, "en").split()


@pytest.mark.parametrize("text", EN_CASES)
def test_english_symbol_token_not_dropped(en, text):
    """Guard without the oracle: the token must not render as nothing."""
    assert en.phonemize(text).strip(), "rendered empty: %r" % text


# Dutch names a wider set (£, €, °, +) than English does, so the isolation must be
# per-language rather than a fixed table.
NL_CASES = ["#1", "x@b", "20\u00b0", "\u00a35", "5+3", "x=y", "1/2", "x&b"]


@pytest.mark.parametrize("text", NL_CASES)
def test_dutch_symbol_is_its_own_word(nl, oracle, text):
    assert nl.phonemize(text).split() == oracle(text, "nl").split()


@pytest.mark.parametrize("text", NL_CASES)
def test_dutch_symbol_token_not_dropped(nl, text):
    assert nl.phonemize(text).strip(), "rendered empty: %r" % text


# Regression: the existing '/' handling must keep working.
@pytest.mark.parametrize("lang,text", [("en", "1/2"), ("nl", "1/2"), ("en", "x/b")])
def test_slash_still_isolated(oracle, lang, text):
    assert G2P(lang).phonemize(text).split() == oracle(text, lang).split()
