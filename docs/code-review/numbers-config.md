# Code review: `numbers.py` + config vs `numbers.c` / `tr_languages.c` / `translate.h`

Read-only audit of espyak's number translation and per-language configuration
against the espeak-ng C source it ports. espeakng-g2p is a clean-room
reimplementation; this document records correspondence, deviations, and latent
gaps. No engine code was changed.

Sources:

- `espyak/numbers.py` ↔ `oracle/espeak-ng/src/libespeak-ng/numbers.c`
- `espyak/language_data.py` ↔ `oracle/espeak-ng/src/libespeak-ng/tr_languages.c`
  (the `tr_languages.py` named in the brief does not exist — the
  `SelectTranslator` port lives entirely in `language_data.py`)
- `espyak/constants.py` ↔ `oracle/espeak-ng/src/libespeak-ng/translate.h`

---

## 1. `constants.py` ↔ `translate.h`

**Verdict: faithful, 1:1.** Every constant group was grepped from `translate.h`
and compared by name and numeric value:

| Group | Result |
| --- | --- |
| `L()` / `L3()` / `L4()` translator-name macros | match |
| `RULE_*` (1..32, 60) | match |
| `STRESSPOSN_*` (0,1,2,3,4,5,6,7,8,9,12,13,15) | match |
| `S_*` stress_flags (0x02..0x200000) | match |
| `NUM_*` (0x1..0x10000000) | match |
| `NUM_DFRACTION_1..7` | match |
| `NUM2_*` + `NUM2_THOUSANDS_VAR*` / `THOUSANDPLEX_VAR*` | match |
| `BREAK_THOUSANDS/MYRIADS/LAKH*/INDIVIDUAL` | match |
| `LETTERGP_*` (0..7) | match |
| `FLAG_*` dict word1 / word2 / wordflags / suffix | match |
| `DOLLAR_*`, `LOPT_*` (+ `N_LOPTS=18`), `AL_*`, `SAYAS_*`, `CLAUSE_*` | match |
| `N_WORD_PHONEMES`/`N_WORD_BYTES`/… size constants | match |

No deviations. `phonSTRESS_*` are intentionally `None` (resolved at
phoneme-table load), which mirrors upstream's load-time mnemonic lookup.

---

## 2. `numbers.py` ↔ `numbers.c`

### What is ported

`numbers.py` implements the **common cardinal path** of
`TranslateNumber_1` → `LookupNum3` → `LookupNum2`:

- units/teens (`_0`.._19), tens (`_Nx`), exact-ten lexical forms (`_Nx`/full),
  hundreds (`_0c`, lexical `_NC`/`_NC0`), magnitudes (`_0m1`.._0m10).
- decimal part → `_dpt` then each fraction digit individually.
- ordinals (`translate_ordinal`): cardinal high part + ordinal stem (`_No`) +
  suffix ending (`_#st` etc.).
- flag-driven variants actually honoured: `NUM_SWAP_TENS`, `NUM_AND_UNITS`,
  `NUM_HUNDRED_AND`, `NUM_OMIT_1_HUNDRED`, `NUM_OMIT_1_THOUSAND`,
  `NUM_SINGLE_STRESS`, `NUM_DECIMAL_COMMA` (via `decimal_sep` from the caller),
  and the `_Na` ("ein" before magnitude) digit variant.

Key-casing is correct: `numbers.py` lowercases lookup keys (`"_" + key.lower()`)
and the dictionary keys everything lowercase, so `_0M1`/`_0C`/`_Nx` source
fragments resolve from the lowercase `_0m1`/`_0c` keys the port emits.

`NUM_SINGLE_STRESS` semantics match: C scans from the end keeping the **last**
primary stress, demoting earlier `phonSTRESS_P` to `phonSTRESS_3` (secondary);
`_single_stress()` keeps the last `'` and demotes earlier ones to `,`.

### Unported number-language branches (UNIMPLEMENTED)

The per-language `NUM_*`/`NUM2_*` machinery of `numbers.c` that `numbers.py`
does **not** model (documented in the module docstring as future work):

- **Roman numerals** — `TranslateRoman`, `NUM_ROMAN*` (whole function absent).
- **Myriads / lakh-crore grouping** — `BREAK_*`, `NUM2_MYRIADS`, `group_len=4`;
  the port always groups in plain thousands.
- **Thousands variants / feminine forms** — `M_Variant()` (ru/cs/sk/pl/lt/sr-bs-hr
  `0MA`/`0MB`/`1MA`/`1M`), `_Nf`/`_Nfx` feminine digits, `NUM2_THOUSANDS_VAR*`,
  `NUM2_SWAP_THOUSANDS`.
