# Tests

The suite validates `espyak` against the pinned **espeak-ng 1.52.0** oracle. The binary is
used only to *generate* fixtures — the engine never calls it at runtime.

```bash
pytest -q                       # unit + fixture tests (164)
python test/sweep.py 25         # per-language _list-headword sweep vs the oracle
python test/corpus_sweep.py     # real-sentence corpus vs the oracle
```

## Layout

| file | purpose |
| --- | --- |
| `test_en_words.py` | English word fixtures (IPA / Kirshenbaum) vs the oracle |
| `test_numbers.py` | number / ordinal / fraction expansion |
| `test_phoneme_programs.py` | context-dependent `ChangePhoneme`/`InsertPhoneme` behavior |
| `conftest.py` | shared fixtures / pytest configuration |
| `fixtures/` | per-language `word → expected` JSONL captured from the oracle |
| `oracle/` | oracle build pin (`VERSION`) + the fixture generator |
| `sweep.py` | samples the first *N* headwords of every `dictsource/*_list`, diffs vs `espeak-ng -q --ipa`, writes `report.md` |
| `corpus_sweep.py` | runs a hand-built real-sentence corpus across 31 languages |
| `report.md` | generated per-language pass rate (regenerate with `sweep.py`) |

## Current parity

- `sweep.py` (N=25): **1703/1703 = 100.0%** across 86 languages.
- `corpus_sweep.py`: **438/438 = 100.0%** across 31 languages.

> Note: this is the **single** test directory for the repo (`test/`, not `tests/`). Keeping
> one avoids the trap where CI silently collects only one of two directories.
