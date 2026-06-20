# Code review: `espyak/dictionary.py` vs `dictionary.c`

Clean-room verification of `espyak/dictionary.py` against the espeak-ng C source it ports
(`oracle/espeak-ng/src/libespeak-ng/dictionary.c`, espeak-ng 1.52.0). This module is the
letter-to-sound core: the rule-scoring state machine (`MatchRule`), the per-word driver
(`TranslateRules`), dictionary selection (`LookupDict2`/`LookupDictList`/`LookupFlags`),
the stress algorithms (`SetWordStress` + `GetVowelStress`), `RemoveEnding`, and the
`=`/`''` priority-stress handling.

Every C-reference comment in the Python was checked against the cited C line; the ones that
matter are confirmed accurate (see the per-function notes). Line numbers below are
`dictionary.py` (PY) and `dictionary.c` (C).

---

## 1. Function / algorithm correspondence map

| Python (dictionary.py) | C (dictionary.c) | Notes |
|---|---|---|
| `Translator.is_letter` (PY 177) | `IsLetter` (C 770) | letter_bits / remove_accent / letter_groups override |
| `Translator.is_vowel` (PY 198) | `IsVowel` (C 797) | thin wrapper, group `LETTERGP_VOWEL2` |
| `_is_letter_group` (PY 1733) | `IsLetterGroup` (C 702) | `.Lnn` utf-8 string lists; **longest-match** (see §6) |
| `count_vowels` + `_append` (PY 475, 1675) | `AppendPhonemes` (C 1444) | vowel/stressed counting for `@`/`&` rules |
| `MnemIndex.tokenize` (PY 517) | (no direct C; equiv. of phoneme-code stream walk) | greedy mnemonic split |
| `get_vowel_stress` (PY 581) | `GetVowelStress` (C 802) | STRESSPOSN bookkeeping + `=`/`''` |
| `set_word_stress` (PY 647) | `SetWordStress` (C 919) | the STRESSPOSN_* switch + auto-secondary |
| `_compute_weights` (PY 1018) | weight loop inside SetWordStress (C 1002-1026) | heavy/light syllables |
| `match_rule` (PY 1073) | `MatchRule` (C 1484) | rule scoring state machine |
| `_match_post` (PY 1200) | `case RULE_POST:` (C 1651) | post-context rule elements |
| `_match_pre` (PY 1352) | `case RULE_PRE:` (C 1856) | pre-context rule elements |
| `_dollar_rule` (PY 1460) | RULE_DOLLAR arms + `DollarRule` (C 1721/1923/3027) | `$w_alt`/`$p_alt`/`$list`/`$noprefix`/`$unpron` |
| `_apply_replacements` (PY 1496) | `SubstituteChar` (translate.c:784) | `.replace` table (cross-file) |
| `_unpronounceable` (PY 1534) | `Unpronouncable` (translateword.c:1114) | cross-file; no-vowel subset only |
| `translate_rules` (PY 1559) | `TranslateRules` (C 2080) | group dispatch + endings + retranslation |
| `remove_ending` (PY 1686) | `RemoveEnding` (C 2901) | suffix removal + y→i / e-restore |
| `DictList.lookup` / `_eval` (PY 347, 400) | `LookupDict2` (C 2430) | entry selection + flag/condition checks |
| `DictList.lookup_flags` (PY 385) | `LookupFlags` (C 2888) | flags-only lookup |
| `DictList` abbrev/suffix retries — **not in this module** | `LookupDictList` (C 2720) | see §7 (UNIMPLEMENTED) |

`STRESS_IS_*` levels (PY 550-555) match `synthesize.h` 309-314 exactly
(DIMINISHED 0, UNSTRESSED 1, NOT_STRESSED 2, SECONDARY 3, PRIMARY 4, PRIORITY 5).
`phonSTRESS_PREV == 8` (C `phoneme.h:206`); in PY the `=` mnemonic stands in for it.

---

## 2. MatchRule scoring — line-by-line (PY `match_rule` + `_match_post` + `_match_pre`)

