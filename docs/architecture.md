# Architecture

`espyak` mirrors espeak-ng's grapheme-to-phoneme (G2P) front-end **one module per espeak-ng
translation unit**, so each piece of behavior maps directly back to the reference.

## Pipeline

```
text
 │  word split, charset decode
 ▼
translate word
 ├─ digits ─────────────► numbers.TranslateNumber   (ordinals, fractions, lakh/crore, …)
 └─ else
     ├─ dictionary _list exact-word lookup   (flags, multi-word ||, $text, $abbrev)
     ├─ prefix/suffix retranslation          (strip an ending → look up / re-translate the stem)
     ├─ TranslateRules → MatchRule           (groups1/2/3, pre/post context, $rules, endings)
     ├─ SetWordStress                        (STRESSPOSN_* + syllable weight + auto-secondary)
     └─ phonSWITCH? → re-translate in the switched language (foreign words)
 ▼
phoneme programs   (ChangePhoneme / InsertPhoneme, prevPh/nextPh predicates, AppendPhoneme)
 ▼
render → IPA / Kirshenbaum / stress / tie / separator
```

## Module map

| module | ports (espeak-ng) | responsibility |
| --- | --- | --- |
| `constants.py` | `translate.h` | every `RULE_*`/`FLAG_*`/`STRESSPOSN_*`/`NUM_*` constant — the byte-compatibility backbone |
| `data_paths.py` | — | locates the bundled `dictsource/`, `phsource/`, `lang/`; records the pinned oracle version |
| `phoneme_tab.py` | `synthdata.c` / `phoneme.h` | parse `phsource/phonemes` (+`ph_*` includes): Phoneme/PhonemeTable, inheritance, `ipa` strings, feature keywords |
| `rule_compiler.py` | `compiledict.c` | compile `*_rules`/`*_list` to in-memory rule groups with espeak's exact byte encoding (reversed pre-context, shared phoneme strings, two-letter buckets, `.Lnn` groups) |
| `dictionary.py` | `dictionary.c` | `LookupDict2`, `TranslateRules`, `MatchRule` (the scoring state machine), `SetWordStress`, endings, `GetVowelStress` |
| `phoneme_program.py` | `phonemelist.c` programs | `ChangePhoneme`/`InsertPhoneme`/`AppendPhoneme`, `prevPh`/`nextPh` conditions, place/voicing predicates |
| `language_data.py` | `tr_languages.c` + `lang/` voice files | per-language translator config: stress rule/flags, letter bits, conditions, number system |
| `numbers.py` | `numbers.c` | `TranslateNumber` + ordinals/fractions/romans, decimal-comma, lakh/crore, CJK myriads |
| `render.py` | `dictionary.c` output path | `WritePhMnemonic` + `GetTranslatedPhonemeString` → IPA / Kirshenbaum / stress / tie / separator |
| `api.py` / `__main__.py` | public surface | `G2P(lang).phonemize(...)` / `.render(...)` and the `espyak` CLI |

## The semantics that decide byte-compatibility

1. **`MatchRule` scoring + last-best-wins tie-break.** Per-rule points (~21/letter,
   20/letter-group, +35 two-letter-group bonus, ±score markers, distance penalties) with the
   `points >= best` comparison that lets later rules win ties.
2. **Compiled rule byte layout.** Pre-context stored reversed, shared phoneme strings after
   sorting, two-letter group bucketing, `.Lnn` letter groups stored longest-first.
3. **Byte-level pointer arithmetic.** The matcher steps over `bytes`, not `str`, so multi-byte
   UTF-8 and legacy-charset offsets line up with the C exactly.
4. **Dictionary flag bitfields** — overloaded/context-dependent bits, conditional flags vs
   `dict_condition`, skipword counts, `$text`/`$abbrev`/`$alt`.
5. **`SetWordStress`** — the `STRESSPOSN_*` algorithms, syllable weight, auto-secondary stress,
   and the clause / macron / `||`-multiword interactions.
6. **Phoneme programs** — context-dependent `ChangePhoneme`/`InsertPhoneme` (e.g. en `r` →
   `r/` before a non-vowel; the InsertPhoneme stress transfer behind spelled-acronym vowel
   reduction).
7. **`numbers.c` language branches** and the **`phonSWITCH`** mid-word language switch.

## Verification harness

A pinned `espeak-ng 1.52.0` build is the reference ("oracle"): used only to generate the
expected outputs in `test/fixtures/`; the engine never calls it at runtime. Two sweeps keep
parity honest:

- `test/sweep.py N` — the first `N` headwords of every `dictsource/*_list` (free test cases),
  diffed against `espeak-ng -q --ipa`. **1703/1703** at N=25 across 86 languages.
- `test/corpus_sweep.py` — real sentences across 31 languages. **438/438**.

`test/report.md` holds the per-language pass rate.
