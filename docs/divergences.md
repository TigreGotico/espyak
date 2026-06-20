# Justified divergences from espeak-ng

`espyak` aims to reproduce espeak-ng's grapheme-to-phoneme output. Where espeak-ng is
**demonstrably wrong** (it contradicts its own data, or produces linguistically incorrect
output), the default engine does the **correct** thing instead and records the deviation here.

Two modes:

- **`G2P(lang)` (default, `force_compat=False`)** — the linguistically correct G2P. May deviate
  from espeak-ng exactly at the entries below.
- **`G2P(lang, force_compat=True)`** — byte-for-byte espeak-ng, **bugs included**. The parity
  audit (`test/parity_audit.py`) runs in this mode, so "parity %" measures bug-exact fidelity.

Every deviation must: (1) be gated on `force_compat` so the bug-exact path still matches espeak,
(2) name the espeak mechanism that is wrong, (3) show the evidence, (4) be listed here.

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

**Not yet replicable (remaining shn quirk):** some shn words trigger an English language-switch
in espeak, producing garbled mixed output (e.g. ၵိုဝ်း → a long spurious English run). That is
not mirrored; those remain `force_compat` mismatches.