espeak's points are an integer that selects the winning rule via **last-best-wins**
(`>=`), so any off-by-one silently swaps phonemes. Each scoring arm verified:

### Loop scaffolding
| element | C | PY | verdict |
|---|---|---|---|
| init `match.points = 1` | C 1559 | PY 1096 `points = 1` | OK |
| `distance_left = -2`, `distance_right = -6` | C 1551-1552 | PY 1089-1090 | OK |
| consume-letter (`match_type==0`) +21, only if `(letter&0xc0)!=0x80` | C 1644-1647 | PY 1138-1141 | OK |
| `REPLACED_E`/`'e'` equivalence | C 1644 | PY 1138 | OK |
| POST `distance_right += 6`, clamp `>18 -> 19` | C 1653-1655 | PY 1145-1147 | OK |
| PRE `distance_left += 2`, clamp `>18 -> 19` | C 1858-1860 | PY 1162-1164 | OK |
| end-of-stream => `failed = 2` (matched) | C 1576/1588/1609 | PY 1104-1105 | OK (see §5 RULE_PHONEMES) |
| `failed==2 && unpron_ignore==0` accept | C 2037 | PY 1180 | OK |
| `check_atstart`: require `pre_ptr[-1]==' '`, then `+4` | C 2039-2041 | PY 1181-1183 | OK |
| `points >= best.points` (last-best-wins) | C 2044 | PY 1184 | OK |
| `total_consumed += group_length`; min 1 | C 2069-2071 | PY 1191-1193 | OK |
| `best.points==0 -> phonemes=""` | C 2075-2076 | PY 1195-1196 | OK |
| group-length>1 `+35` bonus | C 2185 (in TranslateRules) | PY 1616 (in translate_rules) | OK — applied in driver, not MatchRule (the C 2057 `+35` is trace-only) |

### POST arms (`_match_post`, PY 1200)
| rule byte | C points | PY points | verdict |
|---|---|---|---|
| RULE_LETTERGP | `lg_pts(20, or 19 if grp==2) - distance_right` (C 1671-1674) | PY 1208-1211 | OK |
| RULE_LETTERGP2 | `20 - distance_right` (C 1682) | PY 1219 | OK |
| RULE_NOTVOWEL | `20 - distance_right`; FLAG_SUFFIX_VOWEL space-fail (C 1688-1694) | PY 1223-1228 | OK |
| RULE_DIGIT | `20 - distance_right` (C 1697-1699) | PY 1229-1232 | OK; **tone_numbers branch absent** (see §3 POTENTIAL-BUG-1) |
| RULE_NONALPHA | `21 - distance_right` (C 1709) | PY 1237 | OK |
| RULE_DOUBLE | `21 - distance_right` (C 1716) | PY 1252 | OK |
| RULE_DOLLAR | see §4 | PY 1256-1259 | DOLLAR_UNPR diff (justified, §4) |
| `'-'` | `22 - distance_right`; FLAG_HYPHEN_AFTER (C 1743-1744) | PY 1260-1262 | OK |
| RULE_SYLLABLE | `18 + syllable_count - distance_right` (C 1769) | PY 1280-1281 | OK |
| RULE_NOVOWELS | `19 - distance_right` (C 1785) | PY 1296 | OK |
| RULE_INC_SCORE | `+20`, `post_ptr--` (C 1806-1808) | PY 1297-1299 | OK |
| RULE_DEC_SCORE | `-20`, `post_ptr--` (C 1810-1812) | PY 1300-1302 | OK |
| RULE_ENDING | `end_type` decode + LOPT_SUFFIX guard (C 1823-1834) | PY 1305-1314 | OK |
| RULE_NO_SUFFIX | `+1`, `post_ptr--`; FLAG_SUFFIX_REMOVED fail (C 1837-1843) | PY 1315-1320 | OK |
| RULE_SKIPCHARS `(J` | scan to target/LETTERGP2 (C 1788-1804) | PY 1321-1342 | OK (see §6 note) |
| RULE_DEL_FWD | find next `'e'`, mark del_fwd (C 1814-1822) | PY 1303-1304 `pass` | UNIMPLEMENTED (§3 POTENTIAL-BUG-2) |
| RULE_SPELLING `'W'` | not a distinct C POST arm | PY 1241-1249 | added feature, scoped to spelling mode (justified, §6) |
| default literal byte | `21 - distance_right` if not utf8-cont (C 1846-1850) | PY 1343-1348 | OK |

