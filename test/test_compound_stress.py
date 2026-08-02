"""Compound-word secondary stress and the `_||` compound-join word break.

Three espeak mechanisms, each with an adversarial counter-case so the fix cannot
be a per-word special case:

1. A non-SUFX_T suffix (`&) wood (_S4`, en `wood` value-4 ending) is APPENDED to the
   stem and the whole word is stressed together (translateword.c:525-528 + :578,
   add_suffix_phonemes==0), so a full vowel in the tail keeps its secondary stress
   (hollywood -> hˈɒliwˌʊd). Counter-case: driftwood, whose one-syllable stem leaves
   the tail as the LAST syllable, which the auto-secondary loop never reaches -> no
   secondary (dɹˈɪftwʊd). A SUFX_T suffix (ro unele) is held out and stays unstressed.

2. A `$only`/`$onlys` dict entry must NOT match once a PREFIX was removed
   (LookupDict2:2571). en `put ,pUt $onlys` is skipped for the `out`-prefix-stripped
   stem of `output`, so `put` re-translates via rules to plain `pUt` and the whole
   out+put is stressed once -> ˈaʊtpʊt (not ˈaʊtpˌʊt). Counter-case: `puts`, where the
   's' suffix legitimately selects the $onlys entry.

3. The bare phonPAUSE `_` immediately before a `||` word break swallows the break's
   space (a compound join spelled `_||` in a dict entry: highend hˌaiˈɛnt, bestseller
   bˈɛst̪sˈeller), while a plain `||` join keeps it (nordrhein nˈɔɾt raɪn). A trailing
   length mark on that pause renders nothing (highend's `::` -> no ː). Counter-case:
   spoken-number word breaks are REAL boundaries and keep their space even when a
   pause abuts the break (pl/cs/ru decimals).
"""
import pytest

from espyak.api import G2P

# (lang, word, expected_ipa)
COMPOUND_SECONDARY = [
    ("it", "hollywood", "(en)hˈɒliwˌʊd(it)"),
    ("en", "hollywood", "hˈɒliwˌʊd"),
    ("en", "bollywood", "bˈɒliwˌʊd"),
    # adversarial: one-syllable stem -> tail is the final syllable, no auto-secondary
    ("en", "driftwood", "dɹˈɪftwʊd"),
    # adversarial: SUFX_T suffix held out, stays unstressed
    ("ro", "unele", "ˈunele"),
]

PREFIX_ONLYS = [
    ("en", "output", "ˈaʊtpʊt"),
    ("fr", "output", "(en)ˈaʊtpʊt(fr)"),
    # adversarial: the 's' suffix legitimately picks the $onlys `put` entry
    ("en", "puts", "pˈʊts"),
]

COMPOUND_BREAK = [
    # `_||` compound join: no space
    ("it", "bestseller", "bˈɛst̪sˈeller"),
    ("de", "highend", "hˌaiˈɛnt"),
    # adversarial: plain `||` join keeps the space
    ("de", "nordrhein", "nˈɔɾt raɪn"),
    ("en", "lunchroom", "lˈʌntʃ ɹuːm"),
]

# spoken-number word breaks stay spaced even with a pause abutting the `||`
DECIMAL_SPACING = [
    ("pl", "3,5", "tʃˈɨ pʃɛtɕˈinɛk pʲˈɛɲtɕ"),
    ("cs", "3,5", "tr̝̊ˌi tʃaːrka pjˈet"),
    ("ru", "3,14", "trʲˈi ˈi ʌdʲˈin tʃʲɪtˈyrʲɪdʲɪsʲˈɑtøx"),
]

ALL = COMPOUND_SECONDARY + PREFIX_ONLYS + COMPOUND_BREAK + DECIMAL_SPACING


@pytest.mark.parametrize("lang,word,expected", ALL)
def test_compound_stress_and_break(oracle, lang, word, expected):
    assert G2P(lang, force_compat=True).phonemize(word) == expected
    assert oracle(word, lang, "ipa") == expected
