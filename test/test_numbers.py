"""Cardinal-number translation vs the espeak-ng oracle (English core)."""
import pytest
from espyak.api import G2P

# cardinal core (NUM_HUNDRED_AND). NUM_THOUSAND_AND ("one million and five"), ordinals,
# decimals/years and the per-language NUM_* variants are not yet modelled.
CASES = ["0", "5", "7", "21", "42", "100", "105", "999",
         "1000", "1234", "1000000", "2000000", "1005000", "13", "19", "80"]


@pytest.fixture(scope="module")
def en():
    return G2P("en")


@pytest.mark.parametrize("num", CASES)
def test_cardinal_matches_oracle(en, oracle, num):
    assert en.phonemize(num) == oracle(num, "en")
