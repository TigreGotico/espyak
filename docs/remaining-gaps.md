# Remaining gaps — why `force_compat` parity is not yet 100%

`espyak` is a clean-room Python port of espeak-ng. In `force_compat` mode it reproduces
espeak-ng **byte-for-byte, bugs included**, and the headword parity audit measures exactly
that. This document is the per-fail ledger: it accounts for every remaining mismatch and
separates the systematic-deferred ones (a known C feature, closable feature-by-feature)
from the clause-tonic-ordering floor (deterministic mechanisms whose byte-exact port is
blocked by an architectural ordering difference, plus a slice of genuine oracle
self-inconsistency / UB). None of these are formant-synthesis allophones — an earlier
"synthesis-irreducible" verdict on the `ru`/`pt` entries was re-verified and found WRONG.

## The number

Full-headword audit (`test/parity_audit.py --cap 2000`, oracle = espeak-ng 1.52.0,
`-q --ipa`, `force_compat=True`), all 105 languages with a `_list`:

```
OVERALL 46162 / 46228 = 99.86%   →   66 mismatches
```

The 136 fails are spread thin: **46 of 105 languages** have any fail at all, and the
largest single concentration is **`it` = 31** (26 of which are one mechanism — Cyrillic
single letters spelled through a `ru` language switch). No other language exceeds 5 fails;
**59 languages are at 100%**, including every one that historically dominated the gap —
`shn` 2000/2000, `et` 211/211, `lv` 570/570, `smj`/`ur`/`yue`/`pl`/`lb` all 100%.

Symptom histogram (input shape, not cause): `word=55, single-char=39, non-alpha=26,
two-letter=15, single-symbol=1`. The root-cause buckets below sum to 136.

| Bucket | Root cause | Count | Kind |
|--------|------------|------:|------|
| **A** | Phoneme-level language switch / codepoint verbalization not crossed | **29** | systematic-deferred |
| **B** | Letter-name / abbreviation / symbol spelling (`LookupDictList` long tail) | **45** | systematic-deferred |
| **C** | Word stress / vowel-quality / voicing not derivable by rule | **52** | mixed (some irreducible) |
| **D** | `numbers.c` branches + `$N` dollar-fraction | **10** | systematic-deferred |

`B` and `D` and most of `A` are systematic and closable feature-by-feature. The
IRREDUCIBLE residue lives inside `C` (and a slice of `A`): see "The irreducible floor".

---

### (A) Phoneme-level language switch — **29**

**The faithfulness gap.** espeak's `TranslateWord2` emits an *in-band* `phonSWITCH`
phoneme and calls `SetTranslator2`, re-translating a foreign or unknown run **in place** on
the shared `ph_list2` buffer; the source language's post-processing (stress copy, tone
copy, regressive voicing) then runs *over the switched phonemes*. espyak switches at the
**string level**: it re-renders the foreign run with a cached `G2P(lang)` and brackets the
result `(lang)…(orig)` (see `docs/code-review/api-rule_compiler.md` D8). The output surface
matches when the switch is clean; it diverges when the source language's post-processing
must cross the boundary, or when the switched run produces nothing in espyak.

The shn codepoint-spelling sub-case of this — the largest historical contributor — is
**closed**: an in-band `\x01<hex>\x02` sentinel carries the codepoint spelling and the
phonSWITCH so shn's tone post-pass crosses it (`d921a45`), taking shn to 2000/2000.

**What remains:**

| lang | input | espeak (oracle) | espyak (got) |
|------|-------|-----------------|--------------|
| it | `а` (Cyrillic) | `tʃɪrˈillɪko(ru)ˈɑ(it)` ("cirillico", then the letter in ru) | `` (empty) |
| nog | `книга` | `(ru)knʲˈiɡa(nog)` | `` (empty) |
| it | `hollywood` | `(en)hˈɒliwˌʊd(it)` (secondary kept) | `(en)hˈɒliwʊd(it)` (secondary dropped) |
| de | `nvda` | `(en)ˌɛnvˌiːdˌiːˈeɪ(de)` (spelled letter names) | `(en)nvdˈɑː(de)` |
| fr | `output` | `(en)ˈaʊtpʊt(fr)` | `(en)ˈaʊtpˌʊt(fr)` (spurious secondary) |

