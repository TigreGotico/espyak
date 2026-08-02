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
    # espeak matches the voice/language code case-insensitively (en-us -> file en-US,
    # pt-br -> pt-BR, fr-be -> fr-BE) and, failing a filename match, against the codes a
    # voice file declares on its `language` lines (en-gb -> the gmw/en file, which is the
    # canonical British voice). Prefer an exact filename hit, then a case-fold filename
    # match, then a declared-language match.
    #
    # Multiple voice files can declare the same requested code (e.g. `en`, `en-GB-scotland`
    # and `en-GB-x-rp` all declare `language en-gb ...`); the trailing number on the
    # `language` line is espeak-ng's match PRIORITY (lower = better/more canonical), so the
    # declared-language fallback must pick the lowest-priority declaration, not merely the
    # first one `os.listdir` happens to yield -- directory iteration order is filesystem-
    # dependent (a fresh checkout vs. an existing one can list entries differently), which
    # previously made this resolution non-deterministic across environments/checkouts.
    name_fallback = None
    best_lang_fallback = None  # (priority, fpath)
    code_lower = code.lower()
    for group in sorted(os.listdir(LANG_DIR)):
        gdir = os.path.join(LANG_DIR, group)
        if not os.path.isdir(gdir):
            continue
        cand = os.path.join(gdir, code)
        if os.path.isfile(cand):
            return cand
        for name in sorted(os.listdir(gdir)):
            fpath = os.path.join(gdir, name)
            if not os.path.isfile(fpath):
                continue
            if name_fallback is None and name.lower() == code_lower:
                name_fallback = fpath
            priority = _declared_language_priority(fpath, code_lower)
            if priority is not None and (best_lang_fallback is None or priority < best_lang_fallback[0]):
                best_lang_fallback = (priority, fpath)
    if name_fallback is not None:
        return name_fallback
    return best_lang_fallback[1] if best_lang_fallback else None


def _declared_language_priority(fpath, code_lower):
    """Priority (lower = better match) of a ``language <code> [priority]`` line matching
    ``code_lower`` in the voice file at ``fpath``, or ``None`` if it declares no such code.
    A line with no explicit priority number defaults to espeak-ng's own default of 5."""
    try:
        with open(fpath, encoding="utf-8") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) >= 2 and parts[0] == "language" and parts[1].lower() == code_lower:
                    if len(parts) >= 3:
                        try:
                            return int(parts[2])
                        except ValueError:
                            pass
                    return 5
    except OSError:
        pass
    return None


def phonemes_master():
    """Path to the master phsource/phonemes file."""
    return os.path.join(PHSOURCE_DIR, "phonemes")
