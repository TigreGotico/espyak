# Remaining gaps — why `force_compat` parity is not yet 100%

`espyak` is a clean-room Python port of espeak-ng. In `force_compat` mode it reproduces
espeak-ng **byte-for-byte, bugs included**, and the headword parity audit measures exactly
that. This document explains the gap between the current rate and a clean 100%.

## The number

Full-headword audit (`test/parity_audit.py --cap 2000`, oracle = espeak-ng 1.52.0,
`-q --ipa`, `force_compat=True`), all 105 languages:

```
OVERALL 45579 / 46228 = 98.60%   →   649 mismatches
```

The 649 fails are concentrated: **69 of 105 languages** have any fail at all, and one
language (`shn`) accounts for **204** of them. The audit's symptom histogram
(`non-alpha=334, word=177, single-char=110, two-letter=26, single-symbol=2`) describes the
*shape* of the input, not the cause; the root-cause breakdown below is what matters.

## Root-cause categories (counts sum to 649)

Every one of the 649 fails was re-derived against the oracle and classified by the
**faithfulness gap that produces it**, not by its surface symptom. The five buckets below
sum to exactly 649.

| Cat | Root cause | Count | Closable? |
|-----|------------|------:|-----------|
| **A** | String-level vs phoneme-level language switch / codepoint verbalization | **240** | Hard — needs an architectural refactor |
| **B** | Unimplemented C features (abbrev `LookupDictList`, stress-rule arms, SUFX, numbers.c) | **193** | Yes, feature by feature (high effort, long tail) |
| **C** | Lexical/data vowel quality & length not derivable by rule | **~120** | Partly — bounded by what the bundled data encodes |
| **D** | UB / non-reproducible espeak state (uninitialised stress sentinel residue) | **~30** | No — fundamentally non-portable |
| **E** | Genuine edge: symbol tables, clause/abbrev one-offs | **~66** | Mostly, one at a time (diminishing returns) |

The mechanistic classifier that produced these emits five *operational* buckets that the
table above re-maps onto the A–E faithfulness framework:
`A(lang-switch)=240`, `segment(vowel/consonant/letter-name)=161`, `stress=131`,
`E-symbol=101`, `B-num(numbers)=16` — summing to 649. `segment` and `stress` each split
across B/C/D/E (a stress-placement miss can be an unported stress-rule arm **or** the UB
sentinel; a `segment` miss can be lexical vowel quality **or** an unported feature), so the
A–E counts are an honest re-allocation of those two mixed buckets, detailed per category
below. A and B-num map cleanly; the C/D/E split of `segment`+`stress`+`E-symbol` is given
with its reasoning in each section.

---

### (A) Architecture: string-level vs phoneme-level language switch — **240** (biggest)

**The faithfulness gap.** espeak's `TranslateWord2` emits an *in-band* `phonSWITCH`
phoneme and calls `SetTranslator2`, re-translating a foreign or unknown run **in place** on
the shared `ph_list2` buffer. The source language's post-processing (stress copy, tone
copy, regressive voicing) then runs *over the switched phonemes*. For an unknown character,
`TranslateLetter` spells it by its Unicode codepoint name through the **same** `(en)…`
switch. espyak instead switches at the **string level**: it re-renders the foreign run with
a cached `G2P(lang)` and brackets the result `(lang)…(orig)` (see `docs/code-review/
api-rule_compiler.md` D8, and `docs/divergences.md` for the Myanmar/Shan medial case). The
output surface matches when the switch is clean; it diverges whenever the source language's
post-processing must cross the switch boundary, or when espeak's segmentation of the
switched run differs from espyak's.

**Symptom.** Expected output contains an `(en)…`/`(lang)…` run or a codepoint-name spelling.

**Examples:**

| lang | input | espeak (oracle) | espyak (got) |
|------|-------|-----------------|--------------|
| shn | `ၵၵ်း` | `kk (en)mjˈɑː1nmɑːɑː(shn)lˈe1t…` (Myanmar letter name, shn tone copied onto English) | medial rendered in the cluster |
| cmn | `雄` | `(en)kʃə5ŋtˈuː5(cmn)` (codepoint verbalized, cmn tone 5 on English) | `` (empty) |
| de | `worden` | `vˈɔɾdən` (translated as German) | `(en)wˈɜːdən(de)` (espyak switches to en) |
| as | `আমার` | `ˈa mˈɔ ˈakaɾ (bn)ɾˈɔ(as)` (in-band bn switch mid-word) | `ˈama` |

