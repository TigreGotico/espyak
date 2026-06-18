# NOTICE

## License: intentionally unassigned

This project ships **without a license**. No `LICENSE` file, no SPDX headers, no
`license=` field in package metadata. The choice of license is deliberately deferred
to the maintainer. Until a license is added, no usage grant beyond what the law
provides by default should be assumed.

## Relationship to espeak-ng

`espeakng-g2p` is a **clean-room reimplementation** of the grapheme-to-phoneme (G2P)
front-end of [espeak-ng](https://github.com/espeak-ng/espeak-ng). The Python code here
was written by studying espeak-ng's *documented file formats* and *observable runtime
behavior* — not by copying or translating its C source line by line.

The engine reads espeak-ng's own **source data files** at load time:

- `dictsource/` — pronunciation rules (`*_rules`) and word lists (`*_list`)
- `phsource/` — phoneme definitions
- `lang/` — voice/language configuration files

These data files originate from espeak-ng (pinned to tag **1.52.0**, commit
`4870adfa25b1a32b4361592f1be8a40337c58d6c`). espeak-ng and its data are distributed
under the GPL-3.0-or-later. If/when this project bundles those data files, that data
retains its upstream license; the maintainer is responsible for reconciling the
project's eventual license with the bundled data's terms.

## Compatibility target

Output is validated for byte-for-byte equality against the espeak-ng `1.52.0` binary
(see `test/`). Deliberate divergences from upstream behavior are gated behind the
`force_compat` flag (default `True` = bug-for-bug compatible) and documented in
`docs/divergences.md`.