### PRE arms (`_match_pre`, PY 1352)
| rule byte | C points | PY points | verdict |
|---|---|---|---|
| RULE_LETTERGP | `lg_pts - distance_left` (C 1881) | PY 1362 | OK |
| RULE_LETTERGP2 | `20 - distance_right` (**uses distance_right, a C quirk**, C 1889) | PY 1370 `20 - distance_right` | OK — quirk faithfully reproduced |
| RULE_NOTVOWEL | `20 - distance_left` (C 1897) | PY 1376 | OK |
| RULE_DOUBLE | `21 - distance_left` (C 1904) | PY 1383 | OK |
| RULE_DIGIT | `21 - distance_left` (C 1911) | PY 1388 | OK |
| RULE_NONALPHA | `21 - distance_right` (**C quirk**, C 1918) | PY 1394 `21 - distance_right` | OK — quirk reproduced |
| RULE_DOLLAR | only `$list`/`$p_alt` (`(cmd&0xf0)==0x20`) in PRE (C 1926) | PY 1398-1402 | mostly OK (see §4 POTENTIAL-BUG-4: `post_ptr` ref) |
| RULE_SYLLABLE | `18 + syllable_count - distance_left` (C 1938) | PY 1409 | OK |
| RULE_STRESSED | `+19` (C 1945) | PY 1415 | OK |
| RULE_NOVOWELS | `+3` (C 1960) | PY 1443 | OK |
| RULE_IFVERB | `+1` (C 1966) | PY 1421 | OK |
| RULE_CAPITAL | `+1` (C 1973) | PY 1427 | OK |
| `'.'` (dot-before) | `+50` (C 1977-1986) | — | UNIMPLEMENTED (§3 POTENTIAL-BUG-3) |
| `'-'` | `22 - distance_right`; FLAG_HYPHEN (C 1989-1990) | PY 1444-1446 | OK |
| RULE_SKIPCHARS `J)` | scan backwards (C 1995-2016) | — | UNIMPLEMENTED (§7) |
| default: `RULE_SPACE -> +4`, else `21 - distance_left` (C 2019-2025) | PY 1449-1455 | OK |

`_letter_group_no` (PY 1066) ports `LetterGroupNo` (`g = *p - 'A'; if (g < 0) g += 256`).
Matches.

---

## 3. POTENTIAL-BUG deviations (flagged prominently)

> These could change emitted phonemes. None is in the core scoring arithmetic of common
> languages, but each is a real divergence from the C and is listed for a maintainer to
> confirm against the parity audit.

### POTENTIAL-BUG-1 — RULE_DIGIT `tone_numbers` post branch dropped (POST), and the missing PRE tone_numbers
- **C ref:** `dictionary.c:1700-1704` (POST RULE_DIGIT): when `langopts.tone_numbers` is
  set, a `D` post-rule matches **even with no digit present** (`add_points = 20-distance_right; post_ptr--`).
- **PY:** `_match_post` RULE_DIGIT (PY 1229-1234) only matches a real digit; no
  `tone_numbers` fallback. Same for the top-of-`translate_rules` digit dispatch — the
  `IsDigit(wc) && (tone_numbers==0 || !any_alpha)` guard (C 2146) is approximated by
  "try rules first, then number-name" (PY 1585-1598), not the exact C gate.
- **Effect:** tonal languages whose `.group` rules use a trailing `D` post-rule to match a
  syllable lacking an explicit tone digit could score that rule differently (wrong tone /
  dropped phoneme). Affects `cmn`/`yue`/`vi`/`th` style tone-number tables. Verify whether
  any active rule depends on the no-digit-D match; if none does in the shipped tables this
  is harmless, but it is a genuine omission of a scoring path.

