"""Phoneme-program interpreter (P1b): the output-affecting subset of espeak's
synthesis-time phoneme programs.

espeak's `-x`/`--ipa` text reflects the translation-time phoneme list AFTER the
context-dependent `ChangePhoneme`/`InsertPhoneme` programs run (verified vs the oracle:
en `r`->`r/` before a non-vowel; es `d`->`D`/`b`->`B`/`g`->`G` spirantization between
vowels). This module parses those programs from phsource and runs them over the phoneme
list. Synthesis-only statements (FMT/WAV/Vowelin/Vowelout) are not captured, so only the
identity-changing logic is executed.

Reference: espeak-ng phsource phoneme programs; synthdata.c InterpretPhoneme.
"""
from espyak.phoneme_tab import (
    phVOWEL, phPAUSE, phLIQUID, phNASAL, phSTOP, phVSTOP, phFRICATIVE, phVFRICATIVE,
)

# newword flag (render.PHLIST_START_OF_WORD)
_START_OF_WORD = 1


def set_regressive_voicing(plist, table, regression):
    """Port of SetRegressiveVoicing (phonemelist.c). Walks the phoneme list backward and
    assimilates consonant voicing (regressive), with optional word-final devoicing.
    Used by Slavic and other languages (LOPT_REGRESSIVE_VOICING)."""
    if not regression:
        return
    voicing = 1 if (regression & 0x100) else 0
    stop_propagation = False
    for j in range(len(plist) - 1, -1, -1):
        ph = plist[j].ph
        t = ph.type
        if regression & 0x2 and ph.mnemonic[:1] in ("v", "R"):
            stop_propagation = True
            if regression & 0x10:
                voicing = 0
        if t in (phSTOP, phFRICATIVE):          # voiceless obstruent
            if voicing == 0 and (regression & 0xf):
                voicing = 1
            elif voicing == 2 and ph.voicing_switch:
                nph = table.get(ph.voicing_switch)
                if nph is not None:
                    plist[j].ph = nph
        elif t in (phVSTOP, phVFRICATIVE):      # voiced obstruent
            if voicing == 0 and (regression & 0xf):
                voicing = 2
            elif voicing == 1 and ph.voicing_switch:
                nph = table.get(ph.voicing_switch)
                if nph is not None:
                    plist[j].ph = nph
        else:
            if regression & 0x8:
                if t in (phPAUSE, phVOWEL):
                    voicing = 0
            else:
                voicing = 0
        if stop_propagation:
            voicing = 0
            stop_propagation = False
        if plist[j].newword & _START_OF_WORD:
            if regression & 0x04:
                voicing = 0
            if (regression & 0x100) and voicing == 0:
                voicing = 1

# --- program parser ------------------------------------------------------------


class _If:
    __slots__ = ("branches", "else_block")

    def __init__(self):
        self.branches = []   # list of (condition_tokens, block)
        self.else_block = []


def parse_program(lines):
    """Parse program statement lines into a flat list of statements / _If trees."""
    pos = [0]

    def parse_block(stoppers):
        block = []
        while pos[0] < len(lines):
            line = lines[pos[0]]
            head = line.split()[0]
            if head in stoppers:
                return block
            pos[0] += 1
            if head == "IF":
                node = _If()
                cond = _extract_cond(line, "IF")
                inner = parse_block(("ELIF", "ELSE", "ENDIF"))
                node.branches.append((cond, inner))
                while pos[0] < len(lines) and lines[pos[0]].split()[0] == "ELIF":
                    el = lines[pos[0]]; pos[0] += 1
                    node.branches.append((_extract_cond(el, "ELIF"),
                                          parse_block(("ELIF", "ELSE", "ENDIF"))))
                if pos[0] < len(lines) and lines[pos[0]].split()[0] == "ELSE":
                    pos[0] += 1
                    node.else_block = parse_block(("ENDIF",))
                if pos[0] < len(lines) and lines[pos[0]].split()[0] == "ENDIF":
                    pos[0] += 1
                block.append(node)
            else:
                block.append(line)  # simple statement
        return block

    return parse_block(())


