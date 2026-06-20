# Code review: `phoneme_program.py` + `render.py` vs `synthdata.c` / `phonemelist.c` / `dictionary.c`

Clean-room verification of espyak's phoneme-program VM and output renderer against the
espeak-ng C source they port. Scope: the output-affecting (`-x` / `--ipa`) path only —
synthesis statements (FMT/WAV/Vowelin/Vowelout/VowelStart/length/stress/PauseBefore) are
deliberately not modelled and are out of scope.

C source: `oracle/espeak-ng/src/libespeak-ng/{synthdata.c,phonemelist.c,dictionary.c}`,
compiler keyword table `compiledata.c`, constants `synthesize.h` / `phoneme.h`.

## Architectural note (the central, justified divergence)

espeak-ng compiles textual phsource programs (`IF … THEN … ENDIF`, `ChangePhoneme(x)`,
`CALL`, `ipa …`) into a 16-bit **bytecode** (`phoneme_index`); `InterpretPhoneme`
(synthdata.c:736) is a bytecode VM, and `InterpretCondition` (synthdata.c:468) decodes
condition words. **espyak instead interprets the textual phsource program lines directly**
(`parse_program` builds `_If` trees from `IF/ELIF/ELSE/ENDIF`; `Interpreter._exec` walks
them). The two are semantically equivalent: the bytecode is a 1:1 encoding of the text.
This is the right clean-room strategy and removes a whole class of bytecode-layout bugs;
every deviation below is judged against *semantic* equivalence, not byte layout.

A second structural difference: espeak runs the programs once, inside `MakePhonemeList`
(phonemelist.c:299, `control=0x100` "change phonemes" pass), and `-x`/`--ipa` is rendered
later from the final list, where `WritePhMnemonic` re-runs the program with `control=0`
(no changes, IPA-name only). espyak folds both into `Interpreter.run`: **pass 1** applies
ChangePhoneme/Insert/Append/ipa over the list; **pass 2** (`_ipa_only=True`) re-runs only
`ipa`/`RETURN`/`CALL` against the now-final list so context-dependent `ipa` overrides see
post-ChangePhoneme neighbours. This two-pass `ipa_only` design has no single C counterpart
but reproduces the C ordering (changes settle first, IPA names computed against the final
list); see the `operab opəʁ` / `da @-` comment at phoneme_program.py:205-211. Justified.

## Correspondence map