### POTENTIAL-BUG-2 — RULE_DEL_FWD not implemented
- **C ref:** `dictionary.c:1814-1822` + `2322-2323` (`*match1.del_fwd = REPLACED_E`).
  The rule finds the next `'e'` in the post-context and, on the winning match, rewrites it
  to `REPLACED_E` so a later group treats it as already-consumed (English silent-e logic,
  e.g. `…e…e` words).
- **PY:** `_match_post` RULE_DEL_FWD is `pass` (PY 1303-1304); `del_fwd` is carried but
  `translate_rules` never applies it.
- **Effect:** English (and any lang using `//`-style del-fwd rules) words relying on the
  forward-e deletion get the un-rewritten letter re-translated, possibly emitting a spurious
  vowel. The inline comment calls it "rare; English 'e' replacement". Confirm against the
  English parity set — flagged because it is a silently-skipped instruction, not a documented
  force_compat divergence.

### POTENTIAL-BUG-3 — PRE `'.'` (dot-before) rule not implemented
- **C ref:** `dictionary.c:1977-1986`: a `.` in the pre-context scans backward for any `.`
  earlier in the word and, if found, adds **+50** (a very large score) — used for
  abbreviation / decimal handling.
- **PY:** no `'.'` arm in `_match_pre`; it falls through to the `default` literal-byte case
  (PY 1449), which only matches a literal `.` byte at exactly the previous position and
  scores `21-distance_left`, not +50, and does not scan backward.
- **Effect:** any rule using `.` in the pre-context (abbreviation tables, some number rules)
  scores ~29 points lower and loses to competing rules. Languages with dotted-abbreviation
  rules affected. Flagged: this changes the winning rule, not just a tie.

### POTENTIAL-BUG-4 — PRE RULE_DOLLAR passes `post_ptr` (undefined in `_match_pre`)
- **C ref:** `dictionary.c:1923-1929` (PRE RULE_DOLLAR → `DollarRule`).
- **PY:** `_match_pre` RULE_DOLLAR (PY 1398-1402) calls
  `_dollar_rule(tr, command, word_flags, dict_flags, buf, post_ptr)` — but `_match_pre` has
  **no `post_ptr` parameter or local**. If this arm is ever reached for a `$list`/`$p_alt`
  in a PRE context it raises `NameError`. (`_match_post` correctly passes its own
  `post_ptr`.) The `$list`/`$p_alt` part-word lookup in `_dollar_rule` needs `part_end`;
  with a NameError it would crash rather than mis-score.
- **Effect:** crash (not wrong-phoneme) for any language with a `$list`/`$p_alt`/`$NN` dollar
  command inside a **pre**-context rule. Likely currently unreached (pre-context dollar rules
  are rare), but it is a latent bug, not a divergence — a maintainer should replace
  `post_ptr` with `pre_ptr` (or the correct part-end index) to match the C.

### POTENTIAL-BUG-5 (design divergence) — priority-stress demotion gated to `pt` only
- **C ref:** `dictionary.c:891-907` — the `max_stress == STRESS_IS_PRIORITY` block runs
  **unconditionally inside `GetVowelStress`** for every language: a `''` priority marker
  replaces every other primary (→ UNSTRESSED if `S_PRIORITY_STRESS`, else SECONDARY), then
  the priority vowel becomes the sole primary.
- **PY:** this block lives in `set_word_stress` (PY 670-686) behind
  `tr.priority_stress_demote`, which is enabled **only for `pt`** (`language_data.py:225`).
  The PY `get_vowel_stress` does NOT perform the demotion; it only computes `max_stress`.
- **Effect:** any language **other than pt** that has a `''` (priority) marker in a dict
  entry will keep its other primary markers instead of demoting them — potentially two
  primary stresses where espeak emits one. `da` is named in the PY 130-131 comment as the
  reconciliation case still in flux. Classified here as a deliberate, documented
  force_compat-style gating (the comment explains the `=`-interaction reason), so it is a
  *known* divergence rather than an accidental bug — but it is the single largest behavioural
  gap from the C in this module and is called out so the parity audit owner can track which
  non-pt languages with `''` entries are affected.

