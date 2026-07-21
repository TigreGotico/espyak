"""Cardinal-number translation vs the espeak-ng oracle (English core)."""
import unicodedata

import pytest
from espyak.api import G2P


def _nfc(s):
    return unicodedata.normalize("NFC", s)

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
CY_CARDINAL_CASES = ["1", "2", "9", "10", "11", "12", "15", "16", "18", "19", "100"]


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


# Portuguese: teens, tens and hundreds live in `?N`-gated `_list` entries whose condition prefix
# is glued to the key ("?1_14", "?1_4X", "?1_2C"). The voice's `dictrules 1` sets condition 1,
# so those entries must load AND be selected by the number path (which builds its own lookup
# context). The tens/units connective is NUM_AND_UNITS ("vinte e um"); the thousands use the
# combined `_1M1` "mil" and `_1M2` "um milhão" forms.
PT_CARDINAL_EXACT = {
    "13": "tɹˈezɨ", "14": "kɐtˈorzɨ", "15": "kˈiŋzɨ", "40": "kwɐɾˈeŋtɐ",
    "100": "sˈeɪŋ", "21": "vˈiŋtɨiˈum", "24": "vˈiŋtɨikwˈatɹu",
    "1000": "mˈil", "2000": "dˈoɪʒ mˈil", "1005": "mˈil i sˈiŋku",
    # "um milhão": ũ/ɐ̃/ʊ̃ are base letter + U+0303 combining tilde (espeak's un-normalised form).
    "1000000": "ˈũmiljˈɐ̃ʊ̃",
}


@pytest.fixture(scope="module")
def pt():
    return G2P("pt")


@pytest.mark.parametrize("num,expected", sorted(PT_CARDINAL_EXACT.items()))
def test_portuguese_cardinal_exact(pt, num, expected):
    assert _nfc(pt.phonemize(num)) == _nfc(expected)


@pytest.mark.parametrize("num,expected", sorted(PT_CARDINAL_EXACT.items()))
def test_portuguese_cardinal_matches_oracle(pt, oracle, num, expected):
    assert pt.phonemize(num) == oracle(num, "pt")


@pytest.mark.parametrize("num", ["13", "14", "16", "17", "18", "19", "40", "60", "70", "90"])
def test_portuguese_conditional_number_entries_load(pt, num):
    # These cardinals only exist as condition-gated entries ("?1_14" etc.); before the glued
    # condition prefix parsed correctly they yielded an empty string.
    assert pt.phonemize(num) != ""


def test_portuguese_and_units_connective(pt):
    # NUM_AND_UNITS inserts the "e" (rendered "i") between tens and units: vinte + i + um.
    assert "tɨiˈum" in pt.phonemize("21")  # vˈiŋtɨiˈum
    assert "tɨiˈum" not in pt.phonemize("20")  # plain "vinte" has no connective/unit


def test_portuguese_thousand_omits_um(pt):
    # 1000 is "mil", never "um mil": the combined _1M1 form supersedes value+magnitude.
    out = pt.phonemize("1000")
    assert out == "mˈil"
    assert "um" not in out


def test_portuguese_million_singular_form(pt):
    # 1_000_000 uses the singular _1M2 "um milhão", not the plural _0M2 "milhões".
    assert _nfc(pt.phonemize("1000000")) == _nfc("ˈũmiljˈɐ̃ʊ̃")
    assert "õ" not in _nfc(pt.phonemize("1000000"))  # not the plural "milhões"
