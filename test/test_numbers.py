"""Cardinal-number translation vs the espeak-ng oracle (English core)."""
import pytest
from espyak.api import G2P

# cardinal core (NUM_HUNDRED_AND). NUM_THOUSAND_AND ("one million and five"), ordinals,
# decimals/years and the per-language NUM_* variants are not yet modelled.
CASES = ["0", "5", "7", "21", "42", "100", "105", "999",
         "1000", "1234", "1000000", "2000000", "1005000", "13", "19", "80",
         "3.14", "0.5", "2.0", "42.5", "100.25",
         "1st", "2nd", "3rd", "4th", "5th", "8th", "12th", "20th", "21st",
         "30th", "42nd", "100th", "1000th"]


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