---

## 4. RULE_DOLLAR / DollarRule — detail

| command | C (MatchRule + DollarRule) | PY `_dollar_rule` | verdict |
|---|---|---|---|
| `$unpron` (DOLLAR_UNPR) | sets `match.end_type = SUFX_UNPRON` (C 1724-1725) | returns `(0,0)`, no end_type (PY 1468-1469) | JUSTIFIED — TranslateRules strips `SUFX_UNPRON` (`end_type &= ~SUFX_UNPRON`, C 2306 / PY 1661) before use, so output-equivalent |
| `$noprefix` (DOLLAR_NOPREFIX) | fail if FLAG_PREFIX_REMOVED else `+1` (C 1726-1730) | PY 1464-1467 | OK |
| `$w_alt` `(cmd&0xf0)==0x10` | gate on whole-word dict `$alt` flag, `+23` (C 1731-1736) | PY 1470-1473 | OK |
| `$p_alt` / `$list` `(cmd&0xf0)==0x20 || ==DOLLAR_LIST` | `DollarRule`: build part-word `word_start-1 .. consumed+group_length`, `LookupFlags`, `+23` if FOUND (& !ONLY for $list) or matching `$alt` bit (C 1737-1739, 3027-3043) | PY 1474-1492 | OK in spirit; **part-word slice differs**: PY uses `buf[2:part_end]` where `part_end = post_ptr-1` (PY 1257), C uses `*word - word_start + consumed + group_length + 1`. For suffix rules (`part == whole word`) equivalent; for mid-word matches both approximate the consumed-so-far prefix. Output-equivalent on the cited da cases; JUSTIFIED |

`DollarRule`'s `(flags[0] & (1<<(BITNUM_FLAG_ALT+cmd&0xf)))` ordering: C checks the
`DOLLAR_LIST`/FOUND case first then the `$alt` bit (C 3037-3040); PY splits into a
`DOLLAR_LIST` branch then a `$p_alt` branch (PY 1486-1492). Equivalent.

---

## 5. RULE_PHONEMES / RULE_PH_COMMON / "common phonemes" — divergence

- **C ref:** `dictionary.c:1576-1613`. In the compiled byte stream a rule body can be `0`
  (use the previous `RULE_PH_COMMON` group's phonemes), `RULE_PHONEMES` (phonemes follow
  inline), or `RULE_PH_COMMON` (record common phonemes for following rules).
- **PY:** `match_rule` keeps a `common_phonemes = None` local (PY 1081) and the comment at
  PY 1131 states "RULE_PHONEMES / RULE_PH_COMMON / RULE_LINENUM not present in prog". This is
  because `rule_compiler` already attaches each rule's phoneme string to `cr.phonemes`
  (PY uses `best.phonemes = cr.phonemes`, PY 1186), so the byte-stream phoneme/common
  machinery is resolved at compile time rather than at match time.
- **Verdict:** JUSTIFIED — output-equivalent representation change. Confirm only that
  `rule_compiler` correctly propagates `RULE_PH_COMMON` to the rules that carry `0` bodies
  (out of scope for this file; noted as a cross-module dependency).

`RULE_CONDITION` (`?N`/`?!N`) IS handled at match time (PY 1121-1130, C 1614-1630): `>=32`
means "fail if set", else "fail if not set", `+1` on success. Matches exactly.

---

## 6. IsLetter / IsLetterGroup / helpers

