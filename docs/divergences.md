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

## `shn-tone-marks` — Shan tone marks discarded by espeak

**Languages:** `shn` (Shan)

**Input → output:**

| input | default (`espyak`, correct) | `force_compat` / espeak-ng |
|-------|------------------------------|----------------------------|
| ၵႃ   (no mark) | `kˈa1` | `kˈa1` |
| ၵႃႇ  (mark ႇ)  | `kˈa2` | `kˈa1` |
| ၵႃႈ  (mark ႈ)  | `kˈaɜ` (tone 3) | `kˈa1` |
| ၵႃႉ  (mark ႉ)  | `kˈa5` | `kˈa1` |
| ၵႃႊ  (mark ႊ)  | `kˈa6` | `kˈa1` |

**Who is correct:** espyak. The Shan tone marks ႇ/ႈ/း/ႉ/ႊ carry phonemic tone.

**Why espeak is wrong (evidence):** espeak's *own* `dictsource/shn_rules` map each mark to a
tone phoneme — `ႇ → 2`, `ႈ → 3`, `း → 4`, `ႉ → 5`, `ႊ → 6` (lines 348-361). A later step in the
espeak binary discards those tone phonemes and emits the default tone 1 for every syllable
(`espeak-ng -X` on ၵႃႇ shows the mark translated to nothing, output `k'a1`). So espeak contradicts
its own rules — a bug, not an intended design.

**Implementation:** `LANGS["shn"]` is a tone language (`tone_language: 1`), so every syllable gets
a tone (default 1 if unmarked) and the marked tones are kept. The bug is reproduced only under
`force_compat` via `compat_force_tone1` → `_normalize_tones(force_default=True)`, which drops the
mark-derived tones and forces tone 1.

**Not yet replicable (separate espeak shn corruption):** beyond the tone marks, espeak's shn also
garbles some syllables case-by-case (e.g. ၵေး → `ka1e4`: it inserts a phantom `a` and splits the
vowel). That corruption is inconsistent per input and is **not** mirrored; those remain audit
mismatches under `force_compat` and are espeak being broken, not espyak.
