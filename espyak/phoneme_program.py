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
        arg = _paren_arg(line)
        if head == "ChangePhoneme":
            self._change(plist, i, arg)
        elif head == "InsertPhoneme":
            self._insert(plist, i, arg)
        elif head in ("ChangeIfDiminished", "ChangeIfUnstressed",
                      "ChangeIfNotStressed", "ChangeIfStressed"):
            lvl = plist[i].stresslevel
            cond = {
                "ChangeIfDiminished": lvl == 0,
                "ChangeIfUnstressed": lvl <= 1,
                "ChangeIfNotStressed": lvl < 4,
                "ChangeIfStressed": lvl >= 4,
            }[head]
            if cond:
                self._change(plist, i, arg)
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

    def _change(self, plist, i, mnem):
        ph = self.table.get(mnem)
        if ph is not None:
            plist[i].ph = ph

    def _insert(self, plist, i, mnem):
        ph = self.table.get(mnem)
        if ph is None:
            return
        from espyak.render import PhonemeListEntry
        entry = PhonemeListEntry(ph)
        plist.insert(i, entry)

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
        target_i = {"thisPh": i, "prevPh": i - 1, "nextPh": i + 1,
                    "prevPhW": i - 1, "nextPhW": i + 1, "next2Ph": i + 2}.get(func)
        if target_i is None:
            return False
        # *W variants: treat a word boundary as a pause
        within = func in ("prevPhW", "nextPhW")
        if 0 <= target_i < len(plist):
            entry = plist[target_i]
            ph = entry.ph
            if within:
                # crossing a start-of-word boundary -> pause
                if func == "nextPhW" and (entry.newword & 1):
                    ph, entry = _PAUSE, None
                elif func == "prevPhW" and (plist[i].newword & 1):
                    ph, entry = _PAUSE, None
        else:
            ph, entry = _PAUSE, None
        feat = _FEATURES.get(arg)
        if feat is not None:
            return feat(ph, entry, ctx if func == "thisPh" else {})
        # otherwise arg is a phoneme mnemonic
        return ph.mnemonic == arg


def _paren_arg(line):
    a = line.find("(")
    b = line.rfind(")")
    if a >= 0 and b > a:
        return line[a + 1:b].strip()
    return ""
