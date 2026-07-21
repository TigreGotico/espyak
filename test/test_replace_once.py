"""The `.replace` table (SubstituteChar, translate.c:784) runs exactly ONCE per word,
at clause tokenisation, so a non-idempotent table must not cascade.

Sindarin maps `x`->`cs` and `ch`->`x`; applying the table twice would turn ch->x->cs
(ach -> ˈaks). espeak applies it once, so ch->x stays x and the x group gives χ.
"""
import pytest

from espyak.api import G2P

SJN_CASES = [
    ("ach", "ˈaχ"),      # ch -> x -> χ  (must NOT cascade to cs -> ks)
    ("nach", "nˈaχ"),
]


@pytest.mark.parametrize("word,ipa", SJN_CASES)
def test_sjn_replace_not_cascaded(oracle, word, ipa):
    g = G2P("sjn", force_compat=True)
    assert g.phonemize(word) == ipa
    assert g.phonemize(word) == oracle(word, "sjn", "ipa")
