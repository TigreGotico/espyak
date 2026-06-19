# Usage

## Install

```bash
pip install -e .        # from a clone; the espeak-ng data is bundled under espyak/data/
# or:  uv pip install -e .
```

Python ≥ 3.9, no runtime dependencies.

## The `G2P` class

```python
from espyak import G2P

g2p = G2P(lang="en")
```

- **`lang`** — an espeak-ng language/voice code (`"en"`, `"es"`, `"ru"`, `"hi"`, `"ar"`, …).
  See `espyak/data/dictsource/*_rules` for the full list (117 languages).

Construct one `G2P` per language and reuse it — construction parses that language's rule
data, so it is not free.

### `phonemize(text, ipa=True, tie=None, separator=None)`

Translate text to a phoneme string.

```python
g2p = G2P("en")
g2p.phonemize("hello world")               # 'həlˈəʊ wˈɜːld'
g2p.phonemize("hello world", ipa=False)    # "h@l'oU w'3:ld"  (Kirshenbaum, like espeak -x)
g2p.phonemize("read it", separator="_")    # 'ɹ_ˈiː_d ˈɪ_t'
```

| argument    | default | meaning |
| ----------- | ------- | ------- |
| `text`      | —       | input text (numbers are expanded to words) |
| `ipa`       | `True`  | `True` → Unicode IPA (`--ipa`); `False` → Kirshenbaum ASCII (`-x`) |
| `tie`       | `None`  | tie character inserted between the letters of a multi-char phoneme name |
| `separator` | `None`  | character inserted between phonemes (mutually exclusive with `tie`) |

### `render(phoneme_string, ipa=True, tie=None, separator=None)`

Render a raw espeak phoneme-mnemonic string (the content of `[[…]]`) without running the
letter-to-sound rules — the inverse of the matcher, useful for testing the output path.

```python
G2P("en").render("h@l'oU")                 # 'həlˈəʊ'
```

## Command line

The package installs an `espyak` console script:

```bash
espyak [-v LANG] [-x] [--sep SEP] [--tie TIE] [--phonemes] TEXT
```

```bash
espyak -v en "hello world"          # həlˈəʊ wˈɜːld
espyak -v es "díganme"              # dˈiɣanme
espyak -v fr -x "bonjour"           # bO~Z'ur
espyak -v de --sep _ "haus"         # h_ˈaʊ_s
espyak -v en --phonemes "k't"       # render a phoneme string directly
echo "привет" | espyak -v ru -      # '-' reads from stdin
```

| flag           | meaning |
| -------------- | ------- |
| `-v, --lang`   | language/voice code (default `en`) |
| `-x`           | Kirshenbaum output (default is IPA) |
| `--sep SEP`    | separator between phonemes |
| `--tie TIE`    | tie character within multi-char phonemes |
| `--phonemes`   | treat input as a phoneme mnemonic string (render path) |

## Comparing against espeak-ng

`espyak` aims to match `espeak-ng -q --ipa -v LANG` exactly:

```bash
espeak-ng -q --ipa -v es "díganme"   # dˈiɣanme
espyak           -v es "díganme"     # dˈiɣanme
```

If you find a mismatch, it is a bug — please open an issue with the language, the input
word, and both outputs.

## Examples

Runnable scripts live in [`../examples/`](../examples/):

- `basic.py` — the core API.
- `multilingual.py` — the same idea across many scripts/languages.
- `formats.py` — IPA vs Kirshenbaum vs separators/ties.
- `compare_oracle.py` — diff `espyak` against the `espeak-ng` binary (if installed).
