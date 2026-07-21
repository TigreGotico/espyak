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


# A pronounced symbol suffixed to a number ("42%") is not clause punctuation: it is split
# off and spoken AFTER the number, matching espeak's order.
@pytest.mark.parametrize("num", ["42%", "50%", "100%", "0%", "1%",
                                 "3.5%", "1.5%", "0.5%"])
def test_percent_after_number_matches_oracle(en, oracle, num):
    assert en.phonemize(num) == oracle(num, "en")


@pytest.mark.parametrize("num", ["42%", "50%", "3.5%"])
def test_percent_number_not_dropped(en, num):
    """Guard without the oracle: neither the number nor the symbol may vanish."""
    got = en.phonemize(num)
    assert got.strip(), "rendered empty: %r" % num
    assert "s\u02c8\u025bnt" in got, "percent not spoken in %r: %r" % (num, got)


# A lone symbol keeps its ordinary lookup.
def test_lone_percent_matches_oracle(en, oracle):
    assert en.phonemize("%") == oracle("%", "en")