| espyak (Python) | espeak-ng (C) | notes |
|---|---|---|
| `Interpreter.run` pass 1 | `MakePhonemeList` program loop (phonemelist.c:251-431) calling `InterpretPhoneme(tr,0x100,…)` | applies structural ops |
| `Interpreter.run` pass 2 (`_ipa_only`) | `WritePhMnemonic` → `InterpretPhoneme(NULL,0,…)` (dictionary.c:471) | IPA-name re-eval on final list |
| `Interpreter._exec` / `_If` tree walk | `InterpretPhoneme` opcode loop + `case 2/3` condition/JUMP_FALSE block (synthdata.c:835-868) | IF/ELIF/ELSE/ENDIF ⇔ condition+JUMP_FALSE+ELSE-jump |
| `Interpreter._eval` (AND/OR/NOT, left-to-right) | `InterpretPhoneme` truth accumulator (synthdata.c:838-855): `or_flag`, `truth && / ||`, `i_NOT` | no precedence; OR/AND fold left-to-right — matches |
| `Interpreter._eval_pred` | `InterpretCondition` (synthdata.c:468-663) | which-phoneme selection + predicate |
| `_FEATURES` table | `k_properties[]` (compiledata.c:108-142) + `InterpretCondition` `CONDITION_IS_*` switch | predicate semantics |
| `_change` | `MakePhonemeList` pd_CHANGEPHONEME (phonemelist.c:321-333) + `ReInterpretPhoneme` (phonemelist.c:582-592) | SFLAG_SYLLABLE update, re-interpret, no-2nd-change |
| `_insert` | pd_INSERTPHONEME (phonemelist.c:308-319) + `ReInterpretPhoneme` + "loose the stress" comment (phonemelist.c:309) | stress transfer to inserted phoneme |
| `IfNextVowelAppend` branch | `i_APPEND_IFNEXTVOWEL` (synthdata.c:797-799) | append if next is vowel |
| `AppendPhoneme` branch | pd_APPENDPHONEME (phonemelist.c:429-430) | insert after this phoneme |
| `ChangeIf*` branch | `case 1` ChangeIf + `StressCondition(…,1)` (synthdata.c:827-833, 410-452) | stress-gated change |
| `_call` | `case 9` CALL (synthdata.c:887-908), return stack | CALL proc / `table/mnem` |
| `RETURN` | `INSTN_RETURN` end_flag (synthdata.c:788-790) | |
| `ipa NULL` / `ipa …` → `ipa_override` | `i_IPA_NAME` (synthdata.c:806-813) → `phdata.ipa_string` | conditional IPA name |
| `set_regressive_voicing` | `SetRegressiveVoicing` (phonemelist.c:503-580) | Slavic etc. voicing assimilation |
| `_eval_pred` which-selection (`thisPh/prevPh/nextPh/prev2Ph/next2Ph/*PhW/nextVowel/prevVowel`) | `InterpretCondition` `which` switch (synthdata.c:489-561) | word-boundary (`sourceix`) handling |
| `#i`/`#@` start/end-type match | synthdata.c:577-585 (`end_type` for prevPh on vowel, else `start_type`) | |
| `write_ph_mnemonic` | `WritePhMnemonic` (dictionary.c:441-524) | mnemonic/IPA name writer |
| `_IPA1` table | `ipa1[96]` (dictionary.c:428-435) | Kirshenbaum→IPA, verbatim |
| `render_phoneme_list` | `GetTranslatedPhonemeString` (dictionary.c:560-688) | stress mark + tie/separator + lengthen |
| `_reorder_tones` | (no direct C counterpart; espeak carries tone in `plist->tone_ph`, dictionary.c:661) | different tone model |
| `_STRESS_CHARS` `"==,,''"` | `stress_chars[]="==,,''"` (dictionary.c:588) | matches |

### `InterpretPhoneme` / `InterpretCondition` — line-by-line predicate verification

`condition_level[4] = {1,2,4,15}` (synthdata.c:414); StressCondition returns
`stress_level < condition_level[condition]` for DIMINISHED/UNSTRESSED/NOT_STRESSED, and
for SECONDARY returns `stress_level > 3`. Compiler keyword map (compiledata.c:126-141):

