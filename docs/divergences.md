# Justified divergences from espeak-ng

`espyak` aims to reproduce espeak-ng's grapheme-to-phoneme output. The default engine may
deviate from espeak-ng **only when espeak-ng is linguistically wrong** — its output contradicts
the documented phonology or orthography of the language. A purely code-internal inconsistency
("espeak contradicts its own data") is **not** sufficient: the divergence must correct a genuine
**linguistic** error, and must cite an **authoritative external source** (the Unicode Standard, a
reference grammar/phonology, or a recognised standards body) for that linguistic claim.

Two modes:

- **`G2P(lang)` (default, `force_compat=False`)** — the linguistically correct G2P. May deviate
  from espeak-ng exactly at the entries below.
- **`G2P(lang, force_compat=True)`** — byte-for-byte espeak-ng, **bugs included**. The parity
  audit (`test/parity_audit.py`) runs in this mode, so "parity %" measures bug-exact fidelity.

Every deviation must: (1) be gated on `force_compat` so the bug-exact path still matches espeak,
(2) rest on a **linguistic** basis (espeak's output is wrong *about the language*), (3) cite an
**authoritative external source** for that linguistic claim, (4) name the espeak mechanism that is
wrong, (5) show the evidence, (6) be listed here.

---

## `shn-tone-marks` — Shan tone marks mis-classified as separators by espeak

**Languages:** `shn` (Shan)

**Input → output:**

| input | default (`espyak`, correct) | `force_compat` / espeak-ng |
|-------|------------------------------|----------------------------|
| ၵႃ   (no mark) | `kˈa1` | `kˈa1` |
| ၵေး  (mark း)  | `kˈa1e4` | `kˈa1e4` |
| ၵေႇ  (mark ႇ)  | `kˈa1e2` | `k` (vowel dropped) |
| ၵႃႇ  (mark ႇ)  | `kˈa2` | `kˈa1` |

**Who is correct:** espyak (default). The Shan tone marks carry phonemic tone.

**Linguistic basis (authoritative sources):**

- The **Unicode Standard** names these four characters as *tone marks*, not punctuation:
  U+1087 `MYANMAR SIGN SHAN TONE-2`, U+1088 `MYANMAR SIGN SHAN TONE-3`,
  U+1089 `MYANMAR SIGN SHAN TONE-5`, U+108A `MYANMAR SIGN SHAN TONE-6` — Myanmar block
  (U+1000–U+109F), <https://www.unicode.org/charts/PDF/U1000.pdf> (per-character refs e.g.
  <https://www.compart.com/en/unicode/U+1087>). Treating them as clause separators directly
  contradicts their normative Unicode identity as spacing combining **tone** marks.
- **Shan is a tonal language** with five phonemic tones (a sixth used for emphasis / in the north);
  syllable tone is contrastive (minimal pairs differ by tone alone). Wikipedia, *Shan language*
  <https://en.wikipedia.org/wiki/Shan_language>; Omniglot, *Shan* <https://www.omniglot.com/writing/shan.htm>;
  R. Ishida (W3C i18n), *Shan orthography notes* <https://r12a.github.io/scripts/mymr/shn.html>.

Dropping a tone mark therefore loses phonemic information (a different word), so reproducing
espeak's drop is only justified under `force_compat` (bug-exact mode), never by default.

**Why espeak is wrong (evidence):** espeak mis-classifies four of the five tone marks —
ႇ/ႈ/ႉ/ႊ (U+1087-108A) — as clause **separators**, not syllable marks. `espeak-ng -X` on ၵေႇ
splits it into two clauses (`Translate 'ၵေ'` then `Translate 'ႇ'`); the bare `ၵေ` renders as
just `k` (the ေ vowel needs a following element) and the mark renders nothing, so ၵေႇ → `k`.
Only း (U+1038) survives as a real syllable mark (ၵေး → `kˈa1e4`, kept from its dict entry).

**Implementation:** `LANGS["shn"]` is a tone language (`tone_language: 1`); the default engine
keeps the marks and applies their tones. The bug is reproduced only under `force_compat` via
`compat_separators: "ႇႈႉႊ"`, which turns those four chars into word separators before
tokenization, so the syllable splits and the bare vowel drops.

**Long-vowel tone rendering (replicated):** espeak's `--ipa` renders the tone after a vowel
that has an explicit `ipa` string as a COPY of that vowel — ၵႄ → `kˈɛɛ`, ၵၢ → `kaːaː`,
ၵႆ → `kˈəiəi` — while short/mnemonic vowels (no ipa: a/i/u) keep the tone digit (ၵႃ → `kˈa1`).
`force_compat` reproduces this via `compat_long_vowel_tone` (`_shn_long_vowel_tone_copy`); the
default engine keeps the correct tone digit.

**Orphaned-mark codepoint spelling (partly replicated):** when the asat ် (U+103A) splits off as
its own token it can ORPHAN a following mark; espeak's TranslateLetter then spells that mark by its
codepoint — `(en)<Myanmar alphabet name>(shn)<"letter"><hex-digit names>`, e.g. ၵၵ်း →
`kk (en)mjˈɑː1nmɑːɑː(shn)lˈe1təənˈɛɛŋsˈo1nsˈaːaːmpˈɛɛt` ("Myanmar letter 1038"). For the visarga း
(U+1038) this verbalization is a CONSTANT string (the same for every word), so `force_compat`
reproduces it via `compat_spell_orphan_visarga`. Cases where a MEDIAL (e.g. ွ U+103D) is the
orphaned codepoint are NOT replicated: their hex run is position-dependent AND espeak's segmentation
of the medial diverges from espyak's (it renders the medial in the consonant cluster), so both the
prefix and the suffix differ — a faithful fix would need espeak's full Myanmar segmentation plus
phoneme-level language-switching (the (en) Myanmar name carries the shn tone-copy on English
consonants). Those remain `force_compat` mismatches.

---

## `nl-ige-suffix-recursion` — espeak drops the stem body of `nadelige` / `nalatige`

**Languages:** `nl` (Dutch)

**Input → output:**

| input | default (`espyak`, correct) | `force_compat` / espeak-ng |
|-------|------------------------------|----------------------------|
| nadelige | `naːdˈeːləɣə` | `naːˈə` (stem body dropped) |
| nalatige | `naːlˈaːtəɣə` | `naːˈə` (stem body dropped) |
| nadelig  | `naːdˈeːləx` | `naːdˈeːləx` |
| matige   | `mˈaːtəɣə` | `mˈaːtəɣə` |
| zodanige | `zoːdˈaːnəɣə` | `zoːdˈaːnəɣə` |

**Who is correct:** espyak (default). *nadelige* and *nalatige* are the inflected (attributive)
forms of the adjectives *nadelig* "disadvantageous" and *nalatig* "negligent": the stem is fully
pronounced and the inflectional *-e* adds a final schwa, /naːˈdeːləɣə/ and /naːˈlaːtəɣə/. Collapsing
the word to /naːˈə/ deletes the entire stem body (*d eː l* / *l aː t*), producing a non-word.

**Linguistic basis (authoritative sources):**

- Dutch attributive adjective inflection adds a schwa *-e* to the base form; the base is pronounced
  unchanged and *-e* is realised as /ə/. G. Booij, *The Phonology of Dutch* (Oxford, 1995), ch. on
  adjectival inflection; Wikipedia, *Dutch grammar — Adjectives*
  <https://en.wikipedia.org/wiki/Dutch_grammar#Adjectives>.
- Intervocalic *-g-* in *-ige* is the voiced velar fricative /ɣ/. Wikipedia, *Dutch phonology*
  <https://en.wikipedia.org/wiki/Dutch_phonology>.

Deleting the stem body loses all of its phonemes (a different, unpronounceable word), so reproducing
espeak's collapse is only justified under `force_compat`, never by default.

**Why espeak is wrong (mechanism + evidence):** the ending `@) ige (_S1m` is a SUFX_M ("multiple
suffixes") rule. On removing it, espeak re-translates the stem *with want-endings* so a further
suffix can be stripped (translateword.c:496–505), and that re-translation runs the rules with
`FLAG_SUFFIX_REMOVED`. Under that flag a word-initial *prefix* rule can win the match: the stems
`nadelig`/`nalatig` open with the removable `na` prefix (`_) na (C@@P2 → nˈaː`), which now matches as
a two-letter `SUFX_P` ending — `TranslateRules` returns **empty body phonemes** with `nˈaː` carried
in `end_phonemes` and `SUFX_P` set. Because `SUFX_P` is set, espeak's loop performs no further
`RemoveEnding` and never re-appends the stem body, so `AppendPhonemes` yields only that `na`-prefix
fragment plus the outer suffix schwa: `nˈaː` + `ə` → `naːˈə`. `espeak-ng -q -X -v nl nadelige` shows
the stem re-translation stopping after `_) na (` (`Translate 'nadelig'` → `na:'@`). Stems that do
*not* open with a prefix rule (*matige*, *gunstige*, *zodanige*) re-translate in full and are
untouched, so the collapse is not word-specific — it emerges from the prefix/suffix interaction.

**Implementation:** `_translate_with_suffix` (api.py). Under `force_compat` only, when the ending is
`SUFX_M`, the stem is re-translated with `want_endings=True`; if that returns an empty body with
`SUFX_P` set (the `na`-prefix-as-ending case), the stem body is dropped and the word collapses to the
returned prefix fragment plus the outer suffix phonemes. The default engine skips this branch and
re-translates the full stem.