**Affected:** `it`=26 (Cyrillic single letters: each spells "cirillico" then names the
letter through a `ru` switch — espyak emits nothing for the letter), `nog`=3 (whole Russian
words switch to `ru`; espyak's `nog` rules can't translate them and emit empty), plus single
boundary-stress fails in `it`/`de`/`fr`. Closing this needs the phoneme-level switch (a
shared buffer the source post-processor runs over) rather than the string-level bracket.

---

### (B) Letter-name / abbreviation / symbol spelling — **45**

`LookupDictList` (`dictionary.md` §7) handles dotted abbreviations (`a.b.c`), SUFX-stripped
re-lookup, the `FLAG_ACCENT` fallback chain, and the spelled-letter expansion chain. Its
long tail is the biggest systematic bucket. Surfaces as a single letter, a two-letter
abbreviation, a dotted form, or a symbol whose name espeak expands and espyak does not (or
expands differently):

| lang | input | oracle | got |
|------|-------|--------|-----|
| ca | `t` | `tˈe` (spell the letter) | `tˈɛtə` (re-stressed name) |
| en | `lbs` | `pˈaʊndz` (unit abbrev) | `ˌɛlbˌiːˈɛs` (spelled letters) |
| en | `c#` | `sˈiː hˈaʃ` | `k` (symbol `#` table) |
| hu | `u.n` | `ˈuːɟnɛvɛzɛtː` (abbrev expansion) | `ˈuˌɛnn` |
| es | `ej` | `exˈemplo` (abbrev) | `xˈemplo` |
| ar | `ع` | `ˈʕʕˈaːjn` (letter name) | `ʕ-ˈaːjn` |
| gd | `w` | `dˈɔhbəljuː` | `dˈɔbəljuː` |

**Affected (spread thin):** `ca`/`hu`=4-5 (abbreviations + letter names), `en`/`es`/`ar`/
`gd`/`fo`/`ml`/`kok`/`bpy` and many one-fail languages. Each is its own micro-fix; the
biggest single lever is the `LookupDictList` abbreviation/letter-name expansion chain.

**`ko` `$text` respellings that carry a `/` variant marker (3 entries).** `ko_list` gives
three sandhi respellings as two `/`-separated alternatives — `곗날→곈ː날/겐ː날`,
`툇마루→퇸ː마루/퉨ː마루`, `가ᅬᆺᅵᆯ→가ᅬᆫ닐/가ᅰᆫ닐`. espeak re-injects the `$text` value as a single
word (translate.c FLAG_TEXTMODE), and the embedded `/` makes that word unpronounceable, so it
falls into `SpeakIndividualLetters` (translateword.c:749) → `TranslateLetter` per character.
There `TranslateChar` (translate.c:850) decomposes each syllable into jamo with the `*insert`
recursion and the ko dict-list letter-name entries (`ᄀ gij'@q`, `ᄂ ni;'u-n`) fire for the
isolated initials while the rules voice the medials/finals, dropping the length mark and the
whole post-`/` variant: `곗날 → ɡijˈʌq jˈe t- niˈɯn ˈɐ ɫ`. The per-jamo pieces espyak already
reproduces exactly (standalone `ᄀ→ɡijˈʌq`, `ᅨ→jˈe`, `ᆫ→n`, `ᄂ→niˈɯn`, `ᅡ→ˈɐ`, `ᆯ→ɫ`), but the
word-context token (`t-` where the isolated final ㄴ gives `n`) is an emergent artifact of the
exact `SpeakIndividualLetters`/`*insert`/`SetSpellingStress` buffer path over the `/`-carrying
decomposed string, not any clean per-jamo mapping — so a faithful port is disproportionate to
three dictionary entries. espyak instead renders both `/`-variants as syllables and joins them.

---

### (C) Word stress / vowel quality / voicing — **52** (the largest bucket)

Per-word differences where espeak emits an open/close vowel, a length, a voicing, or a
stress placement that is **lexically or context-conditioned** and not derivable from the
bundled rule data, or is non-reproducible. This bucket holds the entire irreducible floor
plus the rule-recoverable stress residue.