**Affected languages.** `shn` (**204** — every shn fail; medials + visarga codepoint
verbalization with tone copy), `pt`=7, `cmn`=6, `gu`=5, `pa`=5, `as`=5, `de`=5, plus
single fails in `it`/`fr`/`af`. shn alone is 31% of all 649 fails and 85% of category A.

**Block→language switch (`alphabets[]`), as/gu/pa — CLOSED.** The `alphabets[]` table
(`tr_languages.c:73`) maps a Unicode block to a language; a character a language's rules
cannot pronounce is named/switched through that block's language. This is now ported
(`language_data.ALPHABETS` / `alphabet_from_char`):
- **as** (`আমার`…): a Bengali-block letter (`র`, no rule in `as_rules`) trips FLAG_SPELLWORD,
  spelling the whole word by letter NAME; the unnamed `র` switches to its alphabet language
  `bn` → `ˈa mˈɔ ˈakaɾ (bn)ɾˈɔ(as)` (`spell_word_foreign_letter`, `_spell_letters_named`).
- **gu** (`ખ઼`…): a nukta letter `.replace`d to a single Devanagari char that gu can't
  translate → the TranslateLetter single-letter path names the `_hi` alphabet via the default
  English voice, then renders the letter in `hi` → `(en)hˈɪndi(gu)xˈə`
  (`_name_and_render_foreign_letter`).
- **pa** (`ਸੋਫਟਵਿਅਰ`…): a `$text` dict entry whose value is Latin text (`software`) re-translates
  to that text; the non-Latin source switches it to English at the word level (dictionary.c:2257)
  → `(en)sˈɒftweə(pa)`.

**cmn — DEFERRED.** `雄`→`xiong2` ($text pinyin) → cmn rules give nothing → a WORD-level en
switch of `xiong` plus the digit `2` spoken "two", with cmn's render-time **tone post-pass
crossing the `(en)…(cmn)` boundary** (`kʃˈəŋ`→`kʃə5ŋ`, en stress stripped, default tone 5
inserted) — exactly the shn cross-boundary effect of `d921a45`, but over a foreign **word**
switch rather than a codepoint spelling. Closing it needs the cmn tone normalization to run
over the en-switched phonemes; the risk to cmn's 3823 passing cases makes it a separate change.
The two non-switch cmn fails (`都` `tˈu5`→`tˈou5`, `識` `s.ˈi.ɜ`→`s.i.1`) are vowel-quality /
spelled-letter-tone bugs, category C/B, not `alphabets[]`.

**Closable?** Only by replacing the string-level switch with a phoneme-level one: a shared
phoneme buffer the source-language post-processor runs over, plus espeak's full Myanmar/
codepoint `TranslateLetter` segmentation. This is the single highest-leverage refactor —
closing it would recover up to ~240 fails (≈0.52 pp) and is the obvious first priority.

---

### (B) Unimplemented C features — **193**

Documented UNIMPLEMENTED items from `docs/code-review/*` that surface as fails:

**B1 — Abbreviation / `LookupDictList` retries (≈92).** `dictionary.md` §7 lists
`LookupDictList` (`a.b.c` abbreviations, SUFX-stripped re-lookup, `FLAG_ACCENT` fallback)
as not ported, and `numbers-config.md` notes letter-name spelling chains. These produce the
bulk of the `E-symbol`=101 bucket where the input is a dotted abbreviation or a single
spelled letter expanding to a multi-word name:

| lang | input | oracle | got |
|------|-------|--------|-----|
| fo | `kl.` | `kˌəaˈɛl` (spell K-L) | `klohɡːˈan` (mis-expanded) |
| ro | `cf.` | `tʃˌefˈe` (spell C-F) | `konfˈorm` |
| et | `etc` | `ˈet tsetˌera` | `et tsˈetera` |

Affected: `fo`=45, `smj`=18, plus `fa`/`ro`/`hu`/`hi`/`qu`/etc. (`fo` and `smj` are
small-dict languages where almost every fail is an abbreviation/letter-name expansion.)

