"""Equal-score rule tie-break by compiled phoneme CODE (compiledict.c string_sorter).

When two letter-to-sound rules match a letter group at the SAME score, espeak's
MatchRule keeps the last one in the group's compiled order (dictionary.c `points >= best`).
`output_rule_group` sorts each group by `string_sorter`, whose key is the rule's COMPILED
phoneme-code bytes (EncodePhonemes output) — the phoneme-table indices, not the mnemonic
ASCII. So the equal scorer whose phoneme codes sort LAST wins.

`blokade` is the witness. At the `o`, two rules tie at 82 points:

    bl) o (k+      -> ?V      (da_rules: `blokere`, a literal bl_o_k rule)
    L03) o (L01a+  -> ?o      (da_rules: `lokale`,  L03 _o_ L01+a rule)

`?o` and `?V` are SINGLE glottalised-vowel phonemes in the `da` table, with real
CompilePhoneme codes 124 and 109. Because 109 < 124, the `?V` rule sorts before the `?o`
rule, so `?o` wins the last-best-wins tie: blokade -> blʔokˈaaðə (not blʔʌkˈaaðə). A
table-insertion-order proxy for the codes inverts the pair and picks `?V`; the fix keys the
sort on espeak's real phoneme codes (PhonemeSource.codes).

`blok` (no `a` after the `k`, so the `?o` rule fails to match) keeps `?V` -> blˈʔʌk,
confirming the difference is the tie-break, not a blanket `o`->o remapping.
"""
import unicodedata

import pytest

from espyak.api import G2P

CASES = [
    # (lang, word, expected_ipa)
    ("da", "blokade", "blʔokˈaaðə"),  # ?o wins the 82-point tie (real code 124 > 109)
    ("da", "blok", "blˈʔʌk"),         # the ?o rule can't match here -> ?V, contrast case
]


@pytest.mark.parametrize("lang,word,expected", CASES)
def test_forced_compat_matches_oracle(oracle, lang, word, expected):
    g = G2P(lang, force_compat=True)
    got = unicodedata.normalize("NFC", g.phonemize(word))
    assert got == expected
    assert got == unicodedata.normalize("NFC", oracle(word, lang, "ipa"))


@pytest.mark.parametrize("lang,word,expected", CASES)
def test_default_engine_matches(lang, word, expected):
    # the tie-break is a pure ordering mechanism, independent of force_compat.
    got = unicodedata.normalize("NFC", G2P(lang).phonemize(word))
    assert got == expected
