"""CJK / pinyin parity: Pyash (py) digit-letters and Mandarin (cmn) compat-ideograph keys.

Expected values are from espeak-ng 1.52.0 (`-q --ipa`, stdin + trailing newline), force_compat.

Two mechanisms are pinned here:

* Pyash `.replace`: the LAST `.replace` section in `py_rules` wins (`InitGroups`,
  dictionary.c:147, overwrites `replace_chars` per RULE_REPLACEMENTS group), so `2 u`/`7 i`
  are live but the earlier `6 @` is discarded. Those replacements run in the clause reader
  BEFORE any digit-split or number path (translate.c:784), so a mapped digit is a letter by
  the time tokenisation happens: `la2 -> lˈau`, `kla2t -> klˈaut`, `2X -> ˈux`. An unmapped
  digit (`6`) stays a digit — `6` matches its `6 @` dict entry (`ˈə`) and `t6` splits.

* Mandarin CJK compatibility ideographs (U+F900–U+FAFF): espeak keys the dict on raw
  codepoints, so a compat entry (都 U+FA26 `du1`, 識 U+F9FC `shi2`) stays distinct from
  the unified char (都 U+90FD `dou1`, 識 U+8B58 `shi5`). NFC-normalising the key would
  merge them and, as the later entry, corrupt the unified char's pronunciation.
"""
import pytest

from espyak.api import G2P

PY_CASES = [
    ("6", "ˈə"),         # bare digit -> `6 @` dict entry, NOT the `_6 hlis` number form
    ("t6", "t ˈə"),      # unmapped digit splits from the preceding letter
    ("n6", "n ˈə"),
    ("la2", "lˈau"),     # `.replace 2 u` runs before the digit-split -> one syllable
    ("kla2t", "klˈaut"),
    ("2X", "ˈux"),
    ("2", "ˈu"),
    ("hao3", "hˈao tjˈin"),
    ("ma1", "ma hjˈik"),
]

CMN_CASES = [
    (chr(0x90FD), "tˈou5"),   # 都 U+90FD -> dou1 (cmn_list), not the U+FA26 compat `du1`
    (chr(0x8B58), "s.i.1"),   # 識 U+8B58 -> shi5 (neutral), not the U+F9FC compat `shi2`
    (chr(0x8258), "sˈou5"),   # 艘
    (chr(0x5934), "thˈouɜ"),  # 头
    (chr(0x5589), "χˈouɜ"),   # 喉
]


@pytest.mark.parametrize("lang,cases", [("py", PY_CASES), ("cmn", CMN_CASES)])
def test_cjk_pinyin_parity(oracle, lang, cases):
    g = G2P(lang)
    for word, ipa in cases:
        assert g.phonemize(word) == ipa
        assert g.phonemize(word) == oracle(word + "\n", lang, "ipa")


def test_py_last_replace_section_wins():
    # py_rules has two `.replace` sections; only the last (`7 i`, `2 u`) survives — the first
    # (`6 @`) is dropped, exactly as InitGroups overwrites replace_chars per group.
    reps = dict(G2P("py")._rules.replacements)
    assert reps == {"7": "i", "2": "u"}


def test_cmn_compat_ideograph_key_is_distinct():
    # The compat ideograph must not pollute the unified char's dict bucket.
    g = G2P("cmn")
    assert g.phonemize(chr(0x90FD)) == "tˈou5"   # 都 unified -> dou1
    assert g.phonemize(chr(0xFA26)) == "tˈu5"    # 都 compat -> its own du1
