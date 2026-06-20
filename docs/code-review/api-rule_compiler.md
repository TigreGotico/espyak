# Code review: `api.py` + `rule_compiler.py` vs `translateword.c` / `compiledict.c`

Clean-room verification of espyak's translate pipeline (`espyak/api.py`) and compiled-rule
byte encoding (`espyak/rule_compiler.py`) against the espeak-ng C source they port.

C source: `oracle/espeak-ng/src/libespeak-ng/` — `translateword.c` (TranslateWord3),
`translate.c` (TranslateWord2 / phonSWITCH), `dictionary.c` (RemoveEnding; copy_rule_string
is in `compiledict.c`), `compiledict.c` (rule byte encoding). espeak-ng 1.52.0.

Verdict: the rule byte-encoding port (`rule_compiler.py`) is **faithful** — no byte-layout
bug found. The translate pipeline (`api.py`) is a **correct but reduced** port: it implements
one prefix-level and one suffix-level per call and omits several C affix loops/options; these
are recorded as UNIMPLEMENTED, not bugs. **No POTENTIAL-BUG deviations were found.**

---

## 1. Correspondence map

### 1a. `rule_compiler.py` ↔ `compiledict.c`

| Python | C (`compiledict.c`) | Role |
|---|---|---|
| `_copy_rule_string(string, state)` | `copy_rule_string` (778) | per-section special-char encoding; `next_state[5]={2,2,4,4,4}` |
| `_special_char(c,p,i,state,sxflags)` | the `switch(c)` body (837–1011) | one special char in pre(1)/post(3) |
| `compile_rule(line, group_name)` | `compile_rule` (1021) | section split `) ( \t ?`, assemble `match[len_name:]+cond+pre(rev)+post` |
| `_flush(sections,text,state)` | one `copy_rule_string` call | per-token dispatch; empty text is a no-op (`if(string[0]==0)return;`) |
| `RuleSet.compile_file` | `compile_dictrules` (1335) | line loop, `.group`/`.replace`/`.L` directives, group flush |
| `_parse_group_name` | group-name read at 1413–1444 | `0x..` codes, 2-byte UTF-8 truncation |
| `_store_group` | `output_rule_group`+`rgroup` bucketing | groups1 (1 byte) / groups2 (2 byte) / groups3 (codepoint) |
| `_parse_lettergroup` | `compile_lettergroup` (1256) | `.Lnn` items, `_`→space |
| `_sort_rules_by_phoneme_code` (api.py) + `_sort_groups` (no-op) | `string_sorter` (1174) + matcher tie-break | sort-equivalent; see §3 |

Byte-layout checks (all confirmed correct):

- **State machine** `next_state[5]={2,2,4,4,4}` — identical (`_copy_rule_string` line 72).
- **`sxflags=0x808000`** initial value — identical (line 77 vs C 806).
- **Pre reversed, RULE_PRE_ATSTART** — `compile_rule` emits `RULE_PRE_ATSTART`+`start=1`
  when `pre[0]==RULE_SPACE`, else `RULE_PRE`, then iterates `reversed(pre[start:])`. Matches
  C 1149–1162 exactly (omit leading `_`, write PRE backwards).
- **RULE_CONDITION**: `!`→`atoi(cond[1:])+32`, else `atoi(cond)`, gate `0<ix<255`, emit
  `RULE_CONDITION, ix`. Matches C 1132–1147. (Python uses `_leading_int`, tolerating trailing
  junk; C `atoi` does the same.)
- **RULE_POST**: `RULE_POST`+post bytes — matches C 1164–1166.
- **Letter-group order**: pre (state 1) emits `group_byte` then `RULE_LETTERGP`; post (state 3)
  emits `RULE_LETTERGP` then `group_byte`. Identical to C 852–859. Same inversion for
  `RULE_LETTERGP2` (`L`) and `RULE_DOLLAR` (`$`, `T`). Verified — **no off-by-one / order swap.**