- **Locale decimal-fraction modes** — `NUM_DFRACTION_1..7` (it/pl/ro/hu/kk/si
  "hundredths/tenths" suffixes, `_0Z%d`); the port only ever reads the fraction
  as single digits.
- **`NUM_ZERO_HUNDRED`** (vi "zero hundred"), **`NUM_VIGESIMAL`** (60+13),
  **`NUM_SINGLE_AND`**, the `NUM_AND_HUNDRED` / `NUM_THOUSAND_AND` /
  `NUM_HUNDRED_AND_DIGIT` distinctions (only the umbrella `NUM_HUNDRED_AND`
  placement is modelled), **`NUM_SINGLE_VOWEL`**, **`NUM_SINGLE_STRESS_L`**.
- **Ordinal sub-machinery** — `NUM2_MULTIPLE_ORDINAL`, `NUM2_NO_TEEN_ORDINALS`,
  `NUM2_ORDINAL_*`, `_ord`/`_ord20` fallback endings, the hu `_Ne`-variant path,
  the an `_x#`/`ph_ordinal2x` alternate, `CheckDotOrdinal`.
- **Leading-zero speaking**, **`_%ldn`** isolated-number lookup (kl),
  **dict-list digit combos** (`LookupDictList`), **`NUM2_PERCENT_BEFORE`** (si),
  **`speak_missing_thousands`** higher-order repeat logic, trailing pause
  insertion (`str_pause`).

These are **JUSTIFIED omissions** of an explicitly-scoped subset, **but** they
become **per-language UNIMPLEMENTED gaps** wherever a language's `numbers`
bitfield in `tr_languages.c` requests them (see §3, the "numbers" column).

### `numbers.py` — verdict

No correctness bug found in the implemented common path. The divergence is one
of **coverage**, not of wrong output, and is faithfully documented in-module.

---

## 3. `language_data.py` ↔ `tr_languages.c` (`SelectTranslator`)

### Defaults

`DEFAULTS` matches `NewTranslator` exactly: `stress_rule=STRESSPOSN_2R`,
`stress_flags=0`, `unstressed_wd1=1`, `unstressed_wd2=3`,
`max_initial_consonants=3`, `numbers≈NUM_DEFAULT`, and the eight `SetLetterBits`
groups A/B/C/H/F/G/Y/VOWEL2 are byte-identical.

### Spot-check correspondence (the brief's representative set)

| Lang | stress_rule | stress_flags | regression | numbers | Verdict |
| --- | --- | --- | --- | --- | --- |
| **en** | 1L ✓ | 0x08 ✓ | – | (default) | match |
| **es** | 2R ✓ | SPANISH\|FDO\|FN2 ✓ | – | subset of C (drops ROMAN/ROMAN_AFTER/DFRACTION_4) | match + JUSTIFIED number subset |
| **an** | 2R ✓ | SPANISH\|FDO\|FN2 ✓ | – | **no entry** (C: SINGLE_STRESS\|DEC_COMMA\|AND_UNITS\|OMIT_1H\|OMIT_1T\|ROMAN\|ROMAN_ORDINAL) | stress match; numbers UNIMPLEMENTED |
| **ca** | 2R ✓ | +NO_AUTO_2\|FIRST_PRIMARY ✓ | – | (default) | match |
| **de** | 1L ✓ | 0 ✓ | 0x100 ✓ | SWAP_TENS\|DEC_COMMA (C also ALLOW_SPACE\|ORDINAL_DOT\|ROMAN) | match + JUSTIFIED number subset |
| **lv** | 1L ✓ | NO_AUTO_2\|FD\|FDO\|EO_CLAUSE1 ✓ | – | **no entry** (C: DEC_COMMA\|OMIT_1H\|DFRACTION_4\|ORDINAL_DOT) | stress match; numbers UNIMPLEMENTED |
| **ms** | 2R ✓ | FDO\|FN2 ✓ | – | DEC_COMMA\|ALLOW_SPACE\|ROMAN ✓ | match |
| **pl** | 2R ✓ | **0 (C: S_FINAL_DIM_ONLY)** | 0x9 ✓ | **no entry** (C: DEC_COMMA\|ALLOW_SPACE\|DFRACTION_2) | **POTENTIAL-BUG (stress_flags)** + numbers UNIMPLEMENTED |
| **sr/hr/bs** | 1L ✓ | S_FINAL_NO_2 ✓ | **0 (C: 0x3)** | **no entry** (C: rich SINGLE_STRESS\|HUNDRED_AND\|… set) | **POTENTIAL-BUG (regression)** + numbers UNIMPLEMENTED |
| **eu** | EU(15) | FVU\|MID_DIM ✓ | – | (default) (C: SINGLE_STRESS\|DEC_COMMA\|HUNDRED_AND\|OMIT_1H\|OMIT_1T\|VIGESIMAL) | stress JUSTIFIED (rule 15 from voice file `lang/eu`); numbers UNIMPLEMENTED |
| **bn** | 1L ✓ | S_MID_DIM\|S_FINAL_DIM ✓ | – | **no entry** (C: SWAP_TENS + BREAK_LAKH_BN) | stress match; numbers UNIMPLEMENTED |
| **cs** | 1L ✓ | FDO\|FN2 (0x16) ✓ | 0x3 ✓ | (number subset) | match (reference: correctly-ported Slavic, contrast to pl/sr) |