- **`is_letter` (PY 177 ↔ C 770):** `letter_groups[group]` wchar override first, then
  `group>7 -> 0`, then `letter_bits_offset` remap, then the `0xc0..N_REMOVE_ACCENT`
  accented-base inheritance (`remove_accent[letter-0xc0]`), then the `letter_bits` lookup.
  Order and semantics match. One ordering nuance: C checks `letter_groups[group] != NULL`
  **before** the `group>7` guard (so a group≥8 with a non-NULL override would be honored);
  PY guards `group < 8` on the override (PY 179) **and** returns 0 for `group>7` (PY 181).
  In practice only groups 0-7 ever get a `letter_groups` override, so output-equivalent.
  JUSTIFIED.
- **`_is_letter_group` (PY 1733 ↔ `IsLetterGroup` C 702):** C returns the **first** matching
  group string (iterates list order, returns on first full match); PY returns the **longest**
  match (PY comment 1737-1739). espeak stores `.Lnn` members longest-first in the compiled
  data, so C's first-match == longest-match in practice; PY makes that explicit. The `~`
  (empty / `RULE_GROUP_END`) handling: C returns 0 when `~` is hit; PY tracks `has_null` and
  returns 0 only if no longer literal matched. Output-equivalent. JUSTIFIED.
  - Pre-rule length semantics: C returns `len` (the group string length) for `pre`; PY
    returns `best` (the matched byte length) and the caller does `pre_ptr -= (n_bytes-1)`.
    Equivalent for single-codepoint and multi-byte members.
- **RULE_SPELLING `'W'` (PY 1241-1249):** an espeak feature (zero-width spelling-mode
  assertion). PY adds it as a POST arm scoped to `tr._spelling`. Present in espeak's rule
  set; reproduced faithfully. JUSTIFIED.
- **`count_vowels` (PY 475) ↔ `AppendPhonemes` (C 1444):** `phSTRESS` with `std_length<4`
  sets `unstress_mark`; `phVOWEL` not `phUNSTRESSED` and not unstress-marked increments
  `word_stressed_count`, always increments `word_vowel_count`. Matches C 1462-1477 exactly.
  PY skips `|` barrier and whitespace (extra, harmless). JUSTIFIED.

---

## 7. UNIMPLEMENTED C features (not ported)

