"""Multi-word `(w1 w2 ...)` dictionary-entry matching (LookupDict2 skipwords path).

English joins entries like `(has-been)` / `(has been)` into a single pronunciation unit that
spans several source words (has been -> hˈazbiːn). espeak-ng compiles such an entry to a key
("has") plus a stored follow-string ("been ") and matches it against the words that FOLLOW in
the clause; a hyphen inside the parentheses is a word separator, so `(has-been)` and
`(has been)` compile alike. The expected IPA below was captured from the espeak-ng 1.52.0
oracle and is re-verified against the live binary by the oracle-gated tests.
"""
import pytest

from espyak.api import G2P


@pytest.fixture(scope="module")
def en():
    return G2P("en")


# (text, expected_ipa) — espyak output that MATCHES espeak-ng 1.52.0 exactly.
JOINED = [
    ("has been",                "hˈazbiːn"),
    ("has-been",                "hˈazbiːn"),
    ("Has been",                "hˈazbiːn"),            # capital initial still joins
    ("the file has been saved", "ðə fˈaɪl hˈazbiːn sˈeɪvd"),
    ("that has been saved",     "ðɐthɐzbˌɪn sˈeɪvd"),   # 3-word `(that has been)` entry wins
    ("wind up the toy",         "wˈaɪnd ˈʌp ðə tˈɔɪ"),
    ("no one knows",            "nˈəʊwˈɒn nˈəʊz"),
    ("of the world",            "ɒvðə wˈɜːld"),
    ("lean-to shed",            "lˈiːn tuː ʃˈɛd"),
    ("tae kwon do class",       "tˈaɪkwɒndˈəʊ klˈas"),
    ("wall st station",         "wˈɔːlstɹˌiːt stˈeɪʃən"),
]


@pytest.mark.parametrize("text,ipa", JOINED)
def test_multiword_join(en, text, ipa):
    assert en.phonemize(text) == ipa


@pytest.mark.parametrize("text,ipa", JOINED)
def test_multiword_join_matches_oracle(oracle, en, text, ipa):
    assert en.phonemize(text) == oracle(text, "en", "ipa")
    assert en.phonemize(text) == ipa


def test_has_been_is_one_unit(en):
    # the two source words collapse to a single spaceless token (no word break inside the unit)
    assert " " not in en.phonemize("has been")


def test_multiword_only_fires_at_whole_word_boundary(en):
    # "beenish" is not the follow-word "been": the multi-word entry must NOT fire, so the two
    # words stay separate (a raw prefix match would wrongly glue "has been..." here).
    out = en.phonemize("has beenish")
    assert " " in out
    assert "iːnɪʃ" in out


def test_multiword_needs_a_space_between_words(en):
    # a single glued token "hasbeen" is one word for the rules, never the multi-word entry.
    out = en.phonemize("hasbeen")
    assert " " not in out
    assert out == "hˈasbiːn"


def test_allcaps_does_not_drop_following_word(en):
    # all-caps HAS selects the $allcaps single-word `has` entry (not `(has-been)`), so BEEN must
    # still be rendered as its own word rather than silently skipped.
    out = en.phonemize("IT HAS BEEN")
    assert out.count(" ") == 2          # three spelled/spoken words
    assert out.endswith("iːn")          # "been" present at the end


def test_atend_multiword_gated_by_clause_position(en):
    # `(has to) $atend` only applies at clause end; with "go" following it must NOT fire, so
    # there is no glued "haztuː" unit — the words translate separately.
    out = en.phonemize("has to go")
    assert "haztuː" not in out
    assert out.count(" ") == 2


@pytest.mark.parametrize("text", ["it has", "it was", "has been", "no one"])
def test_atend_and_join_match_oracle(oracle, en, text):
    assert en.phonemize(text) == oracle(text, "en", "ipa")