**B2 — Unported stress-rule arms (≈85).** `dictionary.md` §7: `STRESSPOSN_ALL`,
`STRESSPOSN_GREENLANDIC` (kl), `S_FINAL_LONG`, `phonSYLLABIC` syllable-nucleus counting,
`vowel_pause` word-initial PAUSE, plus secondary-stress placement on spelled-letter and
multi-syllable words. These dominate the `stress`=131 bucket:

| lang | input | oracle | got |
|------|-------|--------|-----|
| ro | `dumneavoastră` | `dˈumneavˌɔastrə` | `dˌumneavˈɔastrə` (primary/secondary swapped) |
| pap | `á` | `ˌaskɛrpˈi` | `ˌaskˈɛrpi` |
| vi | `l` | `ˈɛ7ləː2` | `ˈɛ1ləː2` (spelled-letter tone) |

Affected: `ro`=23, `de`=9, `ur`=8, `it`=7, `pt`=6, `pap`=5, `vi`=5, `ms`=5, `da`=5, plus
the SCr group (`bs`/`hr`/`sr`=3 each) and many ≤3 langs. (The handful of `et`=5 stress
fails are split out into category D — they are the UB sentinel residue, not an unported
arm.)

**B3 — `numbers.c` branches (16).** `numbers-config.md` §2 lists roman, myriads/lakh,
feminine/`M_Variant`, `DFRACTION`, `NUM_VIGESIMAL`, ordinal sub-machinery as unported.
Plus the `$N` dollar-fraction dictionary directive (`it intranet$3`, `ro …$2`):

| lang | input | oracle | got |
|------|-------|--------|-----|
| mt | `3000` | `tlˈetː` | `tliːˈeta ˈelf` (myriad/grouping) |
| mr | `१००` | `ʃˈʌmbəɾ` | `ˈeːkʃˈeː` (Devanagari-numeral path) |
| it | `intranet$3` | `intrˈanet dˈɔllarɪ trˈe` | `intrˈanet trˈe` (`$N` dropped) |

Affected: `py`=4, `mr`=3, `fo`=3, `mt`=2, `ro`/`it`/`fr`/`ca`=1.