def _extract_cond(line, kw):
    # "IF <cond> THEN" -> "<cond>"
    s = line.strip()
    if s.startswith(kw):
        s = s[len(kw):].strip()
    if s.endswith("THEN"):
        s = s[:-4].strip()
    return s


# --- predicates ----------------------------------------------------------------


def _is_voiced(ph):
    return ph.type in (phVOWEL, phNASAL, phLIQUID, phVSTOP, phVFRICATIVE) or "vcd" in ph.flags


_FEATURES = {
    "isVowel": lambda ph, e, ctx: ph.type == phVOWEL,
    "isNotVowel": lambda ph, e, ctx: ph.type != phVOWEL,
    "isPause": lambda ph, e, ctx: ph.type == phPAUSE,
    "isPause2": lambda ph, e, ctx: ph.type == phPAUSE,
    "isVoiced": lambda ph, e, ctx: _is_voiced(ph),
    "isRhotic": lambda ph, e, ctx: "rhotic" in ph.flags,
    "isLiquid": lambda ph, e, ctx: ph.type == phLIQUID,
    "isNasal": lambda ph, e, ctx: ph.type == phNASAL,
    "isSibilant": lambda ph, e, ctx: "sibilant" in ph.flags or "sib" in ph.flags,
    "isWordStart": lambda ph, e, ctx: e is not None and e.newword & 1,
    "isWordEnd": lambda ph, e, ctx: ctx.get("word_end", False),
    "isFirstVowel": lambda ph, e, ctx: ctx.get("first_vowel", False),
    "isFinalVowel": lambda ph, e, ctx: ctx.get("final_vowel", False),
    "isStressed": lambda ph, e, ctx: e is not None and e.stresslevel >= 4,
    "isNotStressed": lambda ph, e, ctx: e is None or e.stresslevel < 4,
    "isUnstressed": lambda ph, e, ctx: e is None or e.stresslevel <= 1,
    "isDiminished": lambda ph, e, ctx: e is not None and e.stresslevel == 0,
    "isMaxStress": lambda ph, e, ctx: ctx.get("max_stress", False),
    "isVelar": lambda ph, e, ctx: getattr(ph, "place", None) in ("vel", "lbv"),
    "isPalatal": lambda ph, e, ctx: getattr(ph, "place", None) in ("pal", "pla", "alp"),
    "isVStop": lambda ph, e, ctx: ph.type == phVSTOP,
    "isUStop": lambda ph, e, ctx: ph.type == phSTOP,
    "isVFricative": lambda ph, e, ctx: ph.type == phVFRICATIVE,
    "isLong": lambda ph, e, ctx: "long" in ph.flags,
    # language-defined phoneme flags (flag1..flag8); e.g. uz front vowels for l-clearing.
    "isFlag1": lambda ph, e, ctx: "flag1" in ph.flags,
    "isFlag2": lambda ph, e, ctx: "flag2" in ph.flags,
    "isFlag3": lambda ph, e, ctx: "flag3" in ph.flags,
    "isFlag4": lambda ph, e, ctx: "flag4" in ph.flags,
}

# a synthetic pause phoneme stands in at word boundaries for *W predicates


class _Pause:
    type = phPAUSE
    flags = frozenset()
    mnemonic = "_"


_PAUSE = _Pause()


