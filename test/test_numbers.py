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


# Dutch: units before tens ("tweeenveertig"), bare honderd/duizend, and a single primary
# accent at the front of a compound numeral. Without the language flags these came out as
# "veertigtwee" with a primary on every part.
NL_CASES = ["0", "5", "13", "20", "21", "42", "80", "99",
            "100", "105", "200", "999", "1000", "1005", "1234"]


@pytest.fixture(scope="module")
def nl():
    return G2P("nl")


@pytest.mark.parametrize("num", NL_CASES)
def test_dutch_cardinal_matches_oracle(nl, oracle, num):
    assert nl.phonemize(num) == oracle(num, "nl")


@pytest.mark.parametrize("num,expect_first", [("42", "tʋ"), ("21", "ˈeː"), ("99", "nˈeː")])
def test_dutch_swap_tens(nl, num, expect_first):
    """Guard without the oracle: the unit is spoken BEFORE the ten."""
    assert nl.phonemize(num).startswith(expect_first), nl.phonemize(num)


@pytest.mark.parametrize("num", ["42", "99", "200", "999", "1234"])
def test_dutch_single_primary_accent(nl, num):
    """A compound numeral carries exactly one primary accent."""
    assert nl.phonemize(num).count("\u02c8") == 1, nl.phonemize(num)


# Catalan and Aragonese follow the Spanish pattern; both were wrong before the flags.
CA_CASES = ["5", "20", "21", "42", "99", "100", "105", "200", "1000", "1005", "1234"]


@pytest.mark.parametrize("num", CA_CASES)
def test_catalan_cardinal_matches_oracle(oracle, num):
    assert G2P("ca").phonemize(num) == oracle(num, "ca")


@pytest.mark.parametrize("num", CA_CASES)
def test_aragonese_cardinal_matches_oracle(oracle, num):
    assert G2P("an").phonemize(num) == oracle(num, "an")
