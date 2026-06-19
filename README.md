# espyak

**A pure-Python reimplementation of [espeak-ng](https://github.com/espeak-ng/espeak-ng)'s
grapheme-to-phoneme (G2P) front-end.** Text → phonemes only: no synthesis, no audio, no C
extension, no runtime dependencies.

> Reproduces the `espeak-ng` binary (pinned **1.52.0**) byte-for-byte on its test sets — a
> per-language headword sweep (**1703/1703**, 86 languages) and a real-sentence corpus
> (**438/438**, 31 languages). 117 languages bundled. Inputs outside those sets are not all
> covered yet — see [Coverage](#coverage).

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

`espyak` gives projects espeak-ng's phonemes without the native dependency: nothing to
shell out to, no C-extension to build, and the rules are readable and patchable in Python.
It drops in as a backend for [phoonnx](https://github.com/TigreGotico/phoonnx).

## Install

```bash
pip install -e .          # from a clone (the espeak-ng source data is bundled, ~44 MB)
# or:  uv pip install -e .
```

Python ≥ 3.9. The espeak-ng `dictsource/`, `phsource/`, and `lang/` data are bundled under
`espyak/data/` at the pinned `1.52.0` tag, so nothing is needed system-wide.

## Usage

### Python

```python
from espyak import G2P

g2p = G2P("en")                      # one translator per language — construct once, reuse

g2p.phonemize("read")                # 'ɹˈiːd'
g2p.phonemize("2024 dogs")           # numbers expand to words, then phonemes

g2p.phonemize("cat", ipa=True)       # 'kˈat'        — Unicode IPA (default)
g2p.phonemize("cat", ipa=False)      # "k'at"        — Kirshenbaum ASCII (espeak -x)
g2p.phonemize("cat", separator="_")  # 'k_ˈa_t'      — separate phonemes
g2p.phonemize("cat", tie="͡")         # tie multi-char phoneme names
```

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

`G2P(lang).phonemize(text, ipa=True, tie=None, separator=None)` is the whole surface; see
[`docs/usage.md`](docs/usage.md) for details and `render()` (raw phoneme-string rendering).

## How it works

`espyak` parses espeak-ng's own source data at load time and replays its pipeline in Python:

```
text → dictionary _list lookup → prefix/suffix retranslation → letter-to-sound rules
     → SetWordStress → phoneme programs (ChangePhoneme/InsertPhoneme) → render (IPA / -x)
```

Fidelity is inherited from the bundled data; the matcher, stress, number, and
phoneme-program logic are re-implemented to match the binary, espeak-ng's quirks included.
[`docs/architecture.md`](docs/architecture.md) has the module map and pipeline.

## Verification

```bash
pytest -q                            # unit + fixture tests
python test/sweep.py 25              # per-language _list-headword sweep vs the oracle
python test/corpus_sweep.py          # real-sentence corpus vs the oracle
```

The reference ("oracle") is a pinned `espeak-ng 1.52.0` build, used only to generate
expected outputs — `espyak` never calls it at runtime. Every dictionary `*_list` headword
is a free test case; `test/report.md` holds the per-language pass rate.

## Coverage

The headword sweep samples the first *N* **alphabetic, length ≥ 3** headwords per language
(1703 words at N=25); that set and the real-sentence corpus reproduce espeak-ng exactly.
Inputs **outside** those sets can still differ — isolated accented letters spoken as their
name (`á` → "a acute"), bare ordinal suffixes (`th`, `nd`), unicode-codepoint names
(`U+5c1`), and some uncommon words. Raise `N` in `test/sweep.py`, or widen its word filter,
to exercise more of the dictionary.

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
docs/              architecture, usage
examples/          runnable usage examples
test/              unit tests, oracle fixtures, sweep + corpus harnesses
```

## Provenance

`espyak` is an **AI-assisted port**. The Python was written by an AI coding assistant that
read and instrumented espeak-ng's C source; **human review has been minimal**. It is not an
independent clean-room implementation.

## License

`espyak` is **GPL-3.0-or-later**, the same as espeak-ng — from which it is derived and whose
data it bundles under `espyak/data/`. See [`LICENSE`](LICENSE).
