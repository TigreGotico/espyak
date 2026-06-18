"""Parse espeak-ng's phsource phoneme definitions into in-memory phoneme tables.

This is the symbolic half of synthdata.c / phoneme.h: it loads ``phsource/phonemes``
and the ``include``-d ``ph_*`` files, resolves ``phonemetable`` inheritance and
``import_phoneme`` copies, and exposes, per phoneme, the data the G2P **output** layer
needs: mnemonic, type, the explicit ``ipa`` string (if any), and the stress level for
stress phonemes.

The synthesis-time phoneme *programs* (FMT/WAV/IF/ChangePhoneme) are intentionally
**not** executed: espeak's ``-x`` / ``--ipa`` text output reflects the translation-time
phoneme list, not synthesis-time allophony (verified against the oracle). We parse far
enough to capture ``ipa`` attributes and phoneme types, and skip the rest.

Reference: espeak-ng phsource/phonemes, src/libespeak-ng/compile_phoneme.c.
"""
import os

from espyak import data_paths

# phoneme types (phoneme.h) — mirrored in constants.py
phINVALID = 0
phPAUSE = 1
phSTRESS = 2
phVOWEL = 3
phLIQUID = 4
phSTOP = 5
phVSTOP = 6
phFRICATIVE = 7
phVFRICATIVE = 8
phNASAL = 9
phVIRTUAL = 10

# Keywords that set a phoneme's `type` field. Mix of reserved words (pause/stress/
# liquid/vowel/virtual) and phoneme-feature mnemonics (vwl/nas/stp/...). espeak maps
# features in phoneme.c::phoneme_add_feature; reserved words in compiledata.c.
_TYPE_KEYWORDS = {
    "pause": phPAUSE,
    "stress": phSTRESS,
    "vowel": phVOWEL,
    "vwl": phVOWEL,
    "liquid": phLIQUID,
    "nasal": phNASAL,
    "nas": phNASAL,
    "stop": phSTOP,
    "stp": phSTOP,
    "afr": phSTOP,        # espeak treats affricate as stop
    "frc": phFRICATIVE,
    "apr": phFRICATIVE,   # espeak uses apr for [h]
    "flp": phVSTOP,
    "virtual": phVIRTUAL,
}


# program statement keywords captured for the phoneme-program interpreter (P1b).
# Synthesis-only statements (FMT/WAV/Vowelin/Vowelout/formants) are intentionally NOT
# captured — they don't affect the translation-time phoneme string.
_PROGRAM_KEYWORDS = {
    "IF", "ELIF", "ELSE", "ENDIF",
    "ChangePhoneme", "InsertPhoneme", "IfNextVowelAppend", "AppendPhoneme",
    "ChangeIfDiminished", "ChangeIfUnstressed", "ChangeIfNotStressed",
    "ChangeIfStressed", "CALL", "RETURN",
}


# place-of-articulation feature keywords (phoneme.h), captured for isVelar/isPalatal/...
_PLACE_KEYWORDS = {
    "blb", "lbd", "bld", "dnt", "alv", "rfx", "pla", "alp", "pal",
    "vel", "lbv", "uvl", "phr", "glt",
}


def _unescape_mnemonic(tok):
    """Phoneme source escapes special chars with backslash (e.g. ``\\,`` -> ``,``)."""
    out = []
    i = 0
    while i < len(tok):
        if tok[i] == "\\" and i + 1 < len(tok):
            out.append(tok[i + 1])
            i += 2
        else:
            out.append(tok[i])
            i += 1
    return "".join(out)


