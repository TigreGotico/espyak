# Remaining gaps — why `force_compat` parity is not yet 100%

`espyak` is a clean-room Python port of espeak-ng. In `force_compat` mode it reproduces
espeak-ng **byte-for-byte, bugs included**, and the headword parity audit measures exactly
that. This document is the per-fail ledger: it accounts for every remaining mismatch and
separates the systematic-deferred ones (a known C feature, closable feature-by-feature)
from the IRREDUCIBLE floor (UB / formant-synthesis allophones / oracle self-inconsistency
that no port can recover).

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
| ru | `могла` | `mʌɡɭˈa` | `mʌɡɭˈɑ` | `a`/`ɑ` stress/position allophone (irreducible) |
| ru | `радио` | `rˈɑdʲɪo` | `ərˈɑdʲɪo` | spurious word-initial schwa |
| tr | `ben` | `bˈæn` | `bˈɛn` | `e`/`æ` lexical vowel |
| la | `pro` | `pˈrɔ` | `prˈɔ` | onset-cluster stress placement (`pˈr` vs `prˈ`) |
| sr/hr/bs | `uxd` | `ˈuˌɪkzdˌə` | `ˈuˌɪɡzdˌə` | `kz`/`ɡz` voicing assimilation |
| sr/hr/bs | `sl` | `sˈəlˌə` | `sˈl̩` | syllabic-l spell vs nucleus |
| cs | `byl` | `bˈil` | `bˈil̩` | syllabic-l render |
| da | `barrikade` | `bˈɑʔikaaðə` | `bˌɑʔikˈaaðə` | primary/secondary placement |
| ky | `эмнеге` | `ˌemneɡˈe` | `emneɡˈe` | missing leading secondary |
| is | `vegna` | `ʋˈɛɡna` | `ʋˈɛɡhn#a` | `gn` cluster (mnemonic `hn#` leaks) |
| af | `cliché` | `kliʃˈɛɪɛɪ` (vowel copied) | `kliʃˈɛɪː` (lengthened) | diphthong-copy vs `ː` |
| pt | `pròs` | `pɹˈuʃ` | `pɹˈʊʃ` | formant-synthesis allophone (irreducible) |
| cmn | `都` | `tˈou5` | `tˈu5` | spelled-letter vowel quality |
| it | `й` | `ɪ brevˈe` | `ɪ brˈeve` | Cyrillic letter-name `@-` reduction / name stress |

**Closable share.** The onset-cluster stress (`la pro`/`prae`/`trans`), the missing leading
secondary (`ky`), the syllabic-consonant render (`cs`/`sr` `sl`/`byl`), and the voicing
assimilation (`sr/hr/bs uxd`) are rule-modellable — unported stress-rule arms and
`phonSYLLABIC` / regressive-voicing details (`dictionary.md` §7). These are
systematic-deferred, not floor.

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

## The irreducible floor

Inside bucket C (and a slice of A) sit the cases that no faithful port can recover, because
the target output is not a function of the input plus the bundled data:

1. **`pt pròs` / `experts` formant-synthesis allophones.** The `o (s_ -> =U` mnemonic `U`
   is rendered `u` (close) by espeak's WAV/FMT synthesis pass in full-word context, and `ʊ`
   (lax) when the mnemonic is fed via `[[…]]`; the oracle itself disagrees with its own
   `-q` mnemonic. `experts` is the same class (`t`+`s#` → affricate `tʃ` only under
   synthesis). espyak renders the mnemonic deterministically and cannot reproduce the
   synthesis-pass branch.
2. **`ru` `a`/`ɑ` reduction (`могла`/`смогла`/`побыла`).** A stress/position-conditioned
   allophone espeak emits from internal state the bundled `ru` data does not encode by rule.
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
5. **`nl` `nadelige`/`nalatige` oracle `$2`-collapse** (`naːˈə`): espeak collapses the word
   to two phonemes via a `$2`/suffix interaction that is an oracle self-inconsistency — the
   bundled rules pronounce the full word, the binary truncates it.
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

Stop before chasing the irreducible floor (the formant-synthesis allophones, the `ru`
reduction, the oracle `$2`-collapse, the Hangul/segmentation deletions): those are the hard
floor, not a backlog.
