"""Locate the bundled espeak-ng source data (dictsource / phsource / lang).

The engine never calls the espeak-ng binary at runtime; it parses these source data
files. The binary under ``oracle/`` is used only by the test harness to generate
ground-truth fixtures.
"""
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(_HERE, "data")

DICTSOURCE_DIR = os.path.join(DATA_DIR, "dictsource")
PHSOURCE_DIR = os.path.join(DATA_DIR, "phsource")
LANG_DIR = os.path.join(DATA_DIR, "lang")


def version():
    """Return (version, commit) of the pinned espeak-ng data."""
    try:
        with open(os.path.join(DATA_DIR, "VERSION"), encoding="utf-8") as fh:
            ver, commit = fh.read().split()
            return ver, commit
    except (OSError, ValueError):
        return ("unknown", "unknown")


def rules_path(lang):
    """Path to ``<lang>_rules`` source file."""
    return os.path.join(DICTSOURCE_DIR, "%s_rules" % lang)


def list_path(lang):
    """Path to ``<lang>_list`` source file."""
    return os.path.join(DICTSOURCE_DIR, "%s_list" % lang)


def listx_path(lang):
    """Path to ``<lang>_listx`` source file (compiled after _list for some langs)."""
    return os.path.join(DICTSOURCE_DIR, "%s_listx" % lang)


def extra_path(lang):
    """Path to ``<lang>_extra`` source file (appended dictionary entries)."""
    return os.path.join(DICTSOURCE_DIR, "%s_extra" % lang)


def emoji_path(lang):
    return os.path.join(DICTSOURCE_DIR, "%s_emoji" % lang)


def voice_path(code):
    """Find the voice/lang config file for a language code by scanning lang groups.

    espeak-ng stores voices as ``lang/<group>/<code>`` (e.g. ``lang/gmw/en``). The
    file's basename is the canonical voice name.
    """
    for group in sorted(os.listdir(LANG_DIR)):
        gdir = os.path.join(LANG_DIR, group)
        if not os.path.isdir(gdir):
            continue
        cand = os.path.join(gdir, code)
        if os.path.isfile(cand):
            return cand
    return None


def phonemes_master():
    """Path to the master phsource/phonemes file."""
    return os.path.join(PHSOURCE_DIR, "phonemes")
