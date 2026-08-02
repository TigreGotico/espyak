# espyak

`espyak` is a pure-Python reimplementation of [espeak-ng](https://github.com/espeak-ng/espeak-ng)'s
grapheme-to-phoneme (G2P) front-end. It converts text to phonemes only: no synthesis, no
audio, no C extension, no runtime dependencies.

> `espyak` reproduces the `espeak-ng` binary (pinned **1.52.0**) byte-for-byte. The
> full-headword parity audit (every `*_list` word, `force_compat` mode) reaches **99.71%**
> across 105 languages - **59 at 100%** - and **99.69%** across 22 sub-dialect variants
> (pt-br, en-us, es-419, …). The package bundles 117 languages. [`docs/remaining-gaps.md`](docs/remaining-gaps.md)
> lists the remaining fails.

```python
from espyak import G2P

g2p = G2P("en")
g2p.phonemize("hello world")              # 'həlˈəʊ wˈɜːld'   (IPA)
g2p.phonemize("hello world", ipa=False)   # "h@l'oU w'3:ld"   (Kirshenbaum / -x)

G2P("es").phonemize("buenos días")        # 'bwˈenos dˈias'
G2P("de").phonemize("straße")             # 'ʃtɾˈɑːsə'
G2P("ru").phonemize("привет")             # 'prʲivʲˈet'
```

## Why

`espyak` gives a project espeak-ng's phonemes without the native dependency. There is
nothing to shell out to and no C extension to build, and the rules stay readable and
patchable in Python. It works as a backend for [phoonnx](https://github.com/TigreGotico/phoonnx).

## Install

```bash
pip install -e .          # from a clone (the espeak-ng source data is bundled, ~44 MB)
# or:  uv pip install -e .
```

Python 3.9 or later is required. The espeak-ng `dictsource/`, `phsource/`, and `lang/` data
ship bundled under `espyak/data/` at the pinned `1.52.0` tag, so no system-wide install is
needed.

## Usage

### Python

```python
from espyak import G2P

g2p = G2P("en")                      # one translator per language - construct once, reuse

g2p.phonemize("read")                # 'ɹˈiːd'
g2p.phonemize("2024 dogs")           # numbers expand to words, then phonemes

g2p.phonemize("cat", ipa=True)       # 'kˈat'        - Unicode IPA (default)
g2p.phonemize("cat", ipa=False)      # "k'at"        - Kirshenbaum ASCII (espeak -x)
g2p.phonemize("cat", separator="_")  # 'k_ˈa_t'      - separate phonemes
g2p.phonemize("cat", tie="͡")         # tie multi-char phoneme names
```

### Dialects and sub-dialect variants

A variant code (`pt-br`, `en-us`, `es-419`, `fr-be`, …) loads the same way: pass it to
`G2P`. espeak-ng models a sub-dialect as a small voice file that layers over the shared
base language (its dictionary, rules, and translator config), overriding only the phoneme
table, the dictionary conditionals, and a few post-translation phoneme substitutions:

```python
G2P("pt-br").phonemize("dia")        # 'dʒˈiæ'   - Brazilian di palatalization
G2P("pt").phonemize("dia")           # 'dˈiɐ'    - base (European) Portuguese
G2P("en-us").phonemize("better")     # 'bˈɛɾɚ'   - rhotic, the en-us replace table
G2P("es-419").phonemize("cielo")     # 'sjˈelo'  - seseo (θ→s); base es → 'θjˈelo'
```

The 22 supported variants (codes are case-insensitive):

| family | variants |
| --- | --- |
| en | `en-us`, `en-us-nyc`, `en-gb-scotland`, `en-gb-x-rp`, `en-gb-x-gbclan`, `en-gb-x-gbcwmd`, `en-029`, `en-shaw` |
| ca | `ca-va`, `ca-ba`, `ca-nw` |
| fr | `fr-be`, `fr-ch` |
| pt / es | `pt-br`, `es-419` |
| ru | `ru-cl`, `ru-lv` |
| vi | `vi-vn-x-central`, `vi-vn-x-south` |
| cmn / yue / fa | `cmn-latn-pinyin`, `yue-latn-jyutping`, `fa-latn` |

### Command line

```bash
espyak -v en "hello world"           # həlˈəʊ wˈɜːld
espyak -v es "díganme"               # dˈiɣanme
espyak -v fr -x "bonjour"            # bO~Z'ur    (Kirshenbaum)
espyak -v de --sep _ "haus"          # h_ˈaʊ_s
echo "привет" | espyak -v ru -       # read from stdin
```

### Output formats

| API argument          | CLI flag    | effect |
| --------------------- | ----------- | ------ |
| *(default)*           | `--ipa`     | Unicode IPA with `ˈ`/`ˌ` stress |
| `ipa=False`           | `-x`        | Kirshenbaum ASCII |
| `separator="_"`       | `--sep=_`   | insert a separator between phonemes |
| `tie="͡"`              | `--tie`     | tie character within multi-char names |

`G2P(lang).phonemize(text, ipa=True, tie=None, separator=None)` is the whole surface. See
[`docs/usage.md`](docs/usage.md) for details and `render()` (raw phoneme-string rendering).

## How it works

`espyak` parses espeak-ng's own source data at load time and replays its pipeline in Python:

```
text → dictionary _list lookup → prefix/suffix retranslation → letter-to-sound rules
     → SetWordStress → phoneme programs (ChangePhoneme/InsertPhoneme) → render (IPA / -x)
```

Fidelity comes from the bundled data. The matcher, stress, number, and phoneme-program
logic are re-implemented to match the binary, including espeak-ng's quirks.
[`docs/architecture.md`](docs/architecture.md) has the module map and pipeline.

## Verification

```bash
pytest -q                            # unit + fixture tests
python test/sweep.py 25              # per-language _list-headword sweep vs the oracle
python test/corpus_sweep.py          # real-sentence corpus vs the oracle
python test/parity_audit.py --cap 2000              # full-headword parity, every language
python test/parity_audit.py --variants --cap 2000   # the same for the 22 sub-dialect variants
```

The reference ("oracle") is a pinned `espeak-ng 1.52.0` build, used only to generate
expected outputs. `espyak` never calls it at runtime. Every dictionary `*_list` headword is
a free test case. `parity_audit.py` tests every headword in `force_compat` mode, where the
edge cases (single accented letters, abbreviations, codepoint names) are where parity
breaks, and writes a per-language table plus a JSONL of every mismatch. `--variants` audits
each dialect's base headwords through its voice layer. `test/report.md` holds the
per-language sweep pass rate.

## Coverage

Full-headword parity is **99.71%** (105 languages, `--cap 2000`) and **99.69%** across the
22 variants, with 59 base languages at 100%. The remaining ~136 base fails concentrate in
phoneme-level language switches, letter-name/abbreviation spelling (`LookupDictList`),
unported `numbers.c` branches, and a small irreducible floor (formant-synthesis allophones,
the `ru` `a`/`ɑ` reduction, oracle self-inconsistencies). [`docs/remaining-gaps.md`](docs/remaining-gaps.md)
catalogs, classifies, and prioritizes them. The default engine (`force_compat=False`) is the
linguistically correct G2P, and it deviates from espeak-ng only at the entries in
[`docs/divergences.md`](docs/divergences.md).

## Project layout

```
espyak/            the engine (one module per espeak-ng translation unit)
  api.py           public G2P entry point
  dictionary.py    MatchRule / TranslateRules / SetWordStress / LookupDict2
  rule_compiler.py compiledict.c - rule byte encoding + groups
  phoneme_tab.py   phsource loader; phoneme_program.py - ChangePhoneme/InsertPhoneme
  language_data.py per-language translator config (tr_languages.c + voice files)
  voice.py         sub-dialect VARIANT loader (voices.c LoadVoice) - pt-br/en-us/es-419/…
  numbers.py       TranslateNumber + ordinals/fractions
  render.py        phoneme list → IPA / Kirshenbaum / stress / tie / separator
  data/            bundled espeak-ng dictsource/ phsource/ lang/ @ 1.52.0
docs/              architecture, usage, divergences, remaining-gaps, code-review/
examples/          runnable usage examples
test/              unit tests, oracle fixtures, sweep + corpus + parity_audit harnesses
```

## Provenance

`espyak` is an AI-assisted port. An AI coding assistant wrote the Python after reading and
instrumenting espeak-ng's C source, and human review has been minimal. It is not an
independent clean-room implementation.

## License

`espyak` is GPL-3.0-or-later, the same license as espeak-ng, from which it is derived and
whose data it bundles under `espyak/data/`. See [`LICENSE`](LICENSE).