| Predicate | C code / semantics | espyak `_FEATURES` / handling | Verdict |
|---|---|---|---|
| `isVowel` | PHONEME_TYPE phVOWEL | `ph.type == phVOWEL` | ✓ |
| `isNotVowel` | OTHER isNotVowel → `ph.type != phVOWEL` | `ph.type != phVOWEL` | ✓ |
| `isPause` | PHONEME_TYPE phPAUSE | `ph.type == phPAUSE` | ✓ |
| `isPause2` | OTHER isBreak → `phPAUSE OR SFLAG_NEXT_PAUSE` (synthdata.c:608) | `ph.type == phPAUSE` only | ✓ justified — SFLAG_NEXT_PAUSE is set only in synthesize.c (post-MakePhonemeList), never at translation/render time |
| `isNasal` | PHONEME_TYPE phNASAL | `ph.type == phNASAL` | ✓ |
| `isLiquid` | PHONEME_TYPE phLIQUID | `ph.type == phLIQUID` | ✓ |
| `isUStop` | PHONEME_TYPE phSTOP | `ph.type == phSTOP` | ✓ |
| `isVStop` | PHONEME_TYPE phVSTOP | `ph.type == phVSTOP` | ✓ |
| `isVFricative` | PHONEME_TYPE phVFRICATIVE | `ph.type == phVFRICATIVE` | ✓ |
| `isVoiced` | OTHER: `vowel OR liquid OR phVOICED` (synthdata.c:634) | `vowel/nasal/liquid/vstop/vfric OR 'vcd' in flags` | ⚠ see DEV-1 |
| `isRhotic` | PHFLAG phRHOTIC | `'rhotic' in flags` | ✓ |
| `isSibilant` | PHFLAG phSIBILANT | `'sibilant'/'sib' in flags` | ✓ |
| `isLong` | PHFLAG phLONG | `'long' in flags` | ✓ |
| `isPalatal` | PHFLAG phPALATAL (bit 9) | `place in (pal,pla,alp)` (place string, not flag) | ⚠ see DEV-2 |
| `isVelar` | PLACE_OF_ARTICULATION phPLACE_VELAR=8 | `place in (vel,lbv)` | ⚠ see DEV-2 |
| `isFlag1` | PHFLAG phFLAG1 | `'flag1' in flags` | ✓ |
| `isFlag2` | PHFLAG phFLAG2 | `'flag2' in flags` | ✓ |
| `isFlag3`/`isFlag4` | **no such C keyword** (compiledata only defines flag1/flag2) | present in table, dead | ✓ harmless — no phsource uses them, parser never sets `flag3/flag4` |
| `isDiminished` | OTHER STRESS 0 → `level < 1` | `level == 0` | ✓ |
| `isUnstressed` | OTHER STRESS 1 → `level < 2` | `level <= 1` | ✓ |
| `isNotStressed` | OTHER STRESS 2 → `level < 4` | `level < 4` | ✓ |
| `isStressed` | OTHER STRESS 3 (SECONDARY) → `level > 3` | `level >= 4` | ✓ (note: `isStressed` is SECONDARY, not PRIMARY) |
| `isMaxStress` | OTHER STRESS 4 (PRIMARY) → `level >= pl->wordstress` (synthdata.c:441) | ctx `max_stress = level >= 4` | ⚠ see DEV-3 |
| `isWordStart` | OTHER: `plist->sourceix != 0` (synthdata.c:610) | `e.newword & 1` | ✓ |
| `isWordEnd` | OTHER: `plist[1].sourceix OR plist[1].type==phPAUSE` (synthdata.c:612) | ctx `word_end = next.newword&1 or end-of-list` | ⚠ see DEV-4 |
| `isAfterStress` | OTHER: walk back within word, true if any prior `level>=4` (synthdata.c:613-622) | ctx: first whole-list vowel with `level>=4`, `i > that` | ⚠ see DEV-5 |
| `isFirstVowel` | OTHER: `CountVowelPosition==1` (per-word backward count) | `vowels[0]==i` over whole list | ⚠ see DEV-5 |
| `isSecondVowel` | OTHER: `CountVowelPosition==2` (per word) | `vowels[1]==i` over whole list | ⚠ see DEV-5 |
| `isFinalVowel` | OTHER: forward scan, true at next word's `sourceix` w/o another vowel (synthdata.c:625-632) | `vowels[-1]==i` over whole list | ⚠ see DEV-5 |
| `isTranslationGiven` | OTHER: `SFLAG_DICTIONARY` | ctx `translation_given` flag | ✓ (model differs; same intent) |

Which-phoneme selection (synthdata.c:489-561) vs `_eval_pred` (phoneme_program.py:453-522):
- `thisPh`(1)/`nextPh`(2)/`next2Ph`(3)/`prevPh`(0) — ✓ (espyak adds `:`-skipping; see DEV-7).
- `nextPhW`(4)/`prevPhW`(5)/`next2PhW`(6)/`prev2PhW`(10) word-boundary fail-the-whole-condition
  via `sourceix` — espyak reproduces with `_ws()` checks (phoneme_program.py:492-504). ✓
  espeak's `next3PhW`(9) is **not** ported (UNIM-1; no phsource uses it).
- `nextVowel`(7)/`prevVowel`(8) — espeak's `prevVowel` reads `worddata->prev_vowel` (the
  cached previous vowel of the word); espyak scans backwards to the nearest vowel
  (phoneme_program.py:456-466). Output-equivalent for the contiguous case. ✓
