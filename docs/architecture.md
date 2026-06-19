# Architecture

`espyak` is a clean-room re-implementation of espeak-ng's grapheme-to-phoneme (G2P)
front-end. The design goal is a **1:1 mapping to espeak-ng's translation units** so that
behavior is easy to compare against the reference and divergences are easy to spot.

## Pipeline

```
text
 │  readclause / word split, charset decode, SSML, [[…]] phoneme mode
 ▼
TranslateWord
 ├─ digits ─────────────► numbers.TranslateNumber  (ordinals, fractions, lakh/crore, …)
 └─ else
     ├─ dictionary._list exact-word lookup  (flags, multi-word ||, $text, $abbrev)
     ├─ prefix/suffix retranslation         (remove ending → look up / re-translate stem)
     ├─ dictionary.TranslateRules → MatchRule   (groups1/2/3, pre/post context, $rules, endings)
     ├─ dictionary.SetWordStress             (STRESSPOSN_* + syllable weight + auto-secondary)
     └─ phonSWITCH? → re-translate in the switched language (foreign words)
 ▼
phoneme programs (ChangePhoneme / InsertPhoneme, prevPh/nextPh predicates, AppendPhoneme)
 ▼
render.GetTranslatedPhonemeString → IPA / Kirshenbaum / stress / tie / separator
```

## Module map

Each module ports one espeak-ng translation unit:

| module | ports (espeak-ng) | responsibility |
| --- | --- | --- |
| `constants.py` | `translate.h` | every `RULE_*`/`FLAG_*`/`STRESSPOSN_*`/`NUM_*` constant — the byte-compat backbone |
| `encoding.py` | charset decode | UTF-8 + legacy charsets (ISO-8859-x, KOI8-R, …) |
| `phoneme_tab.py` | `synthdata.c` / `phoneme.h` | parse `phsource/phonemes` (+`ph_*` includes): Phoneme/PhonemeTable, inheritance, `ipa` strings, feature keywords |
| `rule_compiler.py` | `compiledict.c` | compile `*_rules`/`*_list` to in-memory rule groups with espeak's exact byte encoding (reversed pre-context, shared phoneme strings, two-letter buckets, `.Lnn` groups) |
| `dictionary.py` | `dictionary.c` | `LookupDict2`, `TranslateRules`, `MatchRule` (the scoring state machine), `SetWordStress`, endings, `GetVowelStress` |
| `phoneme_program.py` | `phonemelist.c` programs | `ChangePhoneme`/`InsertPhoneme`/`AppendPhoneme`, `prevPh`/`nextPh` conditions, place/voicing predicates |
| `tr_languages.py` + `language_data.py` | `tr_languages.c` SelectTranslator + `lang/` voice files | per-language translator config (stress rule/flags, letter bits, conditions, numbers) |
| `numbers.py` | `numbers.c` | `TranslateNumber` + ordinals/fractions/romans, decimal-comma, lakh/crore, CJK myriads |
| `readclause.py` | `readclause.c` | ReadClause, SSML, `[[…]]` phoneme mode |
| `render.py` | `dictionary.c` output path | `WritePhMnemonic` + `GetTranslatedPhonemeString` → IPA / Kirshenbaum / stress / tie / separator |
| `api.py` | public surface | `G2P(lang).phonemize(...)` / `.render(...)` |

## The hardest semantics to reproduce

These are what decide byte-compatibility:

1. **`MatchRule` scoring + last-best-wins tie-break.** Per-rule points (~21/letter,
   20/letter-group, +35 two-letter-group bonus, ±score markers, distance penalties) and the
   `points >= best` comparison that makes later rules win ties.
2. **Compiled rule byte layout.** Pre-context stored reversed, shared phoneme strings after
   sorting, two-letter group bucketing, `.Lnn` letter groups stored longest-first.
3. **Byte-level pointer arithmetic.** The matcher steps over `bytes`, not `str`, so multi-byte
   UTF-8 and legacy-charset offsets match C exactly.
4. **Dictionary flag bitfields** — overloaded/context-dependent bits, conditional flags vs
   `dict_condition`, skipword counts, `$text`/`$abbrev`/`$alt`.
5. **`SetWordStress`** — `STRESSPOSN_*` algorithms, syllable weight, auto-secondary stress,
   and the clause/macron/`||`-multiword interactions.
6. **Phoneme programs** — context-dependent `ChangePhoneme`/`InsertPhoneme` (e.g. en `r` →
   `r/` before a non-vowel; the InsertPhoneme stress-transfer behind spelled-acronym
   diminishing).
7. **`numbers.c`** language branches and **`phonSWITCH`** mid-word language switch.

## `force_compat`

Every deliberate deviation from upstream (to fix an espeak-ng bug) is gated:

```python
if force_compat:
    ...  # bit-exact espeak-ng output, bug included
else:
    ...  # documented fix
```

`force_compat` defaults to `True`, so out of the box `espyak` is bit-identical to
espeak-ng 1.52.0. Each divergence is registered and documented in
[`divergences.md`](divergences.md).

## Verification harness

The pinned `espeak-ng 1.52.0` binary is the **oracle**: built once from source and used only
to generate fixtures (`test/fixtures/`). The engine never calls it at runtime. Two sweeps
keep parity honest:

- `test/sweep.py N` — the first `N` headwords of every `dictsource/*_list` (free test cases),
  compared to `espeak-ng -q --ipa`. Currently **1703/1703 = 100.0%** at N=25 across 86 langs.
- `test/corpus_sweep.py` — hand-built real sentences across 31 langs. Currently **438/438 =
  100.0%**.

`test/report.md` is regenerated with the per-language pass rate.