| lang | input | oracle | got | class |
|------|-------|--------|-----|-------|
| ru | `могла` | `mʌɡɭˈa` | `mʌɡɭˈɑ` | voice `replace 03 a a#` vs clause-tonic ordering (see floor #2) |
| la | `pro` | `pˈrɔ` | `prˈɔ` | onset-cluster stress: nonsyllabic `@-` as a pitch syllable (see floor #3) |
| da | `barrikade` | `bˈɑʔikaaðə` | `bˌɑʔikˈaaðə` | primary/secondary placement (rule-scorer tie-break) |
| pt | `pròs` | `pɹˈuʃ` | `pɹˈʊʃ` | grave-accent vowel path short-circuits `o (s_ → =U` (see floor #1) |
| ko | `곗날` | jamo-by-jamo letter names | syllable render | `/`-variant `$text` respell buffer path |

Most of this bucket's historical entries are now **closed** — `ru радио`, `tr ben`, `sr/hr/bs
uxd`/`sl`, `cs byl`, `ky эмнеге`, `is vegna`, `af cliché`, `cmn 都`, `it й` were each fixed by
porting the responsible mechanism (`phonSYLLABIC` counting, `ImportPhoneme` voicingswitch reset,
letter-group overrides, `CountVowelPosition` semantics, raw dict keys, `SetLetterVowel`, and the
`StressCondition` consonant/`LOPT_REDUCE=2` arms).

**Closable share.** What remains here is a mix: the `da` primary/secondary case is a shared
rule-scorer tie-break (engine-wide blast radius for one word), and the rest are the floor
entries below.

---

### (D) `numbers.c` branches + `$N` dollar-fraction — **10**

`numbers-config.md` §2 lists roman, myriads/lakh, feminine/`M_Variant`, `DFRACTION`,
`NUM_VIGESIMAL`, the Devanagari-numeral path, and ordinal sub-machinery as unported, plus
the `$N` dollar-fraction dictionary directive (`it intranet$3`, `ro …$2`):

| lang | input | oracle | got |
|------|-------|--------|-----|
| mr | `२४` | `tʃoːvˈiːs` (24 spoken) | `tʃˈaːɾ` (Devanagari-numeral path) |
| it | `intranet$3` | `intrˈanet dˈɔllarɪ trˈe` | `intrˈanet trˈe` (`$3` dropped) |
| ro | `mesageră$2` | `mesˈadʒeɾˌə dolˈar dˈoɪ` | `…dolˈar dˈoɪ` ($2 stress) |
| py | `6` | `ˈə` | `hlˈis` (digit-name path) |

**Affected:** `py`=4, `mr`=2, `it`/`ro`=1-2, plus assorted digit-bearing inputs. Each is a
bounded port of a known `numbers.c` branch.

---

## The clause-tonic-ordering floor

Inside bucket C (and a slice of A) sit cases whose mechanism is fully deterministic (NOT
formant synthesis — an earlier "synthesis-allophone" verdict on these entries was WRONG, the
same error made and corrected for `sr/hr/bs uxd`), but whose byte-exact port is blocked by
espyak applying the clause-intonation tonic *before* the phoneme programs (via
`set_word_stress(tonic=4)` at the nucleus re-render) where espeak applies it *after*
(`CalcPitches`, post-`InterpretPhoneme`). Reproducing them needs the per-word render reworked
into espeak's clause-level phoneme-list model — the same architectural change floor #3 needs.

1. **`pt pròs` grave-accent vowel path (`pɹˈuʃ` vs `pɹˈʊʃ`).** NOT synthesis. The grave-accented
   `ò` is a non-Portuguese letter; espeak's accent path translates it to the *base* vowel
   phoneme `o` with explicit stress, short-circuiting the following-context rule `o (s_ → =U`.
   The `o` program's `ChangeIfNotStressed(u)` then yields close `u`. espyak treats `ò` as a
   plain `o`, so the `o (s_ → =U` rule fires → phoneme `U` → lax `ʊ`. Proven with the oracle:
   plain `pros` → `pɹˈʊʃ` (identical to espyak's `pròs`), grave `pròs` → `pɹˈuʃ`; `tòs` → `tˈoʃ`,
   `mòs` → `mˈoʃ` confirm the grave forces phoneme `o` regardless of the `s` context. Reachable
   by porting espeak's grave-accent letter path; deferred (one word, high pt-regression risk).
2. **`ru` `a`/`ɑ` (`могла`/`смогла`/`побыла`).** NOT a synthesis allophone. The mechanism is the
   voice file `lang/zle/ru` directive `replace 03 a a#`: in `SubstitutePhonemes`
   (phonemelist.c:85-104), a word-final `a` in a non-primary syllable (flag `0x2`:
   `(stresslevel & 0x7) > 3` skips *stressed* ones) is replaced by phoneme `a#`, which renders
   IPA `a` and — unlike phoneme `a` — has NO `thisPh(isMaxStress) → ChangePhoneme(A)` branch, so
   it never becomes `A`/`ɑ`. For `$u2` `могла` espeak's `SetWordStress(tonic=-1)` leaves the final
   vowel SECONDARY (`unstressed_wd2`=3), the replace fires (3 ≯ 3) → `a#`, and only the later
   `CalcPitches` promotes the stress MARK to primary `ˈ` — after the programs, so `a#` is locked.
   espyak's clause-nucleus re-renders the isolated word with `set_word_stress(tonic=4)`, promoting
   the final vowel to PRIMARY (4) *before* the programs; the replace's `>3` guard then skips it and
   the `a` program fires `ChangePhoneme(A)` → `ɑ`. Verified with an instrumented espeak-ng 1.52
   (`StressCondition`/`InterpretPhoneme`/`SubstitutePhonemes` prints): oracle `ph_list2` carries
   phoneme `a`, sl=3, and it is `SubstitutePhonemes` that swaps it to `a#`. espyak already PARSES
   this directive (`VoiceConfig.replaces`) but never applies it. Reachable, but a byte-exact fix
   for the isolated (nucleus) case is blocked by the clause-tonic ordering above.
3. **Two-level stress: nonsyllabic vowels as pitch syllables** (`la pro`/`prae`/`trans`
   → `pˈrɔ` not `prˈɔ`; `ar ع` → `ˈʕʕˈaːjn`; and the clause-level `de ich habe es`,
   `fr je le` nucleus relocation). espeak runs `SetWordStress` (which EXCLUDES a nonsyllabic
   `@-` from the stress count, dictionary.c GetVowelStress `!phNONSYLLABIC`) and then a
   SEPARATE intonation pass (`count_pitch_vowels`, intonation.c) that counts EVERY `phVOWEL`
   — including nonsyllabic `@-` — as a pitch syllable (`SFLAG_SYLLABLE`, translate.c:618) and
   places the clause tonic there. So the tonic can land on a reduced onset schwa that carries
   no stress and renders as a bare `ˈ` before the following consonant (`p'@-*O` → `pˈrɔ`).
   espyak's nucleus works on the rendered IPA marks of a per-word render, which has already
   collapsed the `@-`; reproducing this needs the per-word render reworked into espeak's
   clause-level phoneme-list model exposing pre-intonation per-syllable stress levels — an
   engine-wide architectural change disproportionate to the handful of affected words.
4. **`ro reacţiona` prefix-stress** (`rˌeaktsjˈona` vs `rˌeaktsjonˈa`): the shared de/nl/af
   `confirm_prefix` branch places the primary one syllable earlier than espyak's stem
   re-translation does; reproducing it needs espeak's exact prefix-confirm loop.
5. **`nl` `nadelige`/`nalatige` oracle `$2`-collapse** (`naːˈə`): a genuine espeak BUG, confirmed
   by instrumenting the oracle. The `$2` word matches the `@) ige [@]` suffix rule and then espeak
   removes the final `-e` and RECURSIVELY re-translates the stem (`Translate 'nadelig'` /
   `Translate 'nalatig'`). Standalone `nadelig` → `naːdˈeːləx` (full, correct), but the recursive
   re-translation *inside* `nadelige` truncates the stem: the oracle's `ph_list2` is only
   `n aː ə` (`d eː l` dropped) → `naːˈə`. This is an oracle self-inconsistency: espyak's default
   engine emits the correct full `naːdˈeːləɣə`. Reproducing the truncation would require porting
   espeak's buggy `RemoveEnding`/suffix-recursion control flow and gating it to `force_compat`;
   deferred (narrow, high risk of truncating other nl `-ige` words).
6. **Base-engine deleted-phoneme / segmentation cases** (e.g. `is gegnum` `hn#` mnemonic
   leak, `ko` Hangul jamo spelling): espeak's segmentation deletes or reorders phonemes via
   synthesis-time state espyak's render does not model.
7. **Clause-level regressive voicing runs after the phoneme programs, not before.**
   espeak calls `SetRegressiveVoicing` on the whole clause list (phonemelist.c:214-216)
   *before* `InterpretPhoneme` executes the phoneme programs. espyak renders word by word,
   so the clause pass (`_apply_cross_word_voicing`) necessarily runs on lists whose programs
   have already fired, and it only rewrites a phoneme where appending the next word changes
   the result. Where a program has already substituted the word-final phoneme, the later
   voicing pass no longer sees the phoneme espeak saw: `pl gnieść wgrał` -> oracle
   `ɡɲʲˈɛʑdʑ vɡrˈaw`, espyak `ɡɲʲˈɛɕtɕ vɡrˈaw` (the word-final `Z;`/`dz;` have already been
   rendered voiceless by their own programs, so the cross-word `v` finds nothing to switch).
   Fixing this needs the per-word render reworked into espeak's clause-level phoneme-list
   model — the same architectural change item 3 above is blocked on.

These put a permanent floor a few hundredths of a percent below a clean byte-for-byte 100%.

---

## Sub-dialect VARIANT system (voices)

`espyak/voice.py` ports espeak's voice/variant mechanism (`LoadVoice`, `voices.c`): a
sub-dialect (`pt-br`, `en-us`, `es-419`, `ca-va`, …) is a small voice/lang file under
`espyak/data/lang/<family>/<code>` that LAYERS over a SHARED base language. The base
translator config comes from the voice's first `language` line (`strtok`'d on `-`: `pt-br`
→ `pt`, `en-us` → `en`); the rules/dict/_list base name is that same value unless a
`dictionary <name>` keyword overrides it (`nb`: `language nb` + `dictionary no` → dict
`no`). The variant then layers: the **phoneme table** (`phonemes <t>`), the **dict
conditionals** (`dictrules N` → `dict_condition` bits selecting `?N` entries in the shared
dict), and **post-translation phoneme `replace`s** (`replace <flags> <old> <new>`, applied
on the final phoneme list with word-end / unstressed / word-start gating, `phonemelist.c:86`).

`test/parity_audit.py --variants --cap 2000` runs each variant's base-language headwords
through `G2P(variant)` and `espeak-ng -v <variant>` so the dialect's `dictrules`/`replace`/
phoneme-table layer is checked, not just the base dict:

```
OVERALL 31389 / 31486 = 99.69%   →   97 mismatches   across 22 variants
```

Per-variant (cap 2000): pt-BR **99.7%**, fr-BE/fr-CH **99.8%**, en-US/en-US-nyc **99.8%**,
en-GB-x-rp/scotland/gbclan/gbcwmd **99.5–99.8%**, en-029 **99.6%**, en-Shaw **99.8%**,
ca-va/ca-nw **99.7%**, ca-ba **99.2%**, cmn-Latn-pinyin **99.9%**, yue-Latn-jyutping
**100%**, vi-VN-x-central/south **100%**, fa-Latn **100%**, ru-LV **99.0%**, es-419
**98.4%**, ru-cl **96.2%**.

**The dialect remainder is base-shared.** The lowest variants are exactly where the base
language is lowest, and the same headwords fail in the base audit: `ru-cl`/`ru-LV` reproduce
`ru` (96.2% — the `a`/`ɑ` reduction + word-initial schwa above), `es-419` reproduces `es`
(98.4% — the abbreviation/letter cases), `ca-ba`/`ca-nw` reproduce `ca`. These are not
variant-layer bugs; they are the base-language fails of buckets A–C surfacing through the
voice. No variant has a fail that the base language does not.

## Prioritized path (most gain first)

1. **Phoneme-level language switch** (A, 29) — the shared-buffer refactor so the source
   post-processor crosses the switch; recovers the `it` Cyrillic-letter block and `nog`.
2. **`LookupDictList` letter-name / abbreviation expansion** (B, 45) — the largest spread,
   one bounded C port covering dotted abbreviations and spelled-letter chains across ~25
   languages.
3. **Unported stress / `phonSYLLABIC` / regressive-voicing arms** (the closable slice of C)
   — `la` onset-cluster stress, `ky` leading secondary, `sr/hr/bs` voicing + syllabic-l.
4. **`numbers.c` branches + `$N` fraction** (D, 10) — Devanagari numerals, `$N` dollar
   fraction.

The clause-tonic-ordering floor (the `pt` grave-accent vowel path, the `ru` `replace 03 a a#`
directive, the `nl` `$2`-collapse bug, the Hangul/segmentation deletions) is deterministic and
G2P-reachable — NOT formant synthesis — but each byte-exact fix is either blocked by the
clause-tonic-before-programs ordering (`ru`, floor #2/#3) or is a narrow, high-regression-risk
port (`pt` accent path; `nl` buggy suffix recursion under `force_compat`). Chase these only
after the buckets above, and only with the clause-level phoneme-list rework in hand.