- NULL-phoneme skip-back for prevPh/prevPhW (synthdata.c:563-568, `phcode==1`) — espyak's
  deleted phonemes are dropped from the list before/at render, so the index already points
  past them; equivalent in effect.
- `#i`/`#@` vowel-category: prevPh on a vowel matches `end_type`, else `start_type`
  (synthdata.c:583-585) — espyak phoneme_program.py:518-520 matches (`endtype` for
  prev*, else `starttype`). ✓

`_change` (phoneme_program.py:336) vs phonemelist.c:321-333 + ReInterpretPhoneme:
- "doesn't obey a second ChangePhoneme" → `self._changed` guard (✓, comment cites synthdata).
- ChangePhoneme(NULL) deletes (`alternative==1 → deleted`, phonemelist.c:328-329) → `deleted=True` ✓.
- SFLAG_SYLLABLE set for vowel / cleared otherwise (ReInterpretPhoneme synthdata… phonemelist.c:583-588) ✓.
- ReInterpretPhoneme also sets `stresslevel=0` when changing a **non-vowel→vowel**
  (phonemelist.c:585-586). espyak's `_change` updates SFLAG_SYLLABLE but does **not**
  zero the stress on a non-vowel→vowel change → DEV-6.
- re-run changed phoneme's program (`InterpretPhoneme` again) ✓ (depth-guarded).

`_insert` (phoneme_program.py:368) vs phonemelist.c:308-319: "if we insert a phoneme
before a vowel then we loose the stress" — espyak transfers the vowel's stress to the
(non-syllabic) inserted phoneme and promotes a lost primary back to the previous vowel
(phoneme_program.py:387-399). The promotion is espyak's reading of MakePhonemeList stress
promotion; the C "loose the stress" is a side effect of re-using the previous slot, and
the inserted phoneme being non-syllabic means the stress no longer renders. Behaviourally
matched for the documented acronym cases. Insert-once-per-pass guard (`_insert_done`) is a
Python-idiom guard against the textual interpreter re-inserting forever — justified
(comment cites lt `rajonas` hang). ✓

`render.py` vs `GetTranslatedPhonemeString` / `WritePhMnemonic`:
- `_IPA1` == `ipa1[96]` verbatim ✓; stress chars `"==,,''"` ✓.
- leading-space for START_OF_WORD-not-sentence/clause (dictionary.c:613) ✓.
- separator emission, skip if starts with superscript `0x2b0..0x36f` (dictionary.c:616-621) ✓.
- stress mark: `stress>1`, clamp to PRIORITY, IPA `0x2cc`/`0x2c8` else `_STRESS_CHARS`
  (dictionary.c:624-639) ✓.
- tie between non-initial alphabetic non-diacritic chars (dictionary.c:643-651) — espyak
  omits the C `!(flags & (1<<(count-1)))` per-char flag guard → DEV-8.
- SFLAG_LENGTHEN → write `phonLENGTHEN` (`:`) (dictionary.c:655-656) ✓.
- syllabic-consonant `phonSYLLABIC` for non-vowel SFLAG_SYLLABLE (dictionary.c:657-660) —
  **not ported** → UNIM-2.
- `plist->tone_ph` extra phoneme (dictionary.c:661-662) — espyak uses `_reorder_tones`
  instead (tones are real list phonemes) → DEV-9 (different model).
- `WritePhMnemonic` flags-byte handling (`*p < 0x20` → strip leading byte, dictionary.c:479-484)
  → espyak write_ph_mnemonic:184 (`ord(p[0]) < 0x20 → p[1:]`) ✓.

## Deviations table

