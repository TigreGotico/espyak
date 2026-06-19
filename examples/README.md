# Examples

Runnable scripts demonstrating `espyak`. Install the package first (`pip install -e .` from
the repo root), then run any script:

```bash
python examples/basic.py
python examples/multilingual.py
python examples/formats.py
python examples/compare_oracle.py es díganme hola
```

| script | shows |
| --- | --- |
| `basic.py` | the core `G2P(lang).phonemize(text)` API |
| `multilingual.py` | the same call across Latin / Cyrillic / Greek / Indic / Arabic / Hebrew / Korean / Armenian |
| `formats.py` | IPA vs Kirshenbaum, and the `separator` / `tie` options |
| `compare_oracle.py` | diff `espyak` against the real `espeak-ng` binary (if installed) |

See [`../docs/usage.md`](../docs/usage.md) for the full API.