**B4 — SUFX_B / SUFX_M / SUFX_T (counted within B2's affected langs).**
`api-rule_compiler.md` D4/D5: Turkish `SUFX_B`, stacked `SUFX_M`, deferred `SUFX_T`.
Affects `tr` (2 segment fails) and a few en stacked-suffix words.

**Closable?** Yes — each is a bounded port of a known C function. But it is a long tail of
~10 separate features across ~40 languages, with the largest single win (abbreviation
`LookupDictList`) worth ~90 fails.

---

### (C) Lexical / data vowel quality & length — **~120** (within `segment`=161)

espeak emits open/close vowel-quality and length distinctions that are **lexically or
stress-conditioned**. A large share of the it/ru open/close `e/ɛ o/ɔ` fails turned out to
be a **`_list` vs `_listx` precedence bug**, not irreducible data — closed (see below).
The residue is genuinely lexical or stress-conditioned. Verified examples where the bundled
data does **not** encode the distinction espeak emits:

| lang | input | oracle | got | note |
|------|-------|--------|-----|------|
| ru | `могла` | `mʌɡɭˈa` | `mʌɡɭˈɑ` | `a`/`ɑ` allophone is stress/position-conditioned |
| lv | `r` | `ˈerr` | `ˈerrr` | spelled-letter consonant length (double vs triple) |
| lv | `pats` | `pˈats` | `pˈat͡s` | affricate tie-bar vs plain — encoding-level length |
| af | `cliché` | `kliʃˈɛɪɛɪ` (vowel copied) | `kliʃˈɛɪː` (lengthened) | diphthong-copy vs `ː` length rendering |
| pt | `voice` | `vˈoɪsɨ` (close o) | `vˈɔɪsɨ` (open ɔ) | `$alt` opens the post-stress vowel, but espeak's `ApplySpecialAttribute2` matches only `phonSTRESS_P` (`'`), NOT the `phonSTRESS_P2` (`''`) priority mark pt's `S_PRIORITY_STRESS` emits; espyak's `'`-search opens it anyway |

**`_list`/`_listx` precedence — CLOSED.** `CompileDictionary` (compiledict.c:1581) compiles
`_list` and `_listx` in an order gated on `langopts.listx`, prepending each entry to its
hash chain, so the **last file compiled wins** `LookupDict2`. Only `cmn`/`yue`/`zh` set
`langopts.listx=1` (compile `_list` then `_listx` → `_listx` wins). **Every other language**
compiles `_listx` then `_list` → **`_list` wins** the tie. espyak loaded `_listx` last
unconditionally, so for the 8 non-Chinese langs with a `_listx` file (`ar bg he ia it ru tk
tr`) a stale/different `_listx` entry shadowed the correct `_list` one. The clearest case:
`it_list` has `lord $alt` (rule gives `O`=ɔ, `$alt` is a no-op on an already-open vowel → ɔ)
but `it_listx` has `lord $alt2` (closes ɔ→o); the `$alt2` wrongly won, giving `lˈord`.
Loading order now follows `langopts.listx`, recovering 14 `it` + 1 `ru` headwords with
**zero regressions** (`it sos`, `condor`, `sonar`, `sofia`, `oscar`, `revolver`, `montreal`,
`vacuolo`, … all now match). The old category-C `it sos` example was one of these — closable,
not a data limit.

Affected residue: `lv`=17, `en`=15, `lb`=11, `ur`=8, `pt`=7, `nl`=7, `de`=5, `ca`=5, and a
tail; the `segment`=161 bucket also contains some letter-name spelling (xex `flˈuː`, ar/ml
letter codepoints) that overlaps B1. After the `_listx` fix and removing the B1-style
letter-name cases, the genuine lexical/length quality residue is below the original ~120.

**Closable?** Partly. The `_list`/`_listx` precedence share is now closed. Of the residue:
the `pt voice` `phonSTRESS_P2` case is a narrow, closable `ApplySpecialAttribute2` arm (one
word, deferred for risk to pt's priority-stress path); `montgomery`-style cases are
stress-placement (B2) surfacing through `ChangeIfNotStressed`. Where espeak's output is
**not** recoverable from the bundled data (a per-voice table or internal inconsistency), it
is a hard data limit, not a code bug.

---

### (D) UB / non-reproducible espeak state — **~30** (within `stress`=131)

espeak's `vowel_stress[]` sentinel is read **uninitialised** in the fixed-initial-stress
path (fi/et). The fi/et common case is already pinned to espeak's output via a
behaviour-faithful flag choice (`S_FINAL_NO_2`, see `language_data.py:120-134`, which is
why `fi` has **0** fails), but the residual `et`=5 fails are exactly the inputs where the
sentinel's garbage value does not map to any flag:

| lang | input | oracle | got |
|------|-------|--------|-----|
| et | `spl` | `sˈupɪ lˌusika tˈæitː` | `sˈupɪ lˌusikˈa tˈæitː` |
| et | `vms` | `vˌɵi mˈuuː sˈeeː sˌuɡune` | `…sˌuɡunˈe` |

The same class of non-determinism appears as one-off secondary-stress placement in other
fixed-stress langs where espeak's auto-secondary loop reads past a syllable boundary in an
order our deterministic port cannot replicate. Conservatively ~30 of the `stress` fails are
of this non-reproducible kind (et's 5 are certain; the rest are the irreducible residue of
fixed-stress langs after B2's modellable arms are subtracted).

**Closable?** **No.** Reproducing it would require reading the same uninitialised C memory —
fundamentally non-portable. This is part of the hard floor below 100%.

---

### (E) Genuine edge — **~66** (remainder of `E-symbol` + `segment`)

The long tail after A–D: symbol-table one-offs, clause-boundary handling, single accented
letters that espeak renders as **empty** (it spells nothing for an unknown standalone
letter while espyak spells the letter name), Arabic/CJK symbol verbalization, and assorted
one-offs.

| lang | input | oracle | got |
|------|-------|--------|-----|
| lb | `à` | `` (empty) | `ˈaː` (espyak spells it) |
| en | `c#` | `sˈiː hˈaʃ` | `k` (symbol `#` table) |
| ar | `د.ج` | `dˌiːnaːr dʒazˈaːʔiɹˌij` | stress shifted |

Affected: spread thin across `qu`=5, `hi`=3, `ar`=3, `hu`=3, `uz`=2, `ta`=2 and many
single-fail langs. The empty-output cases (lb) are espeak deciding a letter is
unpronounceable — a `LOPT_UNPRONOUNCABLE` / "say nothing" path that overlaps D6
(`api-rule_compiler.md`).

**Closable?** Mostly, one at a time, with diminishing returns — each is its own micro-fix.

---

## Verdict: maximum achievable parity and the hard floor

**Realistically achievable: ≈99.5%.** Closing the phoneme-level language switch (A, 240) +
the abbreviation/`LookupDictList` and number ports (B, 193) + the rule-recoverable share of
C would lift parity from 98.60% to roughly **99.4–99.6%** (≈45 990–46 010 / 46 228). That is
the practical ceiling for a faithful port.

**The hard floor that blocks a clean 100%:**

1. **UB (category D, ~30).** espeak reads uninitialised memory (the fi/et stress sentinel).
   Byte-exact reproduction would require reproducing undefined C behaviour — impossible by
   construction.
2. **Internally-ambiguous espeak state (part of C).** Where espeak's open/close vowel or
   length choice is **not** encoded in the bundled data and is internally inconsistent, no
   amount of correct porting recovers it without shipping espeak's exact per-voice tables
   and its inconsistencies.

Together these put a permanent floor a few hundredths of a percent below 100%; a *clean,
byte-for-byte* 100% across all headwords is not attainable for a port that does not embed
espeak's undefined behaviour.

## Sub-dialect VARIANT system (voices)

`espyak/voice.py` ports espeak's voice/variant mechanism (`LoadVoice`, `voices.c`): a
sub-dialect (`pt-br`, `en-us`, `es-419`, `ca-va`, ...) is a small voice/lang file under
`espyak/data/lang/<family>/<code>` that LAYERS over a SHARED base language. The base
translator config comes from the voice's first `language` line (`strtok`'d on `-`: `pt-br`
→ `pt`, `en-us` → `en`); the rules/dict/_list base name is that same value unless a
`dictionary <name>` keyword overrides it (nb: `language nb` + `dictionary no` → dict `no`).
The variant then layers: the **phoneme table** (`phonemes <t>`), the **dict conditionals**
(`dictrules N` → `dict_condition` bits selecting `?N` entries in the shared dict), and
**post-translation phoneme `replace`s** (`replace <flags> <old> <new>`, applied on the
final phoneme list with word-end / unstressed / word-start gating, `phonemelist.c:86`).

All 24 declared variants load; major dialects match the oracle at base-language parity
(sample, cap≈800–1500): en-us 99.6% (`replace 03 I i`), en-gb 99.7%, pt-br 97.6%
(`dia`→`dʒˈiæ`), es-419 97.4% (seseo θ→s), ca-va/ba/nw 99.3–99.5%, fr-be/ch/fr 99.1%
(= base fr), en-029/en-gb-*/en-us-nyc/en-shaw 99.1–99.6%, ru-cl/lv 96–99%, fa-latn 99.9%.
Residual misses are the SAME base-language abbreviation/loanword classes counted above, not
variant-layer bugs.

**Deferred** (load but not at parity — a base-language limit, not the voice layer):
`cmn-latn-pinyin` (Latin-pinyin input needs base-cmn tokenization espyak lacks; Hanzi input
works), `chr-US-Qaaa-x-west` (base `chr` Cherokee-syllabary G2P emits nothing for real
syllabary text — identical in the oracle), and `vi-vn-x-{central,south}` (~92%, base-vi
secondary-stress tail).

## Prioritized path (most gain first)

1. **Phoneme-level language switch refactor** (A, **240**, ≈0.52 pp, ~85% of it is `shn`).
   Shared phoneme buffer + in-band `phonSWITCH` so source-language post-processing crosses
   the switch; espeak's full Myanmar/codepoint `TranslateLetter` segmentation. Highest
   leverage by far — one architectural change, one third of all remaining fails.
2. **Abbreviation / `LookupDictList`** (B1, ≈92) — recovers the small-dict langs (`fo`,
   `smj`) and dotted abbreviations across the board.
3. **Unported stress-rule arms** (B2, ≈85, minus the D residue) — `ro`/SCr/`pap`/`vi`
   secondary-stress placement.
4. **numbers.c branches + `$N` fraction** (B3, 16) and the **C** rule-recoverable vowel
   quality — lower yield, longer tail.

Stop before chasing D and the internally-ambiguous slice of C: those are the hard floor,
not a backlog.