| # | Deviation | C ref | Category | Justification / concern |
|---|---|---|---|---|
| ARCH-1 | Interpret textual phsource, not compiled bytecode | synthdata.c:736-958 (`InterpretPhoneme` VM) | JUSTIFIED | Semantically equivalent; clean-room strategy; bytecode is a 1:1 encoding of the text. |
| ARCH-2 | Two-pass `_ipa_only` re-eval vs C's run-once-then-render-with-control=0 | phonemelist.c:299 + dictionary.c:471 | JUSTIFIED | Reproduces C ordering: changes settle, IPA names computed against final list (comment 205-211). |
| DEV-1 | `isVoiced` includes nasal/vstop/vfric/`'vcd'`; C is `vowel OR liquid OR phVOICED` | synthdata.c:633-634 | JUSTIFIED (output-equiv) | espeak's voiced obstruents carry `phVOICED`; nasals are `phVOICED` in phsource. Superset matches in practice; only used in a few programs and on phonemes that carry the flag anyway. |
| DEV-2 | `isPalatal`/`isVelar` decided by `place` string vs C phflag(palatal)/place(velar) | synthdata.c:594-597; compiledata.c:117,124 | POTENTIAL-BUG (low) | espyak derives `place` from the phsource decl heuristically; phPALATAL is a real phflag in espeak (can be set independent of place). A phoneme flagged palatal without a `pal` place string, or a `pal`-place phoneme without the flag, would disagree. Affects velar-nasal assimilation programs: en/lule_saami `n→N` before `isVelar`; am/ca/hi/ko/gu palatalisation before/after `isPalatal`. |
| DEV-3 | `isMaxStress` = `level>=4`; C = `level >= pl->wordstress` | synthdata.c:440-441 | POTENTIAL-BUG (low) | `wordstress` is the max stress in the word; when a word's top stress is only secondary (3), C's `isMaxStress` fires at level 3 but espyak requires 4. Used by da (many programs) and ru; could shift da vowel changes in words whose nucleus never reaches primary. |
| DEV-4 | `isWordEnd` lacks the `next.type==phPAUSE` arm | synthdata.c:611-612 | POTENTIAL-BUG (low) | C treats a phoneme followed by a pause as word-end even without a `sourceix`/newword mark. espyak only checks next-is-word-start / end-of-list. A word-internal pause (e.g. inserted `_!`) before the final phoneme would make C report word-end where espyak does not. Rare; depends on pause insertion which espyak largely omits at render time. |
| DEV-5 | `isFirstVowel/isSecondVowel/isFinalVowel/isAfterStress` computed over the whole phoneme list, not per-word | synthdata.c:454-465 (CountVowelPosition), 613-632 | POTENTIAL-BUG | C scopes all four to the **current word** (stops at `sourceix`). espyak's `_context` scans the entire `plist`. For a single-word input these agree; for a multi-word clause rendered as one list, only the last word's last vowel is `isFinalVowel`, first-word vowels are mis-numbered, etc. espyak normally renders word-by-word so the practical blast radius is small, but multi-word `[[…]]` strings or P5 multi-word lists would mis-evaluate. Most-affected: da (`isFirstVowel`/`isSecondVowel`/`isMaxStress` heavy), en (`isFinalVowel`). |
| DEV-6 | `_change` does not zero stress on a non-vowel→vowel ChangePhoneme | phonemelist.c:585-586 (`plist3->stresslevel = 0`) | POTENTIAL-BUG (low) | ReInterpretPhoneme forces an unstressed level when a consonant becomes a vowel so the new vowel isn't spuriously stressed. espyak sets SFLAG_SYLLABLE but keeps the old stresslevel. A consonant→vowel change on a slot that carried a stress mark could render a stray secondary/primary. No phsource hot-path identified that exercises consonant→vowel (changes are usually vowel→glide, the opposite, which espyak does handle by clearing SFLAG_SYLLABLE); low likelihood. |
| DEV-7 | `prev*/next*` step over a `:` length marker | (no C analogue — `:` is merged into the vowel as SFLAG_LENGTHEN before bytecode) | JUSTIFIED | espyak keeps `:` as a list entry in some encode paths; skipping it reproduces espeak where the marker is not a separate phoneme at program time (comment 467-470). Output-equivalent. |
| DEV-8 | tie inserted between any non-initial alpha char; C also skips when the per-char IPA-flags bit is set | dictionary.c:647 (`!(flags & (1<<(count-1)))`) | POTENTIAL-BUG (very low) | The `flags` come from a leading flags-byte in an `ipa` name marking which chars are "joined". Almost no phoneme sets it; matters only with `--tie` on an IPA name that carries the rare flags byte. Negligible. |
| DEV-9 | Tones handled by `_reorder_tones` (digit-named phSTRESS list phonemes) vs C `plist->tone_ph` | dictionary.c:661-662; render.py:212-229 | JUSTIFIED (different model) | espyak models tones as real phonemes in the list and relocates them after the nucleus; espeak carries a separate `tone_ph` code. Output-equivalent for cmn/yue Chao contours per the cited examples. Worth a targeted oracle diff but not a logic error. |
| UNIM-1 | `next3PhW` (which==9) not implemented | synthdata.c:548-554; compiledata.c:98 | UNIMPLEMENTED | No phsource program uses `next3PhW`; zero languages affected. |
| UNIM-2 | syllabic-consonant diacritic (`phonSYLLABIC`, IPA ◌̩) not emitted | dictionary.c:657-660 | UNIMPLEMENTED | A non-vowel carrying SFLAG_SYLLABLE would miss its syllabic mark. espyak's `_change` clears SFLAG_SYLLABLE on non-vowels, so the flag mainly survives on dictionary-supplied syllabic consonants. Affects languages with syllabic consonants marked at translation time (e.g. cs/sk/hr vocalic r/l in some encodings); the existing `nonsyllabic`/`nsy` handling covers the common vocalic-r path differently. Low-moderate. |
| UNIM-3 | `ChangeNextPhoneme` (pd_CHANGE_NEXTPHONEME) not handled | phonemelist.c:301-306; compiledata.c:263 | UNIMPLEMENTED | Valid keyword but **used by zero phonemes** in the bundled phsource; no language affected (dead). |
| UNIM-4 | `SetRegressiveVoicing` per-table phonSWITCH language re-selection | phonemelist.c:511-521, 526-531 | UNIMPLEMENTED (partial) | espyak's `set_regressive_voicing` ports the voicing logic but not the in-loop `phonSWITCH`/`SFLAG_SWITCHED_LANG` table re-selection. Only matters for mixed-language clauses with regressive-voicing langs (pl/ru/etc.) crossing a `(lang)` switch mid-cluster. Rare. |