class Phoneme:
    __slots__ = ("mnemonic", "type", "ipa", "stress_type", "flags", "lengthmod",
                 "program", "place", "starttype", "endtype", "voicing_switch")

    def __init__(self, mnemonic):
        self.mnemonic = mnemonic
        self.type = phINVALID
        self.ipa = None        # explicit `ipa <string>` attribute, else None
        self.stress_type = 0   # for phSTRESS phonemes: std_length / stress level 0..7
        self.flags = set()     # misc boolean keywords (unstressed, length, nolink, ...)
        self.lengthmod = 0
        self.program = []      # raw program statement lines (IF/ChangePhoneme/CALL/...)
        self.place = None      # place of articulation (vel, pal, alv, ...) for isVelar etc.
        self.starttype = None  # vowel category (#i, #@, #o, ...) for #X group predicates
        self.endtype = None    # end vowel category — prevPh(#X) matches on this for vowels
        self.voicing_switch = None  # voiced<->voiceless counterpart (regressive voicing)

    def copy(self, new_mnemonic=None):
        p = Phoneme(new_mnemonic or self.mnemonic)
        p.type = self.type
        p.ipa = self.ipa
        p.stress_type = self.stress_type
        p.flags = set(self.flags)
        p.lengthmod = self.lengthmod
        p.program = list(self.program)
        p.place = self.place
        p.starttype = self.starttype
        p.endtype = self.endtype
        p.voicing_switch = self.voicing_switch
        return p

    def __repr__(self):
        return "Phoneme(%r, type=%d, ipa=%r)" % (self.mnemonic, self.type, self.ipa)


class PhonemeTable:
    def __init__(self, name, parent_name):
        self.name = name
        self.parent_name = parent_name
        self.phonemes = {}  # mnemonic -> Phoneme (this table's own + inherited, flattened)

    def get(self, mnemonic):
        return self.phonemes.get(mnemonic)


def _strip_comment(line):
    # phsource uses // comments
    ix = line.find("//")
    if ix >= 0:
        line = line[:ix]
    return line


