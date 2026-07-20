"""Guard against the released wheel silently dropping bundled dictsource/lang data.

Regression: PyPI espyak==0.0.2a1 was cut before the sub-dialect VARIANT system (voice.py /
`_voice_mod.load`) landed, so `G2P("en-us")` in that release resolved the dict_name straight
from the requested lang code instead of the voice-file base_lang, and looked for a
non-existent `data/dictsource/en-us_rules` (real file: `en_rules`) -> FileNotFoundError at
runtime in any consumer (e.g. phoonnx) that installs espyak from PyPI. `MANIFEST.in` +
`[tool.setuptools.package-data]` must keep shipping every file under `espyak/data/`
(dictsource/phsource/lang have no file extension, so glob patterns must not assume one),
and every dict_name reachable through a real voice file must have its rules/list files
present -- this test fails loudly if either regresses.
"""
import os

import espyak
from espyak import data_paths
from espyak import voice as _voice_mod

DATA_DIR = os.path.dirname(os.path.abspath(data_paths.__file__))
DATA_DIR = os.path.join(os.path.dirname(espyak.__file__), "data")


def _all_voice_codes():
    lang_dir = os.path.join(DATA_DIR, "lang")
    for root, _dirs, files in os.walk(lang_dir):
        for fname in files:
            yield fname


def test_data_directories_are_present_and_non_empty():
    for sub in ("dictsource", "phsource", "lang"):
        d = os.path.join(DATA_DIR, sub)
        assert os.path.isdir(d), "missing bundled data directory: %s" % d
        assert os.listdir(d), "bundled data directory is empty: %s" % d


def test_every_voice_file_resolves_to_packaged_rules():
    """Every code under data/lang must resolve (directly or via variant base_lang) to a
    packaged `<dict_name>_rules` file -- this is exactly what broke for en-us in 0.0.2a1."""
    missing = []
    for code in _all_voice_codes():
        cfg = _voice_mod.load(code)
        dict_name = cfg.dict_name
        rules_file = data_paths.rules_path(dict_name)
        if not os.path.isfile(rules_file):
            missing.append((code, dict_name, rules_file))
    assert not missing, "voice codes with no packaged rules file: %r" % (missing,)


def test_en_us_dialect_loads_without_filenotfounderror():
    """Direct regression test for the exact crash reported downstream (phoonnx CI)."""
    from espyak.api import G2P

    g = G2P("en-us")
    assert g.phonemize("hello world")