class Interpreter:
    def __init__(self, source, table):
        self.source = source
        self.table = table
        self._prog_cache = {}

    def _program(self, ph):
        key = id(ph)
        prog = self._prog_cache.get(key)
        if prog is None:
            prog = parse_program(ph.program)
            self._prog_cache[key] = prog
        return prog

    def run(self, plist):
        """Run each phoneme's program over the list, applying ChangePhoneme/InsertPhoneme."""
        # precompute vowel positions for first/final-vowel predicates
        i = 0
        while i < len(plist):
            entry = plist[i]
            ph = entry.ph
            if ph.program:
                ctx = self._context(plist, i)
                self._exec(self._program(ph), plist, i, ctx)
            i += 1
        return plist

    def _context(self, plist, i):
        entry = plist[i]
        # word membership: previous/next entries until a start-of-word boundary
        word_end = (i + 1 >= len(plist)) or bool(plist[i + 1].newword & 1)
        # first/final vowel within the word
        vowels = [j for j in range(len(plist)) if plist[j].ph.type == phVOWEL]
        first_vowel = bool(vowels and vowels[0] == i)
        final_vowel = bool(vowels and vowels[-1] == i)
        max_stress = entry.stresslevel >= 4
        return {"word_end": word_end, "first_vowel": first_vowel,
                "final_vowel": final_vowel, "max_stress": max_stress}

    # -- execution --
    def _exec(self, block, plist, i, ctx):
        for stmt in block:
            if isinstance(stmt, _If):
                ran = False
                for cond, inner in stmt.branches:
                    if self._eval(cond, plist, i, ctx):
                        if self._exec(inner, plist, i, ctx):
                            return True
                        ran = True
                        break
                if not ran:
                    if self._exec(stmt.else_block, plist, i, ctx):
                        return True
            else:
                if self._exec_simple(stmt, plist, i, ctx):
                    return True  # RETURN
        return False

    def _exec_simple(self, line, plist, i, ctx):
        tok = line.split()
        head = tok[0].split("(")[0]  # `ChangePhoneme(D)` is one token
        if head == "RETURN":
            return True
        if head == "CALL":
            self._call(tok[1], plist, i, ctx)
            return False
        if head == "ipa":
            from espyak.phoneme_tab import _decode_ipa
            plist[i].ipa_override = _decode_ipa(line[len("ipa"):].strip())
            return False
        arg = _paren_arg(line)
        if head == "ChangePhoneme":
            return self._change(plist, i, arg, ctx)
        elif head == "InsertPhoneme":
            self._insert(plist, i, arg)
        elif head == "IfNextVowelAppend":
            # append the phoneme (e.g. linking r-) after this one if next is a vowel
            if i + 1 < len(plist) and plist[i + 1].ph.type == phVOWEL:
                ph = self.table.get(arg)
                if ph is not None:
                    from espyak.render import PhonemeListEntry
                    plist.insert(i + 1, PhonemeListEntry(ph))
        elif head in ("ChangeIfDiminished", "ChangeIfUnstressed",
                      "ChangeIfNotStressed", "ChangeIfStressed"):
            # espeak's StressCondition returns false for SFLAG_DICTIONARY phonemes unless
            # LOPT_REDUCE&1, so dict-entry vowels keep their length/quality (fo hina->hiːna).
            if getattr(plist[i], "dict_no_reduce", False):
                return False
            lvl = plist[i].stresslevel
            cond = {
                "ChangeIfDiminished": lvl == 0,
                "ChangeIfUnstressed": lvl <= 1,
                "ChangeIfNotStressed": lvl < 4,
                "ChangeIfStressed": lvl >= 4,
            }[head]
            if cond:
                return self._change(plist, i, arg, ctx)
        return False

    def _call(self, ref, plist, i, ctx):
        prog = None
        if "/" in ref:
            tname, _, mnem = ref.partition("/")
            t = self.source.table(tname)
            if t is not None:
                p = t.get(mnem)
                if p is not None:
                    prog = parse_program(p.program)
        elif ref in getattr(self.source, "procedures", {}):
            prog = parse_program(self.source.procedures[ref])
        if prog:
            self._exec(prog, plist, i, ctx)

    def _change(self, plist, i, mnem, ctx, _depth=0):
        if mnem == "NULL":
            # ChangePhoneme(NULL) deletes this phoneme (e.g. linking ; before a consonant)
            plist[i].deleted = True
            return True
        ph = self.table.get(mnem)
        if ph is None:
            return False
        plist[i].ph = ph
        plist[i].ipa_override = None
        # re-run the new phoneme's program so ITS ipa / further changes apply (espeak
        # re-interprets the changed phoneme). Guard against ChangePhoneme cycles.
        if ph.program and _depth < 8:
            self._exec(self._program(ph), plist, i, ctx)
        return True  # the changed phoneme's program takes over; stop the old one

    def _insert(self, plist, i, mnem):
        ph = self.table.get(mnem)
        if ph is None:
            return
        from espyak.render import PhonemeListEntry
        entry = PhonemeListEntry(ph)
        plist.insert(i, entry)
        # The main loop already passed index i (the inserting phoneme is now at i+1), so the
        # inserted phoneme would never get its own program run. Run it now so e.g. the
        # epenthetic @- before 'r' applies its conditional `ipa NULL` (ru при -> prʲɪ, not
        # pərʲɪ). Inserted phonemes here don't themselves InsertPhoneme, so no recursion.
        if ph.program:
            self._exec(self._program(ph), plist, i, self._context(plist, i))

    # -- condition evaluation (left-to-right AND/OR, no precedence) --
    def _eval(self, cond, plist, i, ctx):
        tokens = cond.replace("(", " ( ").replace(")", " ) ").split()
        # reassemble predicate calls: func ( arg )
        terms = []  # list of ('NOT'|None, predstr) or operator strings
        j = 0
        while j < len(tokens):
            t = tokens[j]
            if t in ("AND", "OR"):
                terms.append(t)
                j += 1
            elif t == "NOT":
                terms.append("NOT")
                j += 1
            elif j + 3 < len(tokens) and tokens[j + 1] == "(":
                pred = (t, tokens[j + 2])
                terms.append(pred)
                j += 4
            else:
                j += 1
        # evaluate left to right
        result = None
        pending_not = False
        op = None
        for term in terms:
            if term == "NOT":
                pending_not = True
                continue
            if term in ("AND", "OR"):
                op = term
                continue
            val = self._eval_pred(term, plist, i, ctx)
            if pending_not:
                val = not val
                pending_not = False
            if result is None:
                result = val
            elif op == "AND":
                result = result and val
            elif op == "OR":
                result = result or val
        return bool(result)

    def _eval_pred(self, pred, plist, i, ctx):
        func, arg = pred
        # nextVowel / prevVowel: scan to the next/previous vowel, skipping consonants
        if func in ("nextVowel", "prevVowel"):
            step = 1 if func == "nextVowel" else -1
            j = i + step
            while 0 <= j < len(plist):
                if plist[j].ph.type == phVOWEL:
                    feat = _FEATURES.get(arg)
                    if feat is not None:
                        return feat(plist[j].ph, plist[j], {})
                    return plist[j].ph.mnemonic == arg
                j += step
            return False
        target_i = {"thisPh": i, "prevPh": i - 1, "nextPh": i + 1, "prev2Ph": i - 2,
                    "prevPhW": i - 1, "nextPhW": i + 1, "prev2PhW": i - 2,
                    "next2Ph": i + 2, "next2PhW": i + 2}.get(func)
        if target_i is None:
            return False
        # *W variants: treat a word boundary as a pause
        within = func in ("prevPhW", "nextPhW", "prev2PhW", "next2PhW")
        if 0 <= target_i < len(plist):
            entry = plist[target_i]
            ph = entry.ph
            if within:
                # crossing a start-of-word boundary -> pause
                if func in ("nextPhW", "next2PhW") and (entry.newword & 1):
                    ph, entry = _PAUSE, None
                elif func in ("prevPhW", "prev2PhW") and (plist[i].newword & 1):
                    ph, entry = _PAUSE, None
        else:
            ph, entry = _PAUSE, None
        feat = _FEATURES.get(arg)
        if feat is not None:
            return feat(ph, entry, ctx if func == "thisPh" else {})
        if arg.startswith("#"):
            # #i / #@ / #o ... — a vowel category. espeak (synthdata.c:583) matches prevPh()
            # / prevPhW() on the previous vowel's END type (a diphthong eI ends in #i), and
            # next/this on the start type. This nulls the palatalising `;` after an i-vowel
            # (af edms spelled E -> ɛɪ;, no ʲ; sq).
            if func in ("prevPh", "prevPhW", "prev2PhW", "prev2Ph") and ph.type == phVOWEL:
                return getattr(ph, "endtype", None) == arg
            return getattr(ph, "starttype", None) == arg
        # otherwise arg is a phoneme mnemonic
        return ph.mnemonic == arg


def _paren_arg(line):
    a = line.find("(")
    b = line.rfind(")")
    if a >= 0 and b > a:
        return line[a + 1:b].strip()
    return ""
