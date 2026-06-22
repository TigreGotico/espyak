"""Voice / sub-dialect VARIANT loader (port of LoadVoice in voices.c).

espeak-ng models a sub-dialect (pt-br, en-us, es-419, ca-va, ...) not as a separate
rule/dict file but as a small VOICE/LANGUAGE file under ``espeak-ng-data/lang/<family>/<code>``
that LAYERS modifications over a SHARED base language. The base dict + rules + translator
config are those of the base language; the variant only overrides:

  * ``language <base>``  -> the FIRST language line, ``strtok``'d on ``-``, names the base
    language whose translator config + dict/rules/phoneme-table espeak loads (voices.c:550).
    pt-br -> ``pt``, en-us -> ``en``, es-419 -> ``es``, ca-va -> ``ca``.
  * ``dictionary <name>`` -> overrides the dict/rules base name (voices.c:577) while the
    translator config still comes from the language line. nb declares ``language nb`` +
    ``dictionary no`` -> config ``nb`` (defaults), but rules/dict/_list load from ``no``.
  * ``phonemes <table>`` -> swap the phoneme table (es-419 -> es-la, en-us -> en-us). A
    later ``phonemes`` line overrides an earlier one (voices.c:580).
  * ``dictrules N M ...`` -> set numbered dictionary ``?N`` conditions (dict_condition),
    selecting variant-conditional entries in the SHARED base dict (dictionary.c:1616).
  * ``replace <flags> <old> <new>`` -> post-translation phoneme substitutions applied to
    the final phoneme list, gated by the flags (phonemelist.c:86):
        bit 1 -> only at word end
        bit 2 -> NOT in stressed syllables (stresslevel & 7 > 3)
        bit 4 -> only at word start
    ``new`` of ``NULL`` deletes the phoneme.

Synthesis-only keywords (stressLength, stressAmp, intonation, tunes, pitch, ...) do not
affect the IPA G2P output and are parsed-but-ignored.
"""
import os

from espyak import data_paths


def _strtok_dash(name):
    """espeak ``strtok(language_name, "-")`` — the base language is the part before the
    first ``-`` (pt-br -> pt, en-gb-scotland -> en, cmn-latn-pinyin -> cmn)."""
    return name.split("-", 1)[0]


class VoiceConfig:
    """Parsed contents of a voice/lang file, with the base language resolved.

    Attributes:
        code           the requested voice code (e.g. ``pt-br``)
        base_lang      base language for the translator config (strtok of the language line)
        dict_name      base name for rules/dict/_list (``dictionary`` override, else base_lang)
        phoneme_tables ordered list of ``phonemes`` table names (last wins)
        dictrules      list[int] of ``dictrules`` condition numbers
        replaces       list[(flags, old_mnem, new_mnem_or_None)] phoneme substitutions
    """

    def __init__(self, code, base_lang, dict_name, phoneme_tables, dictrules, replaces):
        self.code = code
        self.base_lang = base_lang
        self.dict_name = dict_name
        self.phoneme_tables = phoneme_tables
        self.dictrules = dictrules
        self.replaces = replaces

    @property
    def is_variant(self):
        """True when this voice layers over a different base language (pt-br over pt)."""
        return self.base_lang != self.code


def _parse_replace(p):
    """``replace <flags> <old> [<new>]`` -> (flags, old, new) (PhonemeReplacement,
    voices.c:351). ``new`` defaults to ``NULL`` -> delete; returned as None."""
    parts = p.split()
    if len(parts) < 2:
        return None
    try:
        flags = int(parts[0])
    except ValueError:
        return None
    old = parts[1]
    new = parts[2] if len(parts) > 2 else "NULL"
    if new == "NULL":
        new = None
    return (flags, old, new)


def load(code):
    """Load the voice/lang file for ``code`` and resolve its base language.

    Returns a :class:`VoiceConfig`. If no voice file exists, returns a trivial config
    that treats ``code`` itself as the base language (the plain base-language path).
    """
    path = data_paths.voice_path(code)
    base_lang = code
    dict_name = None
    phoneme_tables = []
    dictrules = []
    replaces = []
    language_set = False

    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                parts = line.split()
                if not parts:
                    continue
                kw = parts[0]
                rest = line[len(kw):].strip()
                if kw == "language":
                    # only the FIRST language line sets the base (voices.c:548); "variant"
                    # is a pseudo-language and ignored.
                    name = parts[1] if len(parts) > 1 else ""
                    if name == "variant":
                        continue
                    if not language_set:
                        base_lang = _strtok_dash(name)
                        language_set = True
                elif kw == "dictionary" and len(parts) > 1:
                    dict_name = parts[1]
                elif kw == "phonemes" and len(parts) > 1:
                    phoneme_tables.append(parts[1])
                elif kw == "dictrules":
                    for tok in parts[1:]:
                        if tok.isdigit():
                            dictrules.append(int(tok))
                        else:
                            break
                elif kw == "replace":
                    rep = _parse_replace(rest)
                    if rep is not None:
                        replaces.append(rep)
    if dict_name is None:
        dict_name = base_lang
    return VoiceConfig(code, base_lang, dict_name, phoneme_tables, dictrules, replaces)