| C feature | C ref | who it affects | category |
|---|---|---|---|
| `tone_numbers` no-digit RULE_DIGIT match (POST) | C 1700-1704 | tonal langs (cmn/yue/vi/th tables) | POTENTIAL-BUG-1 (§3) |
| RULE_DEL_FWD forward-`e` deletion | C 1814-1822, 2322 | en (silent-e), any del-fwd rule | POTENTIAL-BUG-2 (§3) |
| PRE `'.'` dot-before (+50) | C 1977-1986 | abbreviation / dotted rules | POTENTIAL-BUG-3 (§3) |
| PRE RULE_SKIPCHARS `J)` (backward skip) | C 1995-2016 | lv-style backward suffix skip | UNIMPLEMENTED — POST `(J` is ported (PY 1321), the PRE `J)` is not; affects langs using backward skip in pre-context |
| `phonSYLLABIC` syllabic-consonant counting | C 868-874, 1384 | langs with explicit `phonSYLLABIC` (cs/sl syllabic r/l, some Indic) | UNIMPLEMENTED — PY handles `_nonsyllabic_before_vowel` (yue ng) but not the generic `phcode == phonSYLLABIC` "previous consonant is a syllable nucleus" count in get_vowel_stress / set_word_stress output loop |
| `vowel_pause` word-initial PAUSE insert | C 1366-1373 | langs with `langopts.vowel_pause & 0x30` (e.g. de glottal stop) | UNIMPLEMENTED — PY set_word_stress omits the leading `phonPAUSE_NOLINK`/`phonPAUSE_VSHORT` |
| `STRESSPOSN_ALL` (mark all stressed) | C 1188-1193 | langs with stress_rule ALL | UNIMPLEMENTED — no PY switch arm; falls through to no-op (only auto-secondary runs) |
| `STRESSPOSN_GREENLANDIC` (kl) | C 1194-1221 | `kl` | UNIMPLEMENTED — no PY arm |
| `S_FINAL_LONG` (final long-vowel stress) | C 1075-1079 | langs with S_FINAL_LONG flag | UNIMPLEMENTED — PY STRESSPOSN_2R omits the `vowel_length[n-1] > vowel_length[n-2]` final-stress shift |
| S_FINAL_SPANISH per-lang `an`/`ia` + `-ns` default | C 1060-1071 | `an` (Aragonese), `ia` (Interlingua), the generic `-ns`-keeps-penult default | PARTIAL — PY (PY 728-732) implements the `ca`/`es` "not s/n, or preceded-by-consonant" form but not the `an`/`ia` branches nor the C default arm's `phNASAL` `-ns` special-case. Affects an/ia and any lang hitting the default S_FINAL_SPANISH arm |
| `LookupDictList` abbrev (`a.b.c`), MAX3 repeat, FLAG_SUFX_E_ADDED / SUFX_D re-lookups, FLAG_ACCENT letter fallback chain | C 2720-2852 | abbreviations, repeated-word capping, suffix-stripped re-lookup | UNIMPLEMENTED in this module — `DictList.lookup` ports `LookupDict2` selection only; the surrounding `LookupDictList` retry logic lives elsewhere or is not ported. `FLAG_ACCENT` is partially handled via `_last_accent` (PY 380-382) |
| LookupDict2 `FLAG_ALT2_TRANS` hu-specific, `expect_verb_s`, `prev_dict_flags` en-`to` verb-`s` suppression, FLAG_NATIVE translator-switch | C 2616-2647 | hu, en verb forms after "to", translator-switched words | UNIMPLEMENTED — PY `_eval` checks the simple VERB/PAST/NOUN/CAPITAL/ALLCAPS/DOT/ATEND/ATSTART/SENTENCE/STEM conditions (PY 425-444) but not the en/hu-specific extra gates. Affects en verb-after-"to" and hu alt-trans |
| TranslateRules language-switch (`phonSWITCH`/`%cen`), bracket pauses, dieresis re-translate | C 2210-2262, 2297-2301 | non-Latin→Latin fallback, bracketed words | PARTIAL — PY does accent-removal re-translate (PY 1635-1647) and FLAG_SPELLWORD (PY 1648-1654) but not the `phonSWITCH` language switch, bracket pauses, or `LOPT_DIERESES` path. Noted in PY docstring 1566 |

---

## 8. JUSTIFIED deviations (Python idiom / output-equivalent / documented)

