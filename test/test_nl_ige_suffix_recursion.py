"""nl `-ige` SUFX_M stem-recursion bug, verified byte-exact against the espeak-ng oracle.

espeak's `@) ige (_S1m` ending re-translates the stem with want-endings (translateword.c:496-505),
running the rules with FLAG_SUFFIX_REMOVED. For the flags-only dict stems `nadelig`/`nalatig` ($2)
the word-initial rule `_) na (` then wins as a two-letter SUFX_P *prefix* ending: TranslateRules
returns an empty body with `nˈaː` in end_phonemes and SUFX_P set, so espeak's loop drops the stem
body and the word collapses to `nˈaː` + suffix schwa `ə` -> `naːˈə`. See docs/divergences.md
(`nl-ige-suffix-recursion`).

`force_compat=True` reproduces this collapse byte-for-byte; the default engine keeps the full,
linguistically-correct word (the stem is pronounced, `-e` adds a schwa).
"""
import pytest

from espyak.api import G2P


# espeak's buggy force_compat output (the two nl headwords that trigger the collapse)
COMPAT_BUG = [
    ("nadelige", "naːˈə"),
    ("nalatige", "naːˈə"),
]

# the linguistically-correct full word the default engine keeps
DEFAULT_CORRECT = [
    ("nadelige", "naːdˈeːləɣə"),
    ("nalatige", "naːlˈaːtəɣə"),
]

# regression guards: other nl `-ige` / `-ig` words must be UNAFFECTED (identical in both modes),
# including the non-inflected stems, `$N`-dict `-ige` words whose stem is NOT a flags-only `-ig`
# headword, and words sharing the `na`-initial rule but not the trigger.
UNAFFECTED = [
    "nadelig", "nalatig",      # the bare stems: no `-e`, no SUFX_M collapse
    "matige", "gunstige", "statige", "aardige", "machtige", "geldige",
    "nodige", "vorige", "huidige", "vurige", "gierige", "gulzige",
    "genadige", "weldadige", "overige", "dertige", "twintige",
    "zodanige", "volledige", "sommige",   # dict `-ig` stems that do NOT collapse
    "nadat", "natie", "nadruk",           # `na`-initial words with no `-ige` ending
]


@pytest.mark.parametrize("word,expected", COMPAT_BUG)
def test_force_compat_reproduces_stem_collapse(oracle, word, expected):
    assert G2P("nl", force_compat=True).phonemize(word) == expected
    assert oracle(word, "nl", "ipa") == expected


@pytest.mark.parametrize("word,expected", DEFAULT_CORRECT)
def test_default_keeps_full_word(word, expected):
    assert G2P("nl").phonemize(word) == expected


@pytest.mark.parametrize("word", [w for w, _ in COMPAT_BUG])
def test_default_differs_from_force_compat_only_here(word):
    # the collapse is force_compat-only: the two modes must disagree for exactly these words
    assert G2P("nl").phonemize(word) != G2P("nl", force_compat=True).phonemize(word)


@pytest.mark.parametrize("word", UNAFFECTED)
def test_other_ige_words_unaffected(oracle, word):
    compat = G2P("nl", force_compat=True).phonemize(word)
    # no collapse: the stem body survives (output is more than a two-phoneme fragment)
    assert compat == G2P("nl").phonemize(word)
    assert compat == oracle(word, "nl", "ipa")