`FDO=S_FINAL_DIM_ONLY 0x06`, `FN2=S_FINAL_NO_2 0x10`, `FD=S_FINAL_DIM 0x04`,
`FVU=S_FINAL_VOWEL_UNSTRESSED 0x100`.

The stress half of the port is strong: stress_rule and stress_flags match the C
switch arm (or a documented voice-file override) for every spot-checked language
except the two flagged below.

### Cyrillic / Greek / Indic / Arabic / Armenian / Korean script blocks

The `_cyrillic_config`, `_greek_config`, `_indic_config`, Arabic, Armenian and
Korean letter-bit builders reproduce the `SetCyrillicLetters` /
`SetGreekLetters` / `SetIndicLetters` / `SetArabicLetters` offset tables and the
per-language stress rules/flags. Spot-checked: ru/uk syllable-count + iotated-Y
group, el 2R + FDO, ar 3R, bn Indic stress. These match. One minor sub-detail:
the C `bn`/`as` arm applies extra `SetLetterBitsRange`/`SetLetterBits` overrides
on top of `SetIndicLetters` (candranindu → B, vowel-signs → F, `bn_consonants2`
→ C) that the generic `_indic_config` does not special-case; this is a
fine-grained letter-classification divergence, not a stress/number one.

---

## 4. Deviation classification

### POTENTIAL-BUG (flagged — verified live)

Both fields below are read by the live engine (`dictionary.py` `SetWordStress`
reads `stress_flags`; `api.py:992` reads `regression`), so these are not
cosmetic. Both contradict the otherwise-correct Slavic pattern (cf. `cs`, which
sets both correctly).

1. **`pl` is missing `stress_flags = S_FINAL_DIM_ONLY` (0x06).**
   `tr_languages.c` Polish sets `stress_flags = S_FINAL_DIM_ONLY`; the Python
   `pl` entry sets `stress_rule`, `extra_vowels`, `set_letter_bits('y')` and
   `regression=0x9` but **no `stress_flags`**, so it falls to `0`. Effect:
   Polish unstressed final syllables are not marked diminished.

2. **`sr` / `hr` / `bs` are missing `regression = 0x3` (LOPT_REGRESSIVE_VOICING).**
   `tr_languages.c` Serbian (shared by hr/bs) sets
   `param[LOPT_REGRESSIVE_VOICING] = 0x3`; the three Python entries set
   `stress_*`, `spelling_stress`, `extra_consonants`, `unstress_u_words` but
   **no `regression`** → defaults to `0`. Effect: no regressive voicing
   assimilation. Note `cs` and `sk` (same Slavic family) *do* set `0x3`,
   confirming this is an oversight rather than an intentional choice.

### JUSTIFIED

- `numbers.py` implemented-path omissions of the non-common `NUM_*`/`NUM2_*`
  branches (§2), documented in-module.
- Per-language `numbers` bitfields trimmed to the ported subset where the only
  dropped flags are unimplemented features (es/de drop ROMAN/ALLOW_SPACE/
  ORDINAL_DOT/DFRACTION — features absent from the engine anyway).
- `eu` `stress_rule=EU(15)`, and the other voice-file-derived stress rules
  (`fi`/`et`/`ur`/`chr`/`piqd`/`quc`/`py` etc.) — folded in from `lang/<code>`
  voice files, a deliberate and documented enrichment over the bare C switch.
- `sa`, `haw` Python entries — no C `SelectTranslator` arm (they default in C);
  the port legitimately adds them via Indic config / a special macron rule.

### UNIMPLEMENTED (per-language number coverage)