| deviation | C ref | justification |
|---|---|---|
| phoneme stream as mnemonic **strings**, not byte codes | throughout C (`phoneme_tab[phcode]`) | PY works on mnemonic strings + a `MnemIndex`; greedy longest-match tokenize reproduces the byte-code walk. The `_BARRIER` `|` and `_LITERAL_DIGITS` (PY 22-32) keep otherwise-droppable tokens alive — pure representation choice |
| `cr.phonemes` attached at compile time | C 1576-1613 (RULE_PHONEMES/PH_COMMON) | see §5 |
| `=`/`''` priority block placement (set_word_stress not get_vowel_stress) | C 891-907 | §3 POTENTIAL-BUG-5 — documented, gated |
| `get_vowel_stress` `=` extra guard `max_stress < STRESS_IS_PRIORITY` and the `'@-' != nucleus` / yue-`ng` skips | C 826 (the bare `while`) | PY 604, 623-634 — added conditions; the `=` guard prevents `=` from overriding a lexical `''` accent (pt símbolo). The C does this implicitly via the later priority block; PY's split needs the guard. Output-verified on the cited words. JUSTIFIED but interacts with PB-5 — keep an eye on non-pt `=`+`''` combos |
| `@-` very-short-schwa excluded from vowel count | (no C equivalent) | PY 630-634, 988-991 — espeak treats `@-` as a syllable nucleus; PY excludes it to fix onset-cluster stress (eo `pra`). This is a **default-engine correction**, gated implicitly by the `@-` mnemonic; should be confirmed listed in `divergences.md` if it changes force_compat output |
| `_nonsyllabic_before_vowel` (yue/zh `ng`) | (program-signature heuristic) | PY 565-578 — espeak's interpreter ChangePhoneme(N) effect reproduced by inspecting the phoneme program; output-equivalent for the yue case |
| suffix_vowels exclusion from auto-secondary | C runs GetVowelStress on stem only | PY 854-856 — espeak retranslates the stem; PY approximates by excluding the removed suffix's trailing vowels. Output-equivalent on ro `unele` |
| `consonant_types` as a set (PY 1024) | `consonant_types[16]` array (C 962) | PY enumerates phLIQUID/phSTOP/phVSTOP/phFRICATIVE/phVFRICATIVE/phNASAL/phVIRTUAL = the `1` entries (indices 3-9). phVOWEL excluded (PY comment 1021-1023 confirms the array has 0 at phVOWEL). Verified equivalent |
| `_eval` returns `(ok, flags1, flags2, stress)` tuple | C mutates `dictionary_flags`/`dictionary_flags2` in place | PY 400-445 — same condition order as C 2506-2647 for the ported subset (skipwords>80 fail, stress 64-80, flags2 32-63, flags1 0-31). `FLAG_STRESS_END` on `(flag&0xc)==0xc` matches C 2552-2553 |
| `_eval` multiword/skipwords always fail for isolated word | C 2521-2548 (skipwords need `word2` match) | PY 413, 422 — correct for the isolated-word lookup espyak performs |
| extra NFC normalization + polytonic-Greek raw keys | (not in C; espeak hashes raw bytes) | PY 338-345 — needed because espyak keys by Python str, not the byte hash; the polytonic exception prevents canonical-equivalence merges. JUSTIFIED |
| `case_sensitive_letters` / `key_upper` (fo L vs l) | C buckets by raw bytes in the hash | PY 363-371 — reproduces espeak's case-sensitive letter-name buckets that PY's lowercased keys would otherwise merge |
| leading `?N` condition before the word | C list compiler | PY 278-287 — `?N`/`?!N` → `+100`/`+132` flag codes, matching `_eval` decode and C 2510-2520 |
| `_unpronounceable` no-vowel subset only | `Unpronouncable` (translateword.c) | PY 1534-1556 — deliberately restricted to the robust no-vowel acronym case; documented as a subset |

---

## 9. Summary

- **MatchRule scoring:** every points arm verified equal to the C, **including** the two C
  quirks (PRE LETTERGP2 / NONALPHA using `distance_right`). The only missing POST/PRE arms
  are RULE_DEL_FWD, PRE `'.'`, PRE `J)`, and the `tone_numbers` no-digit branch — all in §3/§7.
- **SetWordStress auto-secondary loop (PY 857-887 ↔ C 1281-1329):** verified line-by-line —
  `S_FINAL_NO_2`, `0x8000` (first-vowel), trochaic `(v-1)<=UNSTRESSED && (v+1)<=UNSTRESSED|…`,
  `S_NO_AUTO_2`, `S_2_TO_HEAVY` (both the "heavy follows" and "directly-followed-by-heavy"
  checks), and `S_FIRST_PRIMARY` all match. The diminished-emit loop (PY 988-1014 ↔
  C 1378-1438) matches including `S_FINAL_DIM`/`S_NO_DIM`/`S_MID_DIM` and LOPT_IT_LENGTHEN.
- **Stress-rule switch:** STRESSPOSN_2R/1R/3R/SYLCOUNT/1RH/1RU/1SL/EU/2LLH verified equal;
  **STRESSPOSN_ALL, STRESSPOSN_GREENLANDIC, S_FINAL_LONG, and the S_FINAL_SPANISH an/ia/-ns
  arms are not ported** (§7).
- **Priority `''` / `=`:** the priority-demotion is moved out of GetVowelStress and gated to
  `pt` (§3 PB-5) — the biggest behavioural gap; the `=` guard is a justified compensating
  change.

The deviations that can change emitted phonemes are concentrated in §3 (PB-1..PB-5) and the
§7 unimplemented stress-rule / TranslateRules-switch features; the scoring core itself is
faithful.
