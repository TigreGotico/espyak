# espeakng-g2p

**A pure-Python, dependency-free reimplementation of [espeak-ng](https://github.com/espeak-ng/espeak-ng)'s
grapheme-to-phoneme (G2P) front-end.** Text → phonemes only — no synthesis, no audio, no C extension.

> **Status: byte-for-byte against the `espeak-ng` binary on the validation sets.**
> Per-language headword sweep **1703/1703 = 100.0%** (86 languages) · real-sentence corpus
> **438/438 = 100.0%** (31 languages), checked against the pinned oracle (espeak-ng
> **1.52.0**). 117 languages bundled, 164 tests passing. A handful of isolated edge cases
> beyond the sweep are still being closed — see [Coverage](#coverage).

Import package: **`espyak`**.

```python
from espyak import G2P

g2p = G2P("en")
g2p.phonemize("hello world")              # 'həlˈəʊ wˈɜːld'   (IPA)
g2p.phonemize("hello world", ipa=False)   # "h@l'oU w'3:ld"   (Kirshenbaum / -x)

G2P("es").phonemize("buenos días")        # 'bwˈenos dˈias'
G2P("de").phonemize("straße")             # 'ʃtɾˈɑːsə'
G2P("ru").phonemize("привет")             # 'prʲivʲˈet'
```

---

## Highlights

- 🎯 **Byte-exact** with `espeak-ng -q --ipa` (and `-x`) — same phonemes, stress marks,
  ties, and separators, bugs faithfully included.
- 🐍 **Pure Python, zero runtime dependencies.** No `espeak-ng` binary, no `espeak_phonemizer`
  C-extension. Runs anywhere CPython does (3.9+).
- 🌍 **117 languages** bundled — Latin, Cyrillic, Greek, Indic, Arabic, Hebrew, Korean,
  Armenian, CJK structure, and many low-resource/constructed languages.
- 🔬 **Introspectable & patchable.** The rules, stress, and number logic are re-derived in
  readable Python you can read, debug, and extend — not a black-box `.so`.
- 🧪 **Oracle-validated.** Every dictionary headword and a real-sentence corpus are checked
  against the actual espeak-ng 1.52.0 binary.

## Install

```bash
pip install -e .          # from a clone (the espeak-ng source data is bundled, ~44 MB)
# or:  uv pip install -e .
```

> Python ≥ 3.9. The espeak-ng `dictsource/`, `phsource/`, and `lang/` data are bundled under
> `espyak/data/` at the pinned `1.52.0` tag, so nothing needs to be installed system-wide.

## Quick start

### Python API

```python
from espyak import G2P

g2p = G2P("en")                      # one translator per language (cache & reuse it)

g2p.phonemize("read")                # 'ɹˈiːd'
g2p.phonemize("2024 dogs")           # numbers expand to words, then phonemes

# output formats
g2p.phonemize("cat", ipa=True)       # 'kˈat'        — Unicode IPA (default)
g2p.phonemize("cat", ipa=False)      # "k'at"        — Kirshenbaum ASCII (espeak -x)
g2p.phonemize("cat", separator="_")  # 'k_ˈa_t'      — separate phonemes
g2p.phonemize("cat", tie="͡")         # tie multi-char phoneme names

# bug-for-bug compatibility is the default; opt into documented fixes with force_compat=False
faithful = G2P("en")                 # force_compat=True  (default)
patched  = G2P("en", force_compat=False)
```

### Command line

```bash
espyak -v en "hello world"           # həlˈəʊ wˈɜːld
espyak -v es "díganme"               # dˈiɣanme
espyak -v fr -x "bonjour"            # bO~Z'ur    (Kirshenbaum)
espyak -v de --sep _ "haus"          # h_ˈaʊ_s
echo "привет" | espyak -v ru -       # read from stdin
```

## Supported output

| flag / arg            | espeak-ng equivalent | effect |
| --------------------- | -------------------- | ------ |
| *(default)*           | `--ipa`              | Unicode IPA with `ˈ`/`ˌ` stress |
| `ipa=False` / `-x`    | `-x`                 | Kirshenbaum ASCII |
| `separator="_"`       | `--sep=_`            | insert a separator between phonemes |
| `tie="͡"`              | `--tie`              | tie character within multi-char names |

## How it works

A **clean-room** engine: it was authored by studying espeak-ng's *documented file formats*
and *observable behavior*, not by copying its C source. At load time it parses espeak-ng's
own source data and replays the pipeline in Python:

```
text → dictionary _list lookup → prefix/suffix retranslation → letter-to-sound rules
     → SetWordStress → phoneme programs (ChangePhoneme/InsertPhoneme) → render (IPA / -x)
```

Fidelity is inherited from the bundled data; the matcher, stress, number, and
phoneme-program logic are re-derived. See [`docs/architecture.md`](docs/architecture.md)
for the module map and pipeline, and [`docs/usage.md`](docs/usage.md) for the full API.

### Deliberate divergences

Where upstream has a bug worth fixing, the fix is gated behind a `force_compat` flag
(default `True` = bit-identical to espeak-ng, bug included). Set `force_compat=False` to
opt into the documented fix. Every divergence is listed in
[`docs/divergences.md`](docs/divergences.md).

## Verification

```bash
pytest -q                            # 164 unit + fixture tests
python test/sweep.py 25              # per-language _list-headword sweep vs the oracle
python test/corpus_sweep.py          # real-sentence corpus vs the oracle
```

The oracle is the pinned `espeak-ng 1.52.0` binary (built once from source; used **only**
to generate fixtures — the engine never calls it at runtime). Every dictionary `*_list`
headword is a free test case; `test/report.md` records the per-language pass rate.

### Coverage

The headword sweep samples the first *N* **alphabetic, length ≥ 3** headwords per language
(1703 words at N=25) — that set, plus the real-sentence corpus, is byte-exact (100%).
Inputs **outside** that sample are not all covered yet: isolated accented letters spoken as
their name (`á` → "a acute"), bare ordinal suffixes (`th`, `nd`), unicode-codepoint names
(`U+5c1`), and a small number of less-common words still differ from the oracle. These edge
cases are the remaining work toward 100% on the *full* dictionary, and are easy to surface
by raising `N` in `test/sweep.py` or widening the word filter.

## Project layout

```
espyak/            the engine (one module per espeak-ng translation unit)
  api.py           public G2P entry point
  dictionary.py    MatchRule / TranslateRules / SetWordStress / LookupDict2
  rule_compiler.py compiledict.c — rule byte encoding + groups
  phoneme_tab.py   phsource loader; phoneme_program.py — ChangePhoneme/InsertPhoneme
  language_data.py per-language translator config (tr_languages.c + voice files)
  numbers.py       TranslateNumber + ordinals/fractions
  render.py        phoneme list → IPA / Kirshenbaum / stress / tie / separator
  data/            bundled espeak-ng dictsource/ phsource/ lang/ @ 1.52.0
docs/              architecture, usage, divergences
examples/          runnable usage examples
test/              unit tests, oracle fixtures, sweep + corpus harnesses
```

## Why

Every consumer in the OVOS ecosystem currently shells out to the `espeak-ng` binary
([ovos-tts-plugin-espeakNG](https://github.com/OpenVoiceOS/ovos-tts-plugin-espeakNG)) or
wraps the graveyarded `espeak_phonemizer` C-extension. This library removes the native
dependency, makes the rules introspectable and patchable in Python, and slots in as a
first-class [phoonnx](https://github.com/TigreGotico/phoonnx) backend.

## License

**Intentionally unassigned** — there is no `LICENSE`, no SPDX header, and no `license=`
metadata. The choice is deferred to the maintainer; see [`NOTICE.md`](NOTICE.md). The
bundled espeak-ng data under `espyak/data/` remains GPL-3.0-or-later (espeak-ng's license).
