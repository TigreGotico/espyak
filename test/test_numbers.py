"""Cardinal-number translation vs the espeak-ng oracle (English core)."""
import pytest
from espyak.api import G2P

# cardinal core (NUM_HUNDRED_AND). NUM_THOUSAND_AND ("one million and five"), ordinals,
# decimals/years and the per-language NUM_* variants are not yet modelled.
CASES = ["0", "5", "7", "21", "42", "100", "105", "999",
         "1000", "1234", "1000000", "2000000", "1005000", "13", "19", "80",
         "3.14", "0.5", "2.0", "42.5", "100.25",
         "1st", "2nd", "3rd", "4th", "5th", "8th", "12th", "20th", "21st",
         "30th", "42nd", "100th", "1000th",
         "1005", "2034", "1234567"]  # thousand-and


@pytest.fixture(scope="module")
def en():
    return G2P("en")


@pytest.mark.parametrize("num", CASES)
def test_cardinal_matches_oracle(en, oracle, num):
    assert en.phonemize(num) == oracle(num, "en")


# German: NUM_SWAP_TENS (units-and-tens) + the _Na "ein"-before-magnitude form
DE_CASES = ["5", "21", "35", "99", "100", "105", "1000", "1234"]


@pytest.fixture(scope="module")
def de():
    return G2P("de")


@pytest.mark.parametrize("num", DE_CASES)
def test_german_cardinal_matches_oracle(de, oracle, num):
    assert de.phonemize(num) == oracle(num, "de")


# Spanish: lexicalised hundreds (cien/ciento/doscientos), exact tens (veinte), "mil".
# Compound tens+units (21, 31) need NUM_SINGLE_STRESS reassignment — not yet modelled.
ES_CASES = ["5", "20", "30", "100", "105", "200", "300", "500", "1000"]


@pytest.fixture(scope="module")
def es():
    return G2P("es")


@pytest.mark.parametrize("num", ES_CASES)
def test_spanish_cardinal_matches_oracle(es, oracle, num):
    assert es.phonemize(num) == oracle(num, "es")


# Decimal-fraction reading is per-language (the NUM_DFRACTION_* bits). Digit-by-digit languages
# (nl/de/sv/da/el/an, and ru with its "и"…"десятых" frame) spell each fraction digit; the
# whole-cardinal languages (fr/es/it/pt/ro/pl/cs/fi/tr/ca) read the fraction as one number when it
# is short enough. These probes are byte-exact against the oracle across both readings.
DFRACTION_CASES = [
    ("sv", "3,14"), ("sv", "0,5"), ("sv", "12,345"), ("sv", "0,05"), ("sv", "100,25"),
    ("da", "3,14"), ("da", "0,5"), ("da", "12,345"), ("da", "0,05"), ("da", "7,7"),
    ("an", "3,14"), ("an", "0,5"), ("an", "12,345"), ("an", "0,05"), ("an", "100,25"),
    ("ru", "3,14"), ("ru", "0,5"), ("ru", "12,345"), ("ru", "0,05"), ("ru", "0,123"),
    ("it", "3,14"), ("it", "0,5"), ("it", "12,345"), ("it", "0,05"), ("it", "2,0"),
    ("ca", "3,14"), ("ca", "0,5"), ("ca", "0,05"), ("ca", "100,25"), ("ca", "0,123"),
    ("ro", "3,14"), ("ro", "0,5"), ("ro", "0,05"), ("ro", "2,0"), ("ro", "7,7"),
    ("el", "0,5"), ("el", "12,345"), ("el", "0,05"), ("el", "2,0"), ("el", "0,123"),
]


@pytest.mark.parametrize("lang,num", DFRACTION_CASES)
def test_decimal_fraction_matches_oracle(oracle, lang, num):
    assert G2P(lang).phonemize(num) == oracle(num, lang)


# Welsh counts in tens: 20 = "dau ddeg", 42 = "pedwar deg dau" (tens fragment before the unit),
# and the teens are "deg" + unit with no dedicated _10.._19 entries. 100 drops the leading "un".
CY_CARDINAL_CASES = ["1", "2", "9", "10", "11", "12", "15", "16", "18", "19", "100",
                     # the tens 20-99 embed "deg" (10) as a secondary-stressed component; its
                     # explicit long vowel eː must survive (ðˌeːɡ, not the reduced ðˌɛɡ) because
                     # the number fragments come from the `_list` dictionary (SFLAG_DICTIONARY),
                     # which exempts them from the ChangeIfNotStressed(E) reduction.
                     "20", "22", "23", "30", "40", "42", "50", "55", "60", "66",
                     "70", "77", "80", "88", "90", "99"]


@pytest.fixture(scope="module")
def cy():
    return G2P("cy")


@pytest.mark.parametrize("num", CY_CARDINAL_CASES)
def test_welsh_cardinal_matches_oracle(cy, oracle, num):
    assert cy.phonemize(num) == oracle(num, "cy")


@pytest.mark.parametrize("num,unit_core", [("42", "aɨ"), ("55", "øm"), ("23", "iː")])
def test_welsh_tens_precede_units(cy, num, unit_core):
    # The tens word ("pedwar deg", "dau ddeg", …) comes before the unit — regression guard against
    # the units-first ordering.
    out = cy.phonemize(num)
    assert "ðˌ" in out  # the "deg" tens marker is present
    assert out.index("ðˌ") < out.rindex(unit_core)


@pytest.mark.parametrize("num", ["20", "42", "60", "99"])
def test_welsh_tens_component_keeps_long_vowel(cy, num):
    # The tens "deg" (10) is only secondary-stressed inside the compound, but its long eː must
    # not be reduced to ɛ: number fragments are dictionary-sourced, so ChangeIfNotStressed(E)
    # does not fire on them (StressCondition control&1 / SFLAG_DICTIONARY).
    out = cy.phonemize(num)
    assert "ðˌeːɡ" in out
    assert "ðˌɛɡ" not in out


@pytest.mark.parametrize("word,expected", [
    # `e (d`->e: must win over the `e (CC` / `e (C` consonant-group rules — that only happens
    # once SetLetterVowel(w) removes `w` from the consonant group, so `pedwar` (e+d+w) matches
    # `e (d` not `e (CC`. Regression guard for the long-vowel rule-scoring fix.
    ("pedwar", "pˈeːdwar"),
    ("deg", "dˈeːɡ"),
    ("peth", "pˈeːθ"),
    ("pedwar deg dau", "pˈeːdwar dˈeːɡ dˈaɨ"),
])
def test_welsh_word_long_vowel(cy, oracle, word, expected):
    assert cy.phonemize(word) == expected
    assert cy.phonemize(word) == oracle(word, "cy")


@pytest.mark.parametrize("word", ["wrth", "hwn", "hwnnw", "shwd", "rhwng"])
def test_welsh_w_words_pronounced_not_spelled(cy, oracle, word):
    # With `w` a vowel (SetLetterVowel), a w-initial/w-medial word still has a vowel nucleus and
    # must be pronounced, not spelled letter-by-letter. Guards the pronounceability check against
    # forgetting that set_letter_vowel letters count as vowels.
    out = cy.phonemize(word)
    assert out == oracle(word, "cy")
    # a spelled-out word produces one stress mark per letter name; a pronounced one has a single
    # primary and no spurious per-letter secondaries.
    assert out.count("ˈ") == 1 and "ˌ" not in out
