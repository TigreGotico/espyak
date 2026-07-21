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
_SFLAG_SYLLABLE = 0x04  # render.SFLAG_SYLLABLE


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
    # isVelar tests phPLACE_VELAR (==8), set only by the `vel` keyword (lbv is phPLACE_LABIO_VELAR,
    # a different place). isPalatal tests the phPALATAL phflag (bit 9), set by pal/alp/pzd —
    # independent of the place string (e.g. `liquid pzd` is palatal with no place keyword).
    "isVelar": lambda ph, e, ctx: getattr(ph, "place", None) == "vel",
    "isPalatal": lambda ph, e, ctx: "palatal" in ph.flags,
    "isVStop": lambda ph, e, ctx: ph.type == phVSTOP,
    "isUStop": lambda ph, e, ctx: ph.type == phSTOP,
    "isVFricative": lambda ph, e, ctx: ph.type == phVFRICATIVE,
    "isLong": lambda ph, e, ctx: "long" in ph.flags,
    # language-defined phoneme flags (flag1..flag8); e.g. uz front vowels for l-clearing.
    "isFlag1": lambda ph, e, ctx: "flag1" in ph.flags,
    "isFlag2": lambda ph, e, ctx: "flag2" in ph.flags,
    "isFlag3": lambda ph, e, ctx: "flag3" in ph.flags,
    "isFlag4": lambda ph, e, ctx: "flag4" in ph.flags,
    # ba/tt/tr: a phoneme supplied by a dictionary entry (the letter-name 'kA') is "translation
    # given" — its vowel programs (A -> 0 backing) are suppressed, unlike a rules-derived vowel.
    "isTranslationGiven": lambda ph, e, ctx: ctx.get("translation_given", False),
    "isSecondVowel": lambda ph, e, ctx: ctx.get("second_vowel", False),
    "isAfterStress": lambda ph, e, ctx: ctx.get("after_stress", False),
}

# a synthetic pause phoneme stands in at word boundaries for *W predicates


class _Pause:
    type = phPAUSE
    flags = frozenset()
    mnemonic = "_"


_PAUSE = _Pause()

