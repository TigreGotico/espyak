# NOTICE

## Relationship to espeak-ng

`espyak` is a Python reimplementation of the grapheme-to-phoneme (G2P) front-end of
[espeak-ng](https://github.com/espeak-ng/espeak-ng). It reproduces espeak-ng's behavior and
bundles espeak-ng's own source data — `dictsource/` (pronunciation rules `*_rules` and word
lists `*_list`), `phsource/` (phoneme definitions), and `lang/` (voice/language
configuration) — under `espyak/data/`, pinned to tag **1.52.0**
(commit `4870adfa25b1a32b4361592f1be8a40337c58d6c`).

## Provenance

`espyak` is an AI-assisted port. The Python implementation was written by an AI coding
assistant that read and instrumented espeak-ng's C source; human review has been minimal.
It is not an independent clean-room implementation.

## License

espeak-ng is distributed under the **GPL-3.0-or-later**. Because `espyak` is derived from
espeak-ng and bundles its data, `espyak` is **GPL-3.0-or-later** as well. See `LICENSE`.