- **`$` mnemonics** `_MNEM_RULES` ↔ `mnem_rules`: unpr/noprefix/list/w_alt[1-6]/p_alt[1-6]
  with bare `w_alt`=0x11, `p_alt`=0x21. Matches.
- **P/S ending**: emit `RULE_ENDING`, accumulate `sxflags` over the suffix-flag letters and a
  decimal `value`, then emit `(sxflags>>16)&0xff`, `(sxflags>>8)&0xff`, then `value|0x80`.
  Byte order and `|0x80` terminator match C 962–1009 exactly. `P` pre-sets `SUFX_P`.
- **0x-hex / `\`-octal / hex-run literals** — `_copy_rule_string` reproduces the three literal
  paths (0x prefix, backslash-octal `\NNN`, trailing hex run) with the same pointer/`i` advances.
- **Group bucketing** `_store_group`: name `""`→default; 1 byte→groups1; 2 bytes→groups2;
  single ≥3-byte char→groups3 (keyed by codepoint, avoids UTF-8 lead-byte collisions). Matches
  the C distinction between byte-keyed groups and `group3_ix` (1430–1434).
- **`.Lnn` longest-first**: C writes items longest-first (1313–1320) and the matcher takes the
  longest; Python stores items as-is and `_is_letter_group` returns the **longest** match — same
  net behavior (verified `dictionary.py:_is_letter_group`).
- **`9` numeric group** `len_name=0` (don't strip leading char from numeric match strings) —
  `compile_rule` checks `group_name in ("","9")`; matches C `output_rule_group` 1218–1219 and
  `compile_rule` `group_name[0]=='9'` digit allowance.

Constants cross-checked (`espyak/constants.py` ↔ `translate.h`): RULE_PRE=1, RULE_POST=2,
RULE_PHONEMES=3, RULE_PH_COMMON=4, RULE_CONDITION=5, RULE_GROUP_START=6, RULE_GROUP_END=7,
RULE_PRE_ATSTART=8, RULE_LINENUM=9, RULE_ENDING=14, RULE_LETTERGP=17, RULE_LETTERGP2=18,
RULE_DOLLAR=28, RULE_LAST_RULE=31, RULE_SPACE=32, N_LETTER_GROUPS=95, and the full SUFX_*
table (E=0x100 … M=0x80000) — **all match the C `#define`s.**

### 1b. `api.py` ↔ `translateword.c` / `translate.c`

| Python (`api.py`) | C | Role |
|---|---|---|
| `_translate_core` | TranslateWord3 body (266–535) | dict lookup → rules → one prefix OR one suffix branch |
| `translate_word` | TranslateWord3 tail (537–671) | stress determination, prefix-stress reduction, `||` multiword |
| prefix branch (499–515) | TranslateWord3 prefix loop (338–437) + stress (551–570) | `SUFX_P` removal, LOPT_PREFIXES secondary-on-stem + reduce-primaries |
| `_translate_with_suffix` | suffix branch (439–531) | `RemoveEnding`, re-translate stem, append suffix |
| `_reduce_extra_primaries` | reduce-primaries loop (558–566) | keep first `'`, later `'`→`,,` |
| `_apply_alt_attribute` | `ApplySpecialAttribute2` (674–702) | LOPT_ALT&2 open/close vowel after first `'` |
| `_spell_word` / `_join_spelled` | SpeakIndividualLetters + SetSpellingStress | spell-out, count%3 reduction |
| `phonemize` foreign-word `(en)…(lang)` | TranslateWord2 phonSWITCH (416–463) + `_^_` | language switch |
| `remove_ending` (dictionary.py) | `RemoveEnding` (dictionary.c 2901) | suffix removal + y→i / add-e |

---

## 2. Inline C-reference comment accuracy

All inline C-reference line citations spot-checked against the oracle were accurate or close:

- `_reduce_extra_primaries` "translateword.c:557" — matches the reduce-all-but-first-primary
  loop at 557–566. **Accurate.**
