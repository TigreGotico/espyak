"""Language-switch multi-word grouping (translate.c phonSWITCH + SetTranslator2 re-translate).

When a word is unpronounceable in the current language, espeak-ng switches to the Latin default
voice (English) and re-translates in place on the shared clause buffer, so the SWITCHED language
sees the FOLLOWING source words and its own multi-word dictionary entries consume them as one run.
A Swedish clause containing "has been" switches to English, whose `(has been)` entry joins both
words into a single spaceless unit inside one bracket: `(en)hˈazbiːn(sv)`. Without the grouping,
"been" never even switches (Swedish pronounces it) and the multi-word entry can never fire.

The bracketing espyak emits mirrors espeak's `(lang)…(orig)` phonSWITCH markers. Expected IPA was
captured from the espeak-ng 1.52.0 oracle and is re-checked against the live binary by the
oracle-gated test below.
"""
import pytest

from espyak.api import G2P


@pytest.fixture(scope="module")
def sv():
    return G2P("sv")


# (lang, text, expected_ipa) — espyak output matching espeak-ng 1.52.0 byte-for-byte.
CASES = [
    # the multi-word English `(has been)` entry fires INSIDE the switched run: both source words
    # collapse to hˈazbiːn within one (en)…(sv) bracket.
    ("sv", "has been", "(en)hˈazbiːn(sv)"),
    # a third "been" is NOT part of the 2-word entry, so it falls back to Swedish (bˈeːən).
    ("sv", "has been been", "(en)hˈazbiːn(sv) bˈeːən"),
    # the switched run at clause start, and followed by a native word.
    ("sv", "has been saved", "(en)hˈazbiːn(sv) sˈɑːvəd"),
    # the switched run at clause end (preceded by a native word).
    ("sv", "filen has been", "fˈiːlən (en)hˈazbiːn(sv)"),
    # the run mid-clause, native words on both sides.
    ("sv", "filen has been saved", "fˈiːlən (en)hˈazbiːn(sv) sˈɑːvəd"),
    ("sv", "the file has been saved today",
     "thˈeː fˈiːlə (en)hˈazbiːn(sv) sˈɑːvəd tˈuːdaˌyː"),
    # run immediately followed / preceded by a native Swedish word (idag = "today").
    ("sv", "has been idag", "(en)hˈazbiːn(sv) ˈɪdˌɑːɡ"),
    ("sv", "idag has been", "ˈɪdˌɑːɡ (en)hˈazbiːn(sv)"),
    ("sv", "filen has been saved idag",
     "fˈiːlən (en)hˈazbiːn(sv) sˈɑːvəd ˈɪdˌɑːɡ"),
    # a single foreign word with NO multi-word entry must switch alone and consume nothing.
    ("sv", "computer", "(en)kəmpjˈuːtə(sv)"),
    # a switched word whose following word is pronounceable in the source (keyboard -> Swedish)
    # must NOT swallow it: the run is exactly one word.
    ("sv", "computer keyboard", "(en)kəmpjˈuːtə(sv) ɕˈeːyːbˌuːard"),
]


@pytest.mark.parametrize("lang,text,ipa", CASES)
def test_switch_multiword_group(lang, text, ipa):
    assert G2P(lang).phonemize(text) == ipa


@pytest.mark.parametrize("lang,text,ipa", CASES)
def test_switch_multiword_group_matches_oracle(oracle, lang, text, ipa):
    assert G2P(lang).phonemize(text) == oracle(text, lang, "ipa")
    assert G2P(lang).phonemize(text) == ipa


def test_switched_run_is_one_bracket(sv):
    # the two English words sit inside a SINGLE (en)…(sv) bracket, spaceless as one unit.
    out = sv.phonemize("has been")
    assert out.count("(en)") == 1
    assert out.count("(sv)") == 1
    assert " " not in out


def test_single_foreign_word_unchanged(sv):
    # a lone switched word must render identically whether or not following words exist.
    assert sv.phonemize("computer") == "(en)kəmpjˈuːtə(sv)"
    assert sv.phonemize("computer keyboard").startswith("(en)kəmpjˈuːtə(sv) ")