# Context for a target position off the end of the (per-word) phoneme list: espeak's
# phoneme_list always carries trailing clause pauses, so a phoneme at the very end of a
# word is word-final (isWordEnd true) and its off-end neighbour is a pause. The other
# word-scoped features (first/second/final vowel, stress relations) are meaningless for a
# pause and evaluate false, matching the C conditions on a phPAUSE target.
_OFF_END_CTX = {"word_end": True, "first_vowel": False, "second_vowel": False,
                "after_stress": False, "final_vowel": False, "max_stress": False,
                "translation_given": False}


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
        self._insert_done = set()  # phoneme id -> already inserted before itself this pass
        self._ipa_only = False
        i = 0
        while i < len(plist):
            entry = plist[i]
            ph = entry.ph
            if ph.program:
                self._changed = False  # one ChangePhoneme per phoneme interpretation
                ctx = self._context(plist, i)
                self._exec(self._program(ph), plist, i, ctx)
            i += 1
        # espeak re-evaluates context-dependent ipa overrides AFTER all ChangePhonemes are
        # applied (it re-interprets the final list for --ipa rendering). A phoneme whose ipa
        # depends on a NEIGHBOUR that got ChangePhoneme'd must see the new mnemonic: da @-'s
        # `IF nextPhW(r) THEN ipa NULL` must NOT fire once its 'r' neighbour became 'R', so the
        # schwa is kept (operab opəʁ, not opʁ). Second pass re-runs each program applying ONLY
        # ipa statements against the now-final list.
        self._ipa_only = True
        i = 0
        while i < len(plist):
            entry = plist[i]
            if entry.ph.program and not getattr(entry, "deleted", False):
                self._changed = False
                ctx = self._context(plist, i)
                self._exec(self._program(entry.ph), plist, i, ctx)
            i += 1
        self._ipa_only = False
        return plist

    def _context(self, plist, i):
        entry = plist[i]
        # isWordEnd (synthdata.c:611-612): next phoneme starts a word (sourceix) OR is a pause.
        # End-of-list counts (espeak pads a trailing pause).
        word_end = (i + 1 >= len(plist)) or bool(plist[i + 1].newword & 1) \
            or plist[i + 1].ph.type == phPAUSE
        # isFirstVowel/isSecondVowel/isFinalVowel/isAfterStress are scoped to the current WORD
        # (synthdata.c CountVowelPosition stops at sourceix; isFinalVowel/isAfterStress walk to
        # the next/previous word boundary). Use newword&1 marks as the sourceix equivalent.
        ws, we = self._word_bounds(plist, i)
        # isFirstVowel/isSecondVowel (synthdata.c:635-638) test CountVowelPosition(plist)==1/==2,
        # where CountVowelPosition (synthdata.c:454) walks BACKWARD from this phoneme to the word
        # start counting vowels (this phoneme included if it is a vowel). So the flags hold for a
        # CONSONANT sitting after the 1st/2nd vowel too, not only at the vowel itself — e.g. the
        # word-final k of the Malayalam letter name `_ik` counts 1 preceding vowel, so isFirstVowel
        # is true there and the k->g voicing (guarded by NOT isFirstVowel) is correctly suppressed.
        vcount = sum(1 for j in range(ws, i + 1) if plist[j].ph.type == phVOWEL)
        first_vowel = vcount == 1
        second_vowel = vcount == 2
        # isFinalVowel (synthdata.c:625-632) walks FORWARD to the next word boundary; true if no
        # further vowel is found — so it also holds for a trailing consonant after the last vowel.
        final_vowel = not any(plist[j].ph.type == phVOWEL for j in range(i + 1, we))
        # isMaxStress (synthdata.c:440-441): stress_level >= pl->wordstress, where wordstress
        # is the max stresslevel in THIS word (phonemelist.c:227-239) and stress_level is this
        # vowel's level (or the FOLLOWING vowel's if this is a consonant; StressCondition).
        word_max = max((plist[j].stresslevel & 0xf for j in range(ws, we)), default=0)
        if entry.ph.type == phVOWEL:
            sl = entry.stresslevel & 0xf
        elif i + 1 < len(plist) and plist[i + 1].ph.type == phVOWEL:
            sl = plist[i + 1].stresslevel & 0xf
        else:
            sl = -1  # no stress level for this consonant -> StressCondition returns false
        max_stress = sl >= word_max if sl >= 0 else False
        # isAfterStress (synthdata.c:613-622): false at the word-start phoneme; else walk back
        # within the word, true if any prior phoneme carries stresslevel>=4.
        if i <= ws:
            after_stress = False
        else:
            after_stress = any((plist[j].stresslevel & 0xf) >= 4 for j in range(ws, i))
        return {"word_end": word_end, "first_vowel": first_vowel,
                "second_vowel": second_vowel, "after_stress": after_stress,
                "final_vowel": final_vowel, "max_stress": max_stress,
                "translation_given": getattr(self, "_translation_given", False)}

    @staticmethod
    def _word_bounds(plist, i):
        """[start, end) index range of the word containing index i, using newword&1 marks."""
        start = i
        while start > 0 and not (plist[start].newword & 1):
            start -= 1
        end = i + 1
        while end < len(plist) and not (plist[end].newword & 1):
            end += 1
        return start, end

    # -- execution --
    def _exec(self, block, plist, i, ctx):
        target = plist[i] if i < len(plist) else None
        for stmt in block:
            # An InsertPhoneme in an earlier statement inserts a new entry at our index, pushing the
            # phoneme whose program is running one slot right. The remaining statements (e.g. the
            # Indonesian a's ChangeIfUnstressed(a/) after InsertPhoneme(_|) for an a|a hiatus) must
            # still act on that phoneme, not on the freshly-inserted one — re-find it.
            if target is not None and (i >= len(plist) or plist[i] is not target):
                j = i
                while j < len(plist) and plist[j] is not target:
                    j += 1
                if j < len(plist):
                    i = j
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
        if getattr(self, "_ipa_only", False) and head not in ("ipa", "RETURN", "CALL"):
            # second (ipa-only) pass: re-evaluate ipa overrides against the post-ChangePhoneme
            # list without re-applying structural ops (ChangePhoneme/Insert/Append/length/FMT).
            return False
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
        elif head == "AppendPhoneme":
            # insert the phoneme right after this one (Slavic vocalic r* renders ɾ via its
            # `ipa NULL` + AppendPhoneme(*); a diphthong appends a `_|` link before a vowel).
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
            # espeak's CallPhoneme resolves a procedure name first (compiledata.c)
            prog = parse_program(self.source.procedures[ref])
        else:
            # ...then a bare phoneme mnemonic in the current table: `CALL @` runs the
            # called phoneme's whole program inline (synthdata.c i_CALLPH), so en's
            # `phoneme 3 { CALL @ }` inherits @'s IfNextVowelAppend(r-) linking r.
            p = self.table.get(ref)
            if p is not None and p is not plist[i].ph:
                prog = parse_program(p.program)
        if prog:
            self._exec(prog, plist, i, ctx)

    def _change(self, plist, i, mnem, ctx, _depth=0):
        # espeak re-interprets a changed phoneme "but it doesn't obey a second
        # ChangePhoneme()" (synthdata.c). So once a phoneme has been changed in this
        # interpretation, later ChangePhonemes (e.g. via CALL base1/l) are ignored: uz
        # l -> L stays L (ɫ) instead of L -> l/2 (which rendered as a plain 'l').
        if getattr(self, "_changed", False):
            return False
        if mnem == "NULL":
            # ChangePhoneme(NULL) deletes this phoneme (e.g. linking ; before a consonant)
            self._changed = True
            plist[i].deleted = True
            return True
        ph = self.table.get(mnem)
        if ph is None:
            return False
        self._changed = True
        plist[i].ph = ph
        plist[i].ipa_override = None
        # espeak's ReInterpretPhoneme (phonemelist.c): a ChangePhoneme updates SFLAG_SYLLABLE
        # from the new type — set for a vowel, cleared otherwise. So a spelled letter whose
        # vowel turns into a glide (fr cia: i -> j before a) loses its syllable flag and its
        # stress mark (sˌejˈa, not sˌeˌjˈa).
        if ph.type == phVOWEL:
            plist[i].synthflags |= _SFLAG_SYLLABLE
        else:
            plist[i].synthflags &= ~_SFLAG_SYLLABLE
        # re-run the new phoneme's program so ITS ipa / further changes apply (espeak
        # re-interprets the changed phoneme). Guard against ChangePhoneme cycles.
        if ph.program and _depth < 8:
            self._exec(self._program(ph), plist, i, ctx)
        return True  # the changed phoneme's program takes over; stop the old one

    def _insert(self, plist, i, mnem):
        ph = self.table.get(mnem)
        if ph is None:
            return
        # Bound insertion to once per phoneme per pass. The inserting phoneme is re-processed by
        # the main loop (load-bearing for acronym schwa reduction, ms klci), but without this it
        # re-inserts every pass forever when its condition stays true (lt raj -> rajonas hang).
        if id(plist[i]) in self._insert_done:
            return
        self._insert_done.add(id(plist[i]))
        from espyak.render import PhonemeListEntry
        from espyak.phoneme_tab import phVOWEL
        entry = PhonemeListEntry(ph)
        plist.insert(i, entry)
        # espeak (phonemelist.c:308) inserts by OVERWRITING the current slot with the alternative
        # (`plist3->phcode = alternative`) and re-queueing the original for the next iteration; the
        # freshly memset()-ed re-inserted entry gets sourceix=0. So the word-start marker (sourceix)
        # stays on the slot the inserted phoneme now occupies — i.e. it TRANSFERS from the original
        # to the inserted phoneme when the original started the word. Without this, an epenthetic @-
        # inserted before a word-initial `r` sees the `r` still flagged as word-start, so its
        # `IF nextPhW(r) THEN ipa NULL` mis-fails and the schwa is kept (ru радио -> ərˈɑdʲɪo, lt
        # raj -> ərajˈɔnas, instead of rˈɑdʲɪo / rajˈɔnas).
        if plist[i + 1].newword & 1:
            entry.newword |= plist[i + 1].newword
            plist[i + 1].newword = 0
        # espeak (phonemelist.c ~309: "if we insert a phoneme before a vowel then we loose the
        # stress"): the inserted phoneme takes the vowel's stress slot, and since it is
        # non-syllabic the stress no longer renders — the vowel is effectively diminished. In a
        # spelled acronym the 'i' name aɪ inserts _| after the preceding letter's final vowel and
        # so drops its secondary (ms cimb -> sˌiːaɪˌɛmbˈiː, the aɪ bare, not sˌiːˌaɪˌɛmbˈiː).
        orig = plist[i + 1]
        if orig.ph.type == phVOWEL:
            was = orig.stresslevel
            entry.stresslevel = was
            orig.stresslevel = 0
            if was >= 4:
                # the diminished vowel carried the PRIMARY — promote it back to the previous
                # syllabic vowel (MakePhonemeList promotion): ms klci, the final aɪ tonic moves
                # to the c's iː -> kˌeəlsˈiːaɪ, not a primary-less kˌeəlsˌiːaɪ.
                for j in range(i - 1, -1, -1):
                    if plist[j].ph.type == phVOWEL:
                        plist[j].stresslevel = was
                        break
        # The main loop already passed index i (the inserting phoneme is now at i+1), so the
        # inserted phoneme would never get its own program run. Run it now so e.g. the
        # epenthetic @- before 'r' applies its conditional `ipa NULL` (ru при -> prʲɪ, not
        # pərʲɪ). Inserted phonemes here don't themselves InsertPhoneme, so no recursion.
        if ph.program:
            saved = getattr(self, "_changed", False)  # inserted phoneme = own interpretation
            self._changed = False
            self._exec(self._program(ph), plist, i, self._context(plist, i))
            self._changed = saved

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
                # nextVowel/prevVowel do NOT cross a word boundary (synthdata.c:532-546):
                # nextVowel returns false if it meets a word-start (sourceix) before the vowel;
                # prevVowel is scoped to the previous vowel of THIS word. A word boundary is the
                # newword&1 mark on the first phoneme of a word — so for the backward scan the
                # boundary sits ON a word-start phoneme (which may itself be that word's vowel:
                # test it before bailing). This stops ru `V`(-дцать) from reaching the following
                # number word's stressed vowel across a `||` join: двенадцать||тысяч keeps `V`->ʌ
                # (dvʲɪnˈɑttsʌtʲ), while двадцать+два within one word crosses to два (…tsatʲ…).
                # nextVowel (forward) tests the boundary FIRST (synthdata.c:534): a word-start
                # ends the scan even if that phoneme is itself a vowel. prevVowel (backward) is the
                # previous vowel in this word, so a vowel sitting ON the word-start still counts —
                # test the vowel first, then stop at the boundary.
                at_boundary = bool(plist[j].newword & _START_OF_WORD)
                if step > 0 and at_boundary:
                    return False
                if plist[j].ph.type == phVOWEL:
                    feat = _FEATURES.get(arg)
                    if feat is not None:
                        # context-dependent features (isMaxStress, isFirstVowel, …) must be
                        # evaluated for the SCANNED vowel's own position, not with an empty
                        # context — espeak re-runs the predicate at that phoneme.
                        return feat(plist[j].ph, plist[j], self._context(plist, j))
                    return plist[j].ph.mnemonic == arg
                if at_boundary:  # backward scan reached this word's start with no vowel
                    return False
                j += step
            return False
        # espeak merges a length marker (:) into the preceding vowel (SFLAG_LENGTHEN), so it is
        # not a separate phoneme at program time and prev*/next* step over it to the real
        # neighbour. A spelled letter ending in i: then lets the next letter's vowel (aɪ) see a
        # vowel via prevPh — the aɪ's InsertPhoneme(_|) fires and it loses its secondary.
        def _back(k):
            while 1 <= k and plist[k].ph.mnemonic == ":":
                k -= 1
            return k

        def _fwd(k):
            while k < len(plist) and plist[k].ph.mnemonic == ":":
                k += 1
            return k
        target_i = {"thisPh": i, "prevPh": _back(i - 1), "nextPh": _fwd(i + 1),
                    "prev2Ph": _back(_back(i - 1) - 1), "prevPhW": _back(i - 1),
                    "nextPhW": _fwd(i + 1), "prev2PhW": _back(_back(i - 1) - 1),
                    "next2Ph": _fwd(_fwd(i + 1) + 1),
                    "next2PhW": _fwd(_fwd(i + 1) + 1)}.get(func)
        if target_i is None:
            return False
        # *PhW variants do NOT cross a word boundary: espeak (synthdata.c:497-516) returns
        # false for the whole condition when the boundary is hit, rather than evaluating on a
        # pause. prevPhW fails if THIS phoneme starts a word; nextPhW if the next one does; the
        # 2-step variants if either intervening phoneme starts a word. (it ibm: the first
        # spelled letter's prevPhW(isNotVowel) then fails, so its `i` is not reduced to ɪ.)
        within = func in ("prevPhW", "nextPhW", "prev2PhW", "next2PhW")
        if within:
            def _ws(k):
                return 0 <= k < len(plist) and (plist[k].newword & 1)
            if func == "prevPhW" and _ws(i):
                return False
            if func == "prev2PhW" and (_ws(i) or i - 1 < 0 or _ws(i - 1)):
                return False
            if func == "nextPhW" and (i + 1 >= len(plist) or _ws(i + 1)):
                return False
            if func == "next2PhW" and (
                    i + 1 >= len(plist) or _ws(i + 1) or i + 2 >= len(plist) or _ws(i + 2)):
                return False
        if 0 <= target_i < len(plist):
            entry = plist[target_i]
            ph = entry.ph
        else:
            ph, entry = _PAUSE, None
        feat = _FEATURES.get(arg)
        if feat is not None:
            # Position-relative features (isWordEnd, isFinalVowel, isMaxStress, ...) are a
            # property of whichever phoneme the predicate points at, not of thisPh: espeak
            # re-derives them from the target's own position (synthdata.c evaluates the
            # condition after advancing `plist` to prevPh/nextPh/next2Ph). Compute the
            # target's context so e.g. `nextPh(isWordEnd)` sees the next phoneme's word-end
            # status (tr `e -> &` before a word-final nasal: ben -> bˈæn).
            if func == "thisPh":
                tctx = ctx
            elif 0 <= target_i < len(plist):
                tctx = self._context(plist, target_i)
            else:
                tctx = _OFF_END_CTX
            return feat(ph, entry, tctx)
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