- prefix comment "translateword.c:553" (LOPT_PREFIXES "keep a secondary stress on the stem") —
  the `SetWordStress(...,3,0)` is at 555, gate `param[LOPT_PREFIXES]` at 552. **Accurate.**
- `ApplySpecialAttribute2` comment (LOPT_ALT&2) — matches 682–701. **Accurate.**
- `RemoveEnding` docstring "dictionary.c:2901" — exact.
- `_unpronounceable` "translateword.c:1114" — the C `Unpronouncable` lives there; Python ports
  only the no-vowel subset (see §3). Comment correctly states the restriction.
- "compiledict.c:462" (phoneme output read up to first whitespace) in `_flush` — see D9.

---

## 3. Deviations

| # | Deviation | C ref | Category | Justification / concern |
|---|---|---|---|---|
| D1 | Phoneme strings kept as **mnemonic text**, not phoneme-table byte codes; **RULE_PH_COMMON not implemented** (every rule carries its own phoneme string) | `compiledict.c` `output_rule_group` 1231–1250 (RULE_PH_COMMON), `compile_rule` 1103 EncodePhonemes | JUSTIFIED | RULE_PH_COMMON is a pure storage-dedup optimization; expanding it yields identical per-rule phoneme strings. The renderer consumes mnemonics. No behavioral effect. Documented in module docstring. |
| D2 | `_sort_groups` is a **no-op**; rules kept in file order. espyak instead re-sorts at match time by **phoneme-table code** (`G2P._sort_rules_by_phoneme_code`) keyed `(group_seq, [code], match_str)` | `string_sorter` 1174 (sorts by phoneme *string* then match) + matcher last-best-wins `>=` tie-break | JUSTIFIED | C sorts by phoneme string only to enable RULE_PH_COMMON; the *matcher* tie-break (sort-last equal scorer wins) is what matters. espyak reproduces the tie-break by sorting on phoneme **code** (table index), which is what the C matcher compares — a plain ASCII-mnemonic sort gets `tn` (b→B) wrong. The `group_seq` key reproduces "later `.group` block wins" (bn duplicate `এ`). Subtle but correct; reasoning documented in both `_sort_groups` and `_sort_rules_by_phoneme_code`. |
| D3 | Group names truncated to **2 bytes** in `_parse_group_name`; a >2-byte multi-char group keeps its **first char** | `compile_dictrules` 1437–1444 (`group_name[2]=0`) | JUSTIFIED | Mirrors C 2-byte UTF-8 truncation. A 2-byte accented letter (ä) survives; longer groups are 3-byte single chars (handled via groups3) — Python keeps `name[:1]` only when `len(utf8)>2` and not a single char, matching the C path that nulls byte 2. |
| D4 | Prefix handling: **one prefix level per `_translate_core` call** (recurses on stem); **no `loopcount<50` loop, no `confirm_prefix` suffix-recheck, no SUFX_B (Turkish) branch** | TranslateWord3 338–437 (`for loopcount<50`, `confirm_prefix`, `SUFX_B` at 375–415) | UNIMPLEMENTED | Recursion covers nested prefixes (api.py:511 notes innermost-only secondary). **SUFX_B (Turkish `' (Pb`) not handled** — affects **tr** prefix-with-separator. `confirm_prefix` (re-strip suffix to confirm prefix still recognised) is skipped: affects rare prefix+suffix co-occurrence. Not a byte/encoding bug; a coverage gap. Langs affected: **tr** (SUFX_B), edge prefix+suffix combos. |
| D5 | Suffix handling: **single suffix per call**; **SUFX_M (multiple suffixes) loop and SUFX_T deferred-suffix not implemented** | TranslateWord3 `more_suffixes` 447–522 (SUFX_M 496–506), SUFX_T 525/583–588 | UNIMPLEMENTED | `_translate_with_suffix` docstring explicitly states "SUFX_M multiple suffixes and SUFX_Q/SUFX_T variants are not yet handled." SUFX_Q **is** handled (api.py:516). SUFX_T (add suffix *after* stress) and SUFX_M (stacked suffixes, mainly English chains) are gaps. Langs affected: **en** and others using stacked / `T` suffixes. Not a bug. |
| D6 | `_unpronounceable` ports only the **no-vowel** case; the C `length<3` short-remainder spell loop and `Unpronouncable2` (LOPT rule test) are omitted | TranslateWord3 278–303 (`length<3` loop), `Unpronouncable`/`Unpronouncable2` 1114+ | UNIMPLEMENTED | Restricted to the robust no-vowel acronym case (ca Mgfc, en th); guarded to Latin-script non-tonal langs. The `length<3` progressive-letter-spelling and LOPT_UNPRONOUNCABLE rule test are not ported. Langs affected: any relying on LOPT_UNPRONOUNCABLE / short-fragment spelling. Conservative omission, documented. |
| D7 | `remove_ending` SUFX_E for **nl** uses `suffix_add_e` append (like de/af) instead of C's nl-specific "double the vowel before final consonant" letter transform | `RemoveEnding` 2972–2979 (nl branch: `word_end[1]=word_end[0]; word_end[0]=word_end[-1]`) | JUSTIFIED | C's nl branch rewrites stem letters (dez→deez) so the re-translated stem keeps open-syllable length. espyak instead **keeps the in-context phonemes** via the `SUFX_E && incontext_ph` path in `_translate_with_suffix` (api.py:655–660), gated off when `FLAG_SUFX_E_ADDED`. Different mechanism, same result (nl deze → deːz). Reasoning documented at api.py:655 and dictionary.py:1717. |
| D8 | phonSWITCH realized as a string sentinel `_^_<lang>` / `(en)…(lang)` wrapping in `phonemize`, not the C in-band `phonSWITCH` phoneme + `SetTranslator2` re-translate-in-place. The 2-attempt `switch_attempt` retry and unknown-language `phonSCHWA` fallback are not reproduced | `translate.c` TranslateWord2 416–463, `_^_` in TranslateRules | UNIMPLEMENTED | espyak has no shared ph_list2 buffer; it re-renders the foreign word with a cached `G2P(lang)` and brackets it. Behavioral surface (the `(lang)…(orig)` output) matches the `-q --ipa` reference. Coverage of the double-switch retry / `phonSCHWA` "say something" fallback is a minor gap, not a bug. |
| D9 | `_flush` state-4 keeps only the **first** space-separated phoneme token; C `copy_rule_string` appends the whole phoneme string (spaces preserved) and EncodePhonemes consumes all of it | `copy_rule_string` 799–805 | JUSTIFIED | For the documented `tn _k) g  g x2` case espyak yields `g` (drops the `x2` annotation), which is the espeak-ng intended output. Inline comment cites compiledict.c:462. Net result correct for the observed corpus; the comment's "reads only up to first whitespace" describes the *intended* semantics rather than the literal C append. No divergence in rendered output found. |

### Off-by-one / byte-layout audit (the high-risk area)

Specifically re-checked for silent phoneme-shifting byte errors in `rule_compiler.py`:

- pre-section reversal start index (`start=1` only when `pre[0]==RULE_SPACE`) — **correct**.
- letter-group / `$` / `L` / `T` byte **ordering** inverted between pre and post — **correct** both ways.
- `RULE_CONDITION ix` two-byte emission; `0<ix<255` gate — **correct**.
- P/S ending `(sxflags>>16)`, `(sxflags>>8)`, `value|0x80` order and masks — **correct**.
- `len_name` stripping (`match[len_name:]`, `len_name=0` for `""`/`9`, UTF-8 vs latin-1 raw
  byte width) — **correct**; `group_raw` selects latin-1 width so a 0x-code 2-byte group strips
  the right count.
- octal/hex literal pointer advances vs C `p`/`i` — **correct** (no over/under-consume).

**No off-by-one or byte-shift bug detected.**

---

## 4. Summary counts

- JUSTIFIED: **5** (D1, D2, D3, D7, D9)
- UNIMPLEMENTED: **4** (D4, D5, D6, D8)
- POTENTIAL-BUG: **0**
