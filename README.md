# espeakng-g2p

A pure-Python, dependency-free reimplementation of **espeak-ng's grapheme-to-phoneme
(G2P) front-end**. Text → phonemes only — no synthesis, no audio, no C extension.

The goal is **byte-for-byte compatibility** with the real `espeak-ng` binary across all
~130 languages, validated end-to-end against the pinned oracle (espeak-ng `1.52.0`).

Import package: `espyak`.

```python
from espyak import G2P

g2p = G2P("en")
print(g2p.phonemize("hello world"))          # IPA
print(g2p.phonemize("hello world", ipa=False))  # Kirshenbaum
```

## Why

Every consumer in the OVOS ecosystem currently shells out to the `espeak-ng` binary or
wraps the `espeak_phonemizer` C-extension. This library removes the native dependency,
makes the rules introspectable and patchable in Python, and slots in as a first-class
[phoonnx](https://github.com/TigreGotico/phoonnx) backend.

## How it works

It is a **clean-room** engine that parses espeak-ng's own source data
(`dictsource/*_rules`, `*_list`, `phsource/phonemes`, voice files) and replays its
matching, stress, and number logic in Python. See `NOTICE.md` for the licensing stance
(intentionally unassigned) and `docs/divergences.md` for any deliberate deviations from
upstream (all gated behind `force_compat`, default `True`).

## Status

Under construction. See `test/report.md` for the current per-language pass rate and the
plan for the phased rollout.

## License

Intentionally unassigned — see `NOTICE.md`.