class PhonemeSource:
    """Loads and indexes all phoneme tables from phsource."""

    def __init__(self, phsource_dir=None):
        self.dir = phsource_dir or data_paths.PHSOURCE_DIR
        self.tables = {}  # name -> PhonemeTable (flattened with inheritance)
        self._load()

    # -- file/line iteration with `include` inlined --------------------------
    def _iter_lines(self, path):
        # phsource is mostly UTF-8; a few files carry stray bytes in comments. Decode
        # tolerantly — ipa attribute strings are valid UTF-8 and survive intact.
        with open(path, encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                line = _strip_comment(raw).rstrip("\n")
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped.startswith("include "):
                    inc = stripped.split(None, 1)[1].strip()
                    inc_path = os.path.join(self.dir, inc)
                    yield from self._iter_lines(inc_path)
                else:
                    yield stripped

    def _load(self):
        master = data_paths.phonemes_master()
        # Parse into raw table definitions (own phonemes only), preserving order.
        raw_tables = []   # list of (name, parent, {mnemonic: Phoneme})
        # phonemes before the first `phonemetable` belong to the implicit "base" table
        cur_name = "base"
        cur_parent = None
        cur_phonemes = {}
        raw_index = {"base": (cur_name, cur_parent, cur_phonemes)}

        it = self._iter_lines(master)
        cur_ph = None
        if_depth = 0
        in_proc = False
        cur_proc = None
        self.procedures = {}  # name -> list of program lines

        for line in it:
            tok = line.split()
            head = tok[0]

            if head == "procedure":
                in_proc = True
                cur_proc = tok[1] if len(tok) > 1 else ""
                self.procedures[cur_proc] = []
                continue
            if head == "endprocedure":
                in_proc = False
                cur_proc = None
                continue
            if in_proc:
                if cur_proc is not None and head.split("(")[0] in _PROGRAM_KEYWORDS:
                    self.procedures[cur_proc].append(line)
                continue

            if head == "phonemetable":
                # finalize current table
                raw_tables.append((cur_name, cur_parent, cur_phonemes))
                cur_name = tok[1]
                cur_parent = tok[2] if len(tok) > 2 else None
                cur_phonemes = {}
                raw_index[cur_name] = (cur_name, cur_parent, cur_phonemes)
                cur_ph = None
                continue

            if head == "phoneme":
                mnem = _unescape_mnemonic(tok[1])
                cur_ph = Phoneme(mnem)
                cur_phonemes[mnem] = cur_ph
                if_depth = 0
                continue

            if head == "endphoneme":
                cur_ph = None
                continue

            if head == "import_phoneme":
                # import_phoneme TABLE/MNEM -> copy that phoneme from TABLE; a bare
                # `import_phoneme MNEM` (no '/') copies from the CURRENT table (gd R imports
                # R2 -> R renders 'r' not the fallback Kirshenbaum ʀ). The bare form was being
                # mis-read as a table name and silently dropped.
                ref = tok[1]
                imported = None
                if "/" in ref:
                    src_table, _, src_mnem = ref.partition("/")
                    src = raw_index.get(src_table)
                    src_phonemes = src[2] if src else None
                else:
                    src_mnem = ref
                    # current table, then its parent chain (espeak compiles the inherited
                    # base first, so a bare import resolves against it): gd R -> R2 from base.
                    src_phonemes = cur_phonemes if src_mnem in cur_phonemes else None
                    pname, seen = cur_parent, set()
                    while src_phonemes is None and pname and pname not in seen:
                        seen.add(pname)
                        entry = raw_index.get(pname)
                        if entry and src_mnem in entry[2]:
                            src_phonemes = entry[2]
                        pname = entry[1] if entry else None
                if src_phonemes and src_mnem in src_phonemes:
                    imported = src_phonemes[src_mnem].copy(cur_ph.mnemonic if cur_ph else src_mnem)
                if cur_ph is not None and imported is not None:
                    # keep the new mnemonic, inherit attributes
                    imported.mnemonic = cur_ph.mnemonic
                    cur_phonemes[cur_ph.mnemonic] = imported
                    cur_ph = imported
                continue

            if cur_ph is None:
                continue

            # capture program statements (control flow + phoneme changes) for P1b.
            # Statements like `ChangePhoneme(D)` are a single token (no space), so test
            # the keyword prefix before any '('.
            if head.split("(")[0] in _PROGRAM_KEYWORDS:
                cur_ph.program.append(line)
                if head == "IF":
                    if_depth += 1
                elif head == "ENDIF":
                    if_depth = max(0, if_depth - 1)
                continue

            # --- phoneme attribute lines ---
            if head == "ipa":
                # `ipa <string>` sets the output IPA. A top-level ipa is the default; an
                # ipa inside an IF block is conditional, so it goes to the program and is
                # applied by the interpreter (e.g. @- is `ipa ə` but `ipa NULL` before *).
                if if_depth == 0:
                    cur_ph.ipa = _decode_ipa(line[len("ipa"):].strip())
                cur_ph.program.append(line)
                continue
            if head == "stress_type":
                cur_ph.stress_type = int(tok[1])
                cur_ph.flags.add("stress")
                continue
            if head == "lengthmod":
                try:
                    cur_ph.lengthmod = int(tok[1])
                except (ValueError, IndexError):
                    pass
                continue
            # Feature/type keywords may appear anywhere on the line (e.g. `vcd alv stp`).
            # Apply every type keyword found (last wins, as espeak applies features in order).
            if head == "starttype":
                cur_ph.starttype = tok[1] if len(tok) > 1 else None
                continue
            if head == "endtype":
                cur_ph.endtype = tok[1] if len(tok) > 1 else None
                continue
            if head == "voicingswitch":
                cur_ph.voicing_switch = _unescape_mnemonic(tok[1]) if len(tok) > 1 else None
                continue
            for ti, t in enumerate(tok):
                if t == "starttype" and ti + 1 < len(tok):
                    cur_ph.starttype = tok[ti + 1]
                elif t == "endtype" and ti + 1 < len(tok):
                    cur_ph.endtype = tok[ti + 1]
                elif t in _TYPE_KEYWORDS:
                    cur_ph.type = _TYPE_KEYWORDS[t]
                    if t == "stress":
                        cur_ph.flags.add("stress")
                elif t in _PLACE_KEYWORDS:
                    cur_ph.place = t
                elif t in ("vcd", "vls"):
                    cur_ph.flags.add(t)
                elif t == "lng":
                    cur_ph.flags.add("long")  # phLONG: long vowel (syllable-weight + 1SL/1RH)
                elif t in ("flag1", "flag2", "flag3", "flag4"):
                    cur_ph.flags.add(t)  # phoneme feature bits tested by isFlag1..4 programs
                    # (e.g. Bashkir/Tatar back vowels -> dark-l: prevVowel(isFlag2)->Change(L))
            if len(tok) == 1:
                cur_ph.flags.add(head)

        raw_tables.append((cur_name, cur_parent, cur_phonemes))

        # Resolve inheritance: flatten parent chain (parent first, child overrides).
        raw_by_name = {name: (parent, phons) for name, parent, phons in raw_tables}

        def flatten(name, _seen):
            if name in self.tables:
                return self.tables[name]
            if name not in raw_by_name or name in _seen:
                return None
            _seen.add(name)
            parent, phons = raw_by_name[name]
            table = PhonemeTable(name, parent)
            if parent:
                pt = flatten(parent, _seen)
                if pt:
                    table.phonemes.update(pt.phonemes)
            table.phonemes.update(phons)
            self.tables[name] = table
            return table

        for name in raw_by_name:
            flatten(name, set())

        self._resolve_call_types()
        self._derive_voiced_types()

    def _derive_voiced_types(self):
        """compiledata.c: a phVOICED stop/fricative becomes phVSTOP/phVFRICATIVE."""
        for table in self.tables.values():
            for ph in table.phonemes.values():
                if "vcd" in ph.flags:
                    if ph.type == phSTOP:
                        ph.type = phVSTOP
                    elif ph.type == phFRICATIVE:
                        ph.type = phVFRICATIVE

    def _resolve_call_types(self):
        """A phoneme defined only via `CALL X` inherits X's type (e.g. `3` is `CALL @`
        so it is a vowel). Resolve types for phonemes left as phINVALID."""
        for table in self.tables.values():
            for ph in table.phonemes.values():
                if ph.type != phINVALID:
                    continue
                for line in ph.program:
                    tok = line.split()
                    if tok and tok[0] == "CALL":
                        target = self._resolve_call(table, tok[1])
                        if target is not None and target.type != phINVALID:
                            ph.type = target.type
                            ph.flags |= {f for f in target.flags
                                         if f in ("unstressed", "nonsyllabic", "long")}
                        break

    def _resolve_call(self, table, ref):
        if "/" in ref:
            tname, _, mnem = ref.partition("/")
            t = self.tables.get(tname)
            return t.get(mnem) if t else None
        return table.get(ref)

    def table(self, name):
        return self.tables.get(name)


def _decode_ipa(text):
    """Decode an `ipa` attribute string: handle U+xxxx escapes and '_' / '|' markers.

    espeak's ipa strings may contain ``U+xxxx`` hex escapes. A leading low byte (<0x20)
    is a flags byte in compiled form; in source it is rare and handled by callers.
    """
    if not text:
        return ""
    if text == "NULL":
        return ""  # `ipa NULL` means the phoneme produces no IPA output
    out = []
    i = 0
    while i < len(text):
        if text[i : i + 2] == "U+":
            j = i + 2
            hexd = ""
            while j < len(text) and text[j] in "0123456789abcdefABCDEF":
                hexd += text[j]
                j += 1
            if hexd:
                out.append(chr(int(hexd, 16)))
                i = j
                continue
        out.append(text[i])
        i += 1
    return "".join(out)


# module-level cache
_SOURCE = None


def get_source():
    global _SOURCE
    if _SOURCE is None:
        _SOURCE = PhonemeSource()
    return _SOURCE