## Comment-accuracy spot checks

The inline C-reference comments are accurate where checked: the `_changed`/"doesn't obey a
second ChangePhoneme" note (phoneme_program.py:336-340) matches synthdata.c's exit-on-first-
change; the "loose the stress" insert comment (368-403) matches phonemelist.c:309; the
`*PhW` word-boundary comment citing "synthdata.c:497-516" matches synthdata.c:499-511; the
`#i` end-type/start-type comment "synthdata.c:583" matches synthdata.c:583-585; `_IPA1`
"verbatim from dictionary.c ipa1[96]" verified verbatim. One nit: the StressCondition
note at `ChangeIf*` (phoneme_program.py:305-308) is correct re SFLAG_DICTIONARY/LOPT_REDUCE
(synthdata.c:429), but the LOPT_REDUCE&0x2 "promote most-stressed-as-stressed" arm
(synthdata.c:434-437) is not modelled — minor, affects only the ChangeIf gating in
reduce-flagged languages.

## Summary

- JUSTIFIED: 5 (ARCH-1, ARCH-2, DEV-1, DEV-7, DEV-9)
- POTENTIAL-BUG: 6 (DEV-2, DEV-3, DEV-4, DEV-5, DEV-6, DEV-8)
- UNIMPLEMENTED: 4 (UNIM-1, UNIM-2, UNIM-3, UNIM-4)

Highest-value follow-ups: DEV-5 (per-word vs whole-list vowel-position scope — the only
deviation with a plausibly large multi-word blast radius) and DEV-2 (palatal/velar via
place-string heuristic — drives real assimilation programs in several languages).