Languages whose `tr_languages.c` arm sets a non-trivial `numbers` bitfield but
whose Python config either has no `numbers` key or only the common flags, so the
language silently uses `NUM_HUNDRED_AND`: **an, lv, bn, eu, pl, sr/hr/bs** (from
the spot-check) and most other entries lacking a `numbers` key. Output is still
produced (basic cardinals), just without the language's roman/lakh/decimal-mode/
ordinal specifics. This is the same coverage gap as §2, surfaced per language.

---

## 5. Missing `LANGS` entry but **has** a `tr_languages.c` arm (latent gaps)

These languages have a real `SelectTranslator` arm in C but **no key in
`LANGS`**, so `get_config()` falls through to `DEFAULTS` (English-like 2R,
flags=0) — the exact latent gap `an`/`ms` had before this session. Ordered by
value (a cheap future win = an arm that overrides stress_rule/stress_flags away
from the default):

| Lang | C arm sets | Cheap win? |
| --- | --- | --- |
| **nb** (Norwegian Bokmål) | `stress_rule=1L`, `SetLetterVowel('y')`, numbers | **YES** — wrong 2R default today |
| **id** (Indonesian) | shares **ms** block: `2R`, `S_FINAL_DIM_ONLY\|S_FINAL_NO_2`, numbers | **YES** — identical to ms, auto-secondaries final syllable today |
| **ia** (Interlingua) | shares **es** block: `2R`, `S_FINAL_SPANISH\|FDO\|FN2`, numbers | **YES** — like `an` was; copy the es flags |
| **gn** (Guarani) | `stress_rule=1R` (final) | **YES** — wrong 2R default |
| **om** (Oromo) | `2R`, `S_FINAL_DIM_ONLY\|S_FINAL_NO_2\|S_FINAL_LONG(0x80000)` | **YES** — flags missing |
| **sw** (Swahili) / **tn** (Setswana) | `2R`, `S_FINAL_DIM_ONLY\|S_FINAL_NO_2` | **YES** — flags missing (rule already default) |
| **kl** (Greenlandic) | `stress_rule=STRESSPOSN_GREENLANDIC(12)`, `S_NO_AUTO_2` | medium — needs the special rule-12 stressor |
| **zh** (Chinese compat) | `stress_rule=1R`, `S_NO_DIM`, `NUM2_ZERO_TENS` | medium (cmn already present; zh is a back-compat alias) |
| **hak** (Hakka) | `S_NO_DIM`, `tone_numbers=1` | low — tone-number Chinese variant |
| **mt** (Maltese) | `2R` (== default), encoding, numbers | low — stress already correct by default |
| **fa** (Farsi) | only `numbers = AND_UNITS\|HUNDRED_AND` (stress = default) | low — stress already correct; numbers UNIMPLEMENTED |
| **ky** (Kyrgyz) | `numbers = NUM_DEFAULT` only | none — no override |
| **ltg** (Latgalian) | shares **lv** block | low — add as lv alias |
| **mi, qu, th, uz, xex** | `numbers = 0` (disabled until _list complete in espeak itself) | none — espeak itself leaves these incomplete |
| **yue** (Cantonese) | shares cmn/zh tone block | low — alias |

**Highest-value cheap wins: `nb`, `id`, `ia`, `gn`, `om`, `sw`/`tn`** — each is
a one-entry copy of an existing pattern (es/ms block or a single stress_rule/
stress_flags pair) that today silently mis-stresses rules-based words via the 2R
default.

---

## Summary counts

- **constants.py:** 0 deviations (faithful 1:1 with `translate.h`).
- **POTENTIAL-BUG:** 2 (counting sr/hr/bs as one shared block).
  - `pl` missing `stress_flags = S_FINAL_DIM_ONLY`
  - `sr`/`hr`/`bs` missing `regression = 0x3`
- **JUSTIFIED:** the implemented-path number subset, the trimmed per-language
  `numbers` bitfields, voice-file stress-rule enrichment (eu et al.), and the
  Python-only `sa`/`haw` entries.
- **UNIMPLEMENTED:** the non-common `numbers.c` branches (roman, myriads/lakh,
  thousands/feminine variants, locale decimal modes, ordinal sub-machinery,
  vigesimal, zero-hundred, …) — surfaced per-language for **an, lv, bn, eu, pl,
  sr/hr/bs** and every other entry lacking a `numbers` key.
- **Missing-entry latent gaps (have C arm, no `LANGS` key):** nb, id, ia, gn,
  om, sw, tn, kl, zh, hak, mt, fa, ky, ltg, mi, qu, th, uz, xex, yue. Top cheap
  wins: **nb, id, ia, gn, om, sw, tn**.
