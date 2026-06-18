"""Letter-to-sound matcher: port of the core of espeak-ng's dictionary.c.

  - MatchRule       (the rule scoring state machine)
  - TranslateRules  (the per-word driver: group selection, endings, retranslation)
  - AppendPhonemes  (vowel/stress counting used by @ and & rules)
  - IsLetter / IsLetterGroup / IsDigit helpers

The matcher walks each compiled rule's instruction stream (produced by rule_compiler)
exactly as espeak walks the compiled byte stream, so the point arithmetic and the
last-best-wins tie-break are reproduced. Phonemes are accumulated as mnemonic strings.

Reference: espeak-ng 1.52.0 dictionary.c (MatchRule:1484, TranslateRules:2080).
"""
from espyak import constants as K
from espyak.phoneme_tab import phVOWEL, phSTRESS, phLIQUID

REPLACED_E = ord("E")

# default English letter classification (tr_languages.c NewTranslator lines 277-284)
_DEFAULT_LETTER_BITS = {
    K.LETTERGP_A: "aeiou",
    K.LETTERGP_B: "bcdfgjklmnpqstvxz",
    K.LETTERGP_C: "bcdfghjklmnpqrstvwxz",
    K.LETTERGP_H: "hlmnr",
    K.LETTERGP_F: "cfhkpqstx",
    K.LETTERGP_G: "bdgjlmnrvwyz",
    K.LETTERGP_Y: "eiy",
    K.LETTERGP_VOWEL2: "aeiouy",
}


def _utf8_in(buf, i):
    """Decode one UTF-8 char forward at byte index i. Returns (codepoint, nbytes)."""
    if i >= len(buf):
        return 0, 1
    c = buf[i]
    if c < 0x80:
        return c, 1
    if c & 0xe0 == 0xc0:
        n = 2
    elif c & 0xf0 == 0xe0:
        n = 3
    elif c & 0xf8 == 0xf0:
        n = 4
    else:
        return c, 1
    try:
        return ord(buf[i:i + n].decode("utf-8")), n
    except (UnicodeDecodeError, ValueError):
        return c, 1


def _utf8_back(buf, i):
    """Decode the UTF-8 char ending at index i (i points at its last byte going back).

    Returns (codepoint, nbytes) where the char starts at i-(nbytes-1).
    """
    if i < 0:
        return 0, 1
    start = i
    while start > 0 and (buf[start] & 0xc0) == 0x80:
        start -= 1
    n = i - start + 1
    try:
        return ord(buf[start:start + n].decode("utf-8")), n
    except (UnicodeDecodeError, ValueError):
        return buf[i], 1


class Translator:
    """Translator state for the rules engine, configured per language."""

    def __init__(self, phsource=None, config=None):
        self.letter_bits = [0] * 256
        self.letter_groups = [None] * 8     # wchar overrides per group (None = use bits)
        self.letter_bits_offset = 0
        self.dict_condition = 0
        self.expect_verb = 0
        self.word_vowel_count = 0
        self.word_stressed_count = 0
        self.phsource = phsource
        if config is None:
            config = {
                "stress_rule": K.STRESSPOSN_2R, "stress_flags": 0,
                "unstressed_wd1": 1, "unstressed_wd2": 3, "translator_name": 0,
                "letter_bits": dict(_DEFAULT_LETTER_BITS),
                "extra_vowels": "", "extra_consonants": "",
            }
        self.config = config
        self.stress_rule = config.get("stress_rule", K.STRESSPOSN_2R)
        self.stress_flags = config.get("stress_flags", 0)
        self.unstressed_wd1 = config.get("unstressed_wd1", 1)
        self.unstressed_wd2 = config.get("unstressed_wd2", 3)
        self.translator_name = config.get("translator_name", 0)
        self._setup_letters(config)

    def _setup_letters(self, config):
        for group, letters in config.get("letter_bits", _DEFAULT_LETTER_BITS).items():
            bits = 1 << group
            for ch in letters:
                if ord(ch) < 256:
                    self.letter_bits[ord(ch)] |= bits
        # SetLetterVowel: extra vowels go into groups A and VOWEL2
        for ch in config.get("extra_vowels", ""):
            if ord(ch) < 256:
                self.letter_bits[ord(ch)] |= (1 << K.LETTERGP_A) | (1 << K.LETTERGP_VOWEL2)
        for ch in config.get("extra_consonants", ""):
            if ord(ch) < 256:
                self.letter_bits[ord(ch)] |= (1 << K.LETTERGP_C)
        # SetLetterBits(group, letters): OR letters into a specific group
        for group, letters in config.get("set_letter_bits", []):
            for ch in letters:
                if ord(ch) < 256:
                    self.letter_bits[ord(ch)] |= (1 << group)

    def is_letter(self, letter, group):
        # port of IsLetter (dictionary.c:770)
        if group < 8 and self.letter_groups[group] is not None:
            return 1 if chr(letter) in self.letter_groups[group] else 0
        if group > 7:
            return 0
        if self.letter_bits_offset > 0:
            l2 = letter - self.letter_bits_offset
            if 0 < l2 < 0x100:
                letter = l2
            else:
                return 0
        if 0 <= letter < 0x100:
            return 1 if (self.letter_bits[letter] & (1 << group)) else 0
        return 0

    def is_vowel(self, letter):
        return self.is_letter(letter, K.LETTERGP_VOWEL2)


# mnem_flags table (compiledict.c) — keyword -> flag code value
_MNEM_FLAGS = {
    "$1": 0x41, "$2": 0x42, "$3": 0x43, "$4": 0x44, "$5": 0x45, "$6": 0x46, "$7": 0x47,
    "$u": 0x48, "$u1": 0x49, "$u2": 0x4a, "$u3": 0x4b,
    "$u+": 0x4c, "$u1+": 0x4d, "$u2+": 0x4e, "$u3+": 0x4f,
    "$pause": 8, "$strend": 9, "$strend2": 10, "$unstressend": 11,
    "$accent_before": 12, "$abbrev": 13, "$double": 14,
    "$alt": 15, "$alt1": 15, "$alt2": 16, "$alt3": 17, "$alt4": 18, "$alt5": 19,
    "$alt6": 20, "$alt7": 21, "$combine": 23, "$dot": 24, "$hasdot": 25,
    "$max3": 27, "$brk": 28, "$text": 29,
    "$verbf": 0x20, "$verbsf": 0x21, "$nounf": 0x22, "$pastf": 0x23,
    "$verb": 0x24, "$noun": 0x25, "$past": 0x26, "$verbextend": 0x28,
    "$capital": 0x29, "$allcaps": 0x2a, "$accent": 0x2b, "$sentence": 0x2d,
    "$only": 0x2e, "$onlys": 0x2f, "$stem": 0x30, "$atend": 0x31, "$atstart": 0x32,
    "$native": 0x33, "$textmode": 200, "$phonememode": 201,
}


class DictEntry:
    __slots__ = ("phonemes", "flag_codes", "multiword", "rest")

    def __init__(self, phonemes, flag_codes, multiword=False, rest=""):
        self.phonemes = phonemes
        self.flag_codes = flag_codes
        self.multiword = multiword
        self.rest = rest


class DictList:
    """Parsed <lang>_list (+_extra): word -> entries, with espeak's selection logic."""

    def __init__(self):
        self.words = {}     # lowercase word -> list[DictEntry] in file order
        self.text_mode = False

    @classmethod
    def load(cls, *paths):
        dl = cls()
        for path in paths:
            if path:
                dl._parse_file(path)
        return dl

    def _parse_file(self, path):
        try:
            fh = open(path, encoding="utf-8", errors="replace")
        except OSError:
            return
        with fh:
            for raw in fh:
                self._parse_line(raw)

    def _parse_line(self, raw):
        ix = raw.find("//")
        if ix >= 0:
            raw = raw[:ix]
        line = raw.strip()
        if not line:
            return
        flag_codes = []
        rest_words = ""
        # multi-word entry "(w1 w2 ...)"
        if line[0] == "(":
            close = line.find(")")
            if close < 0:
                return
            inside = line[1:close].split()
            word = inside[0] if inside else ""
            rest_words = " ".join(inside[1:])
            tokens = line[close + 1:].split()
            multiword = True
        else:
            toks = line.split()
            word = toks[0]
            tokens = toks[1:]
            multiword = False
        phon_tokens = []
        for tok in tokens:
            if tok.startswith("?"):
                neg = tok[1] == "!" if len(tok) > 1 else False
                num = "".join(ch for ch in tok if ch.isdigit())
                if num:
                    flag_codes.append(int(num) + (132 if neg else 100))
            elif tok.startswith("$"):
                val = _MNEM_FLAGS.get(tok)
                if val == 200:
                    self.text_mode = True
                elif val == 201:
                    self.text_mode = False
                elif val is not None:
                    flag_codes.append(val)
            else:
                phon_tokens.append(tok)
        phonemes = " ".join(phon_tokens)
        entry = DictEntry(phonemes, flag_codes, multiword, rest_words)
        self.words.setdefault(word.lower(), []).append(entry)

    def lookup(self, word, ctx):
        """Return (phonemes_or_None, flags1) or (None, None) if not found.

        Port of LookupDict2 selection: iterate entries last-in-file first, apply
        condition/flag checks against the context (an LookupContext). A returned
        phonemes of "" with flags1!=None means flags-only (use rules).
        """
        entries = self.words.get(word.lower())
        if not entries:
            return None, None
        for entry in reversed(entries):
            ok, flags1, flags2, stress = self._eval(entry, ctx)
            if not ok:
                continue
            flags1 = (flags1 & ~0xf) | stress if stress is not None else flags1
            return entry.phonemes, flags1
        return None, None

    def _eval(self, entry, ctx):
        flags1 = 0
        flags2 = 0
        stress = None
        for flag in entry.flag_codes:
            if flag >= 100:
                if flag >= 132:
                    if (ctx.dict_condition & (1 << (flag - 132))) != 0:
                        return False, 0, 0, None
                else:
                    if (ctx.dict_condition & (1 << (flag - 100))) == 0:
                        return False, 0, 0, None
            elif flag > 80:
                return False, 0, 0, None  # multi-word skipwords: no match for isolated word
            elif flag > 64:
                stress = flag & 0xf
                if (flag & 0xc) == 0xc:
                    flags1 |= K.FLAG_STRESS_END
            elif flag >= 32:
                flags2 |= (1 << (flag - 32))
            else:
                flags1 |= (1 << flag)
        if entry.multiword:
            return False, 0, 0, None  # following words can't match an isolated word
        # condition checks (LookupDict2 tail)
        if (flags2 & K.FLAG_STEM) and not ctx.suffix_removed:
            return False, 0, 0, None
        if (flags2 & K.FLAG_CAPITAL) and not ctx.first_upper:
            return False, 0, 0, None
        if (flags2 & K.FLAG_ALLCAPS) and not ctx.all_upper:
            return False, 0, 0, None
        if (flags1 & K.FLAG_NEEDS_DOT) and not ctx.has_dot:
            return False, 0, 0, None
        if (flags2 & K.FLAG_ATEND) and not ctx.at_end:
            return False, 0, 0, None
        if (flags2 & K.FLAG_ATSTART) and not ctx.first_word:
            return False, 0, 0, None
        if (flags2 & K.FLAG_SENTENCE) and not ctx.sentence:
            return False, 0, 0, None
        if (flags2 & K.FLAG_VERB) and not ctx.expect_verb:
            return False, 0, 0, None
        if (flags2 & K.FLAG_PAST) and not ctx.expect_past:
            return False, 0, 0, None
        if (flags2 & K.FLAG_NOUN) and not ctx.expect_noun:
            return False, 0, 0, None
        return True, flags1, flags2, stress


class LookupContext:
    """Per-word context for dictionary selection (isolated-word defaults)."""

    def __init__(self, first_upper=False, all_upper=False, has_dot=False,
                 first_word=True, at_end=True, sentence=True, dict_condition=0,
                 expect_verb=0, expect_noun=0, expect_past=0, suffix_removed=False):
        self.first_upper = first_upper
        self.all_upper = all_upper
        self.has_dot = has_dot
        self.first_word = first_word
        self.at_end = at_end
        self.sentence = sentence
        self.dict_condition = dict_condition
        self.expect_verb = expect_verb
        self.expect_noun = expect_noun
        self.expect_past = expect_past
        self.suffix_removed = suffix_removed


def is_digit(c):
    return ord("0") <= c <= ord("9")


def is_alpha(wc):
    return chr(wc).isalpha() if wc else False


def count_vowels(tr, ph, mnem_index):
    """Port of AppendPhonemes' vowel/stress counting over a mnemonic phoneme string.

    Updates tr.word_vowel_count and tr.word_stressed_count. `mnem_index` maps a phoneme
    mnemonic -> Phoneme; multi-char mnemonics are matched greedily.
    """
    unstress_mark = False
    i = 0
    n = len(ph)
    maxlen = mnem_index.maxlen
    while i < n:
        if ph[i] in (" ", "\t", "|"):
            i += 1
            continue
        m = None
        for L in range(min(maxlen, n - i), 0, -1):
            cand = ph[i:i + L]
            if cand in mnem_index.table:
                m = cand
                break
        if m is None:
            i += 1
            continue
        p = mnem_index.table[m]
        i += len(m)
        if p.type == phSTRESS:
            if p.stress_type < 4:
                unstress_mark = True
        elif p.type == phVOWEL:
            if ("unstressed" not in p.flags) and (not unstress_mark):
                tr.word_stressed_count += 1
            unstress_mark = False
            tr.word_vowel_count += 1


class MnemIndex:
    """Greedy mnemonic lookup over a phoneme table (for vowel counting / stress)."""

    def __init__(self, phoneme_table):
        self.table = phoneme_table.phonemes
        self.maxlen = max((len(m) for m in self.table), default=1)

    def tokenize(self, ph):
        """Greedy split of a mnemonic phoneme string into [(mnemonic, Phoneme), ...]."""
        toks = []
        i, n = 0, len(ph)
        while i < n:
            if ph[i] in (" ", "\t", "|"):
                i += 1
                continue
            m = None
            for L in range(min(self.maxlen, n - i), 0, -1):
                cand = ph[i:i + L]
                if cand in self.table:
                    m = cand
                    break
            if m is None:
                i += 1
                continue
            toks.append((m, self.table[m]))
            i += len(m)
        return toks


# stress level -> stress mnemonic to insert (stress_phonemes[] indexed by v_stress).
# 1 (unstressed) is never inserted. Renderer maps these back via stress_type.
_STRESS_MNEM = {0: "%%", 2: ",", 3: ",,", 4: "'", 5: "''", 6: "'!"}

# synthesize.h stress levels
STRESS_IS_DIMINISHED = 0
STRESS_IS_UNSTRESSED = 1
STRESS_IS_NOT_STRESSED = 2
STRESS_IS_SECONDARY = 3
STRESS_IS_PRIMARY = 4
STRESS_IS_PRIORITY = 5

# stress_rule values
STRESSPOSN_2R = K.STRESSPOSN_2R


def _ph_is_vowel(p):
    return p.type == phVOWEL and "nonsyllabic" not in p.flags


def get_vowel_stress(toks, stressed_syllable=0):
    """Port of GetVowelStress. Returns (vowel_stress list, phonetic toks, count, primary).

    `phonetic` is the token stream with stress markers removed (as ph_out in C).
    vowel_stress is indexed 1..count-1 (index 0 unused/sentinel).
    """
    vowel_stress = [STRESS_IS_UNSTRESSED]  # index 0
    phonetic = []
    count = 1
    max_stress = -1
    stress = -1
    primary_posn = 0
    for mnem, ph in toks:
        if ph.type == phSTRESS:
            if mnem == "=":
                # phonSTRESS_PREV: place primary stress on the PRECEDING stressable vowel
                j = count - 1
                while (j > 0) and (stressed_syllable == 0) and (vowel_stress[j] < STRESS_IS_PRIMARY):
                    if vowel_stress[j] not in (STRESS_IS_DIMINISHED, STRESS_IS_UNSTRESSED):
                        vowel_stress[j] = STRESS_IS_PRIMARY
                        if max_stress < STRESS_IS_PRIMARY:
                            max_stress = STRESS_IS_PRIMARY
                            primary_posn = j
                        for ix in range(1, j):
                            if vowel_stress[ix] == STRESS_IS_PRIMARY:
                                vowel_stress[ix] = STRESS_IS_SECONDARY
                        break
                    j -= 1
                continue
            # stress marker for the following vowel
            if (ph.stress_type < 4) or (stressed_syllable == 0):
                stress = ph.stress_type
                if stress > max_stress:
                    max_stress = stress
            continue
        if _ph_is_vowel(ph):
            vowel_stress.append(stress)
            if stress >= STRESS_IS_PRIMARY and stress >= max_stress:
                primary_posn = count
                max_stress = stress
            if stress < 0 and "unstressed" in ph.flags:
                vowel_stress[count] = STRESS_IS_UNSTRESSED
            count += 1
            stress = -1
        phonetic.append((mnem, ph))
    vowel_stress.append(STRESS_IS_UNSTRESSED)
    return vowel_stress, phonetic, count, primary_posn, max_stress


def set_word_stress(tr, phoneme_str, mnem_index, dict_flags=0, tonic=-1, control=0):
    """Port of SetWordStress (dictionary.c:919) for stress_rule=STRESSPOSN_2R and the
    common path. Returns the phoneme string with stress mnemonics inserted.
    """
    toks = mnem_index.tokenize(phoneme_str)
    if not toks:
        return phoneme_str
    stressflags = tr.stress_flags

    unstressed_word = False
    stressed_syllable = dict_flags & 0x7
    if dict_flags & 0x8:
        stressed_syllable = dict_flags & 0x3
        unstressed_word = True

    vowel_stress, phonetic, vowel_count, primary_posn, max_stress = get_vowel_stress(
        toks, stressed_syllable)
    max_stress_input = max_stress
    if stressed_syllable > 0:
        if stressed_syllable >= vowel_count:
            stressed_syllable = vowel_count - 1
        vowel_stress[stressed_syllable] = STRESS_IS_PRIMARY
        max_stress = STRESS_IS_PRIMARY
        primary_posn = stressed_syllable
    if max_stress < 0 and dict_flags is not None:
        max_stress = STRESS_IS_DIMINISHED

    # GetVowelStress sets *stressed_syllable = primary_posn: an explicit primary stress
    # marker (or $N flag) fixes the stressed syllable, so the stress_rule below is
    # skipped (its guard is `stressed_syllable == 0`). Without this, words with explicit
    # stress get a second primary from the penultimate rule (méxico -> mˈɛxˈiko).
    stressed_syllable = primary_posn

    # syllable weights (heavy/light)
    consonant_types_set = (phVOWEL,)  # placeholder; weight calc below uses types
    vowel_length = [0] * (vowel_count + 2)
    syllable_weight = [0] * (vowel_count + 2)
    _compute_weights(phonetic, vowel_length, syllable_weight)

    # stress rule
    if tr.stress_rule == STRESSPOSN_2R:
        if stressed_syllable == 0:
            max_stress = STRESS_IS_PRIMARY
            if vowel_count > 2:
                stressed_syllable = vowel_count - 2
                if vowel_stress[stressed_syllable] in (STRESS_IS_DIMINISHED, STRESS_IS_UNSTRESSED):
                    stressed_syllable = stressed_syllable - 1 if stressed_syllable > 1 else stressed_syllable + 1
            else:
                stressed_syllable = 1
            if vowel_stress[stressed_syllable] < 0:
                if (vowel_stress[stressed_syllable - 1] < STRESS_IS_PRIMARY) or (vowel_stress[stressed_syllable + 1] < STRESS_IS_PRIMARY):
                    vowel_stress[stressed_syllable] = max_stress
    # STRESSPOSN_1L (first syllable) has no case in espeak's switch: the secondary-stress
    # loop below places the primary on the first eligible vowel (trochaic), so we do
    # nothing here.
    elif tr.stress_rule == K.STRESSPOSN_1R:
        if stressed_syllable == 0:
            stressed_syllable = vowel_count - 1
            while stressed_syllable > 0:
                if vowel_stress[stressed_syllable] < STRESS_IS_DIMINISHED:
                    vowel_stress[stressed_syllable] = STRESS_IS_PRIMARY
                    break
                stressed_syllable -= 1
            max_stress = STRESS_IS_PRIMARY

    # guess complete stress pattern (secondary stresses)
    stress = STRESS_IS_PRIMARY if max_stress < STRESS_IS_PRIMARY else STRESS_IS_SECONDARY
    done = False
    first_primary = 0
    for v in range(1, vowel_count):
        if vowel_stress[v] < STRESS_IS_DIMINISHED:
            if (stressflags & 0x10) and (stress < STRESS_IS_PRIMARY) and (v == vowel_count - 1):
                pass  # S_FINAL_NO_2
            elif (stressflags & 0x8000) and not done:
                vowel_stress[v] = stress
                done = True
                stress = STRESS_IS_SECONDARY
            elif (vowel_stress[v - 1] <= STRESS_IS_UNSTRESSED) and (
                (vowel_stress[v + 1] <= STRESS_IS_UNSTRESSED)
                or (stress == STRESS_IS_PRIMARY and vowel_stress[v + 1] <= STRESS_IS_NOT_STRESSED)
            ):
                if stress == STRESS_IS_SECONDARY and (stressflags & K.S_NO_AUTO_2):
                    continue
                vowel_stress[v] = stress
                done = True
                stress = STRESS_IS_SECONDARY
        if vowel_stress[v] >= STRESS_IS_PRIMARY:
            if first_primary == 0:
                first_primary = v
            elif stressflags & K.S_FIRST_PRIMARY:
                vowel_stress[v] = STRESS_IS_SECONDARY

    if unstressed_word and tonic < 0:
        tonic = tr.unstressed_wd1 if vowel_count <= 2 else tr.unstressed_wd2

    max_stress = STRESS_IS_DIMINISHED
    max_stress_posn = 0
    for v in range(1, vowel_count):
        if vowel_stress[v] >= max_stress:
            max_stress = vowel_stress[v]
            max_stress_posn = v
    if tonic >= 0:
        if (tonic > max_stress) or (max_stress <= STRESS_IS_PRIMARY):
            vowel_stress[max_stress_posn] = tonic
        max_stress = tonic

    # produce output: walk phonetic, insert stress mnemonic before each vowel
    out = []
    v = 1
    for mnem, ph in phonetic:
        if _ph_is_vowel(ph):
            v_stress = vowel_stress[v]
            if v_stress <= STRESS_IS_UNSTRESSED:
                if (v > 1) and (max_stress >= 2) and (stressflags & K.S_FINAL_DIM) and (v == vowel_count - 1):
                    v_stress = STRESS_IS_DIMINISHED
                elif (stressflags & K.S_NO_DIM) or (v == 1) or (v == vowel_count - 1):
                    v_stress = STRESS_IS_UNSTRESSED
                elif (v == vowel_count - 2) and (vowel_stress[vowel_count - 1] <= STRESS_IS_UNSTRESSED):
                    v_stress = STRESS_IS_UNSTRESSED
                else:
                    if (vowel_stress[v - 1] < STRESS_IS_DIMINISHED) or ((stressflags & K.S_MID_DIM) == 0):
                        v_stress = STRESS_IS_DIMINISHED
                        vowel_stress[v] = v_stress
            if (v_stress == STRESS_IS_DIMINISHED) or (v_stress > STRESS_IS_UNSTRESSED):
                out.append(_STRESS_MNEM.get(v_stress, ""))
            v += 1
        out.append(mnem)
    return "".join(out)


def _compute_weights(phonetic, vowel_length, syllable_weight):
    # port of the heavy/light syllable loop (dictionary.c:1002-1026)
    # consonant_types[16] = {0,0,0,1,1,1,1,1,1,1,0,...}: phVOWEL(3)..phNASAL(9) are consonants
    consonant_types = {K.phVOWEL, phLIQUID, K.phSTOP, K.phVSTOP,
                       K.phFRICATIVE, K.phVFRICATIVE, K.phNASAL}
    ix = 1
    n = len(phonetic)
    i = 0
    while i < n:
        mnem, ph = phonetic[i]
        if _ph_is_vowel(ph):
            weight = 0
            nxt = phonetic[i + 1][1] if i + 1 < n else None
            lengthened = nxt is not None and nxt.mnemonic == ":"
            if lengthened or ("long" in ph.flags):
                weight += 1
            vowel_length[ix] = weight
            j = i + 1
            if lengthened:
                j += 1
            c1 = phonetic[j][1] if j < n else None
            c2 = phonetic[j + 1][1] if j + 1 < n else None
            if c1 is not None and c1.type in consonant_types and (
                (c2 is None or c2.type != phVOWEL) or ("long" in c1.flags)
            ):
                weight += 1
            syllable_weight[ix] = weight
            ix += 1
        i += 1


def phLIQUID_T():
    return 4  # phLIQUID


class MatchRecord:
    __slots__ = ("points", "phonemes", "end_type", "del_fwd")

    def __init__(self):
        self.points = 0
        self.phonemes = ""
        self.end_type = 0
        self.del_fwd = None


def _letter_group_no(b):
    g = b - ord("A")
    if g < 0:
        g += 256
    return g


def match_rule(tr, buf, ix_word, group_length, rules, word_flags, dict_flags):
    """Port of MatchRule (dictionary.c:1484).

    buf: word bytes, framed as b"\\x00 <word> \\x00". ix_word: index of current group.
    rules: list[CompiledRule]. Returns (MatchRecord best, new_ix_word).
    """
    best = MatchRecord()
    total_consumed = 0
    common_phonemes = None  # unused (each rule carries its phonemes)

    for cr in rules:
        prog = cr.prog
        klen = len(prog)
        k = 0
        check_atstart = False
        consumed = 0
        distance_left = -2
        distance_right = -6
        failed = 0
        unpron_ignore = word_flags & K.FLAG_UNPRON_TEST
        match_type = 0
        letter_w = 0
        last_letter_w = 0
        points = 1
        end_type = 0
        del_fwd = None

        pre_ptr = ix_word
        post_ptr = ix_word + group_length

        while not failed:
            if k >= klen:
                failed = 2  # reached end of instruction stream => matched
                break
            rb = prog[k]; k += 1
            add_points = 0

            if rb <= K.RULE_LINENUM:
                if rb == K.RULE_PRE_ATSTART:
                    check_atstart = True
                    unpron_ignore = 0
                    match_type = K.RULE_PRE
                elif rb == K.RULE_PRE:
                    match_type = K.RULE_PRE
                    if word_flags & K.FLAG_UNPRON_TEST:
                        failed = 1
                elif rb == K.RULE_POST:
                    match_type = K.RULE_POST
                elif rb == K.RULE_CONDITION:
                    condition_num = prog[k]; k += 1
                    if condition_num >= 32:
                        if (tr.dict_condition & (1 << (condition_num - 32))) != 0:
                            failed = 1
                    else:
                        if (tr.dict_condition & (1 << condition_num)) == 0:
                            failed = 1
                    if not failed:
                        points += 1
                # RULE_PHONEMES / RULE_PH_COMMON / RULE_LINENUM not present in prog
                continue

            if match_type == 0:
                # consume this letter
                letter = buf[post_ptr] if post_ptr < len(buf) else 0
                post_ptr += 1
                if (letter == rb) or (letter == REPLACED_E and rb == ord("e")):
                    if (letter & 0xc0) != 0x80:
                        add_points = 21
                    consumed += 1
                else:
                    failed = 1
            elif match_type == K.RULE_POST:
                distance_right += 6
                if distance_right > 18:
                    distance_right = 19
                last_letter_w = letter_w
                if post_ptr - 1 >= 0 and buf[post_ptr - 1] == 0:
                    failed = 1
                else:
                    letter_w, nb = _utf8_in(buf, post_ptr)
                    letter_xbytes = nb - 1
                    letter = buf[post_ptr] if post_ptr < len(buf) else 0
                    post_ptr += 1
                    failed, add_points, post_ptr, k, rule_end = _match_post(
                        tr, rb, prog, k, buf, letter, letter_w, letter_xbytes,
                        last_letter_w, distance_right, post_ptr, word_flags, dict_flags)
                    if rule_end:
                        end_type = rule_end
            elif match_type == K.RULE_PRE:
                distance_left += 2
                if distance_left > 18:
                    distance_left = 19
                if pre_ptr < 0 or buf[pre_ptr] == 0:
                    failed = 1
                else:
                    last_letter_w, _ = _utf8_in(buf, pre_ptr)
                    pre_ptr -= 1
                    letter_w, nb = _utf8_back(buf, pre_ptr)
                    letter_xbytes = nb - 1
                    letter = buf[pre_ptr] if pre_ptr >= 0 else 0
                    failed, add_points, pre_ptr, k = _match_pre(
                        tr, rb, prog, k, buf, letter, letter_w, letter_xbytes,
                        last_letter_w, distance_left, distance_right, pre_ptr, word_flags, dict_flags)

            if failed == 0:
                points += add_points

        if failed == 2 and unpron_ignore == 0:
            if (not check_atstart) or (pre_ptr - 1 >= 0 and buf[pre_ptr - 1] == ord(" ")):
                if check_atstart:
                    points += 4
                if points >= best.points:
                    best.points = points
                    best.phonemes = cr.phonemes
                    best.end_type = end_type
                    best.del_fwd = del_fwd
                    total_consumed = consumed

    total_consumed += group_length
    if total_consumed == 0:
        total_consumed = 1
    new_ix = ix_word + total_consumed
    if best.points == 0:
        best.phonemes = ""
    return best, new_ix


def _match_post(tr, rb, prog, k, buf, letter, letter_w, letter_xbytes,
                last_letter_w, distance_right, post_ptr, word_flags, dict_flags):
    failed = 0
    add_points = 0
    end_type = 0
    if rb == K.RULE_LETTERGP:
        letter_group = _letter_group_no(prog[k]); k += 1
        if tr.is_letter(letter_w, letter_group):
            lg_pts = 20
            if letter_group == 2:
                lg_pts = 19
            add_points = lg_pts - distance_right
            post_ptr += letter_xbytes
        else:
            failed = 1
    elif rb == K.RULE_LETTERGP2:
        letter_group = _letter_group_no(prog[k]); k += 1
        n_bytes = _is_letter_group(tr, buf, post_ptr - 1, letter_group, 0)
        if n_bytes >= 0:
            add_points = 20 - distance_right
            post_ptr += (n_bytes - 1)
        else:
            failed = 1
    elif rb == K.RULE_NOTVOWEL:
        if tr.is_letter(letter_w, 0) or (letter_w == ord(" ") and (word_flags & K.FLAG_SUFFIX_VOWEL)):
            failed = 1
        else:
            add_points = 20 - distance_right
            post_ptr += letter_xbytes
    elif rb == K.RULE_DIGIT:
        if is_digit(letter_w):
            add_points = 20 - distance_right
            post_ptr += letter_xbytes
        else:
            failed = 1
    elif rb == K.RULE_NONALPHA:
        if not is_alpha(letter_w):
            add_points = 21 - distance_right
            post_ptr += letter_xbytes
        else:
            failed = 1
    elif rb == K.RULE_DOUBLE:
        if letter_w == last_letter_w:
            add_points = 21 - distance_right
            post_ptr += letter_xbytes
        else:
            failed = 1
    elif rb == K.RULE_DOLLAR:
        post_ptr -= 1
        command = prog[k]; k += 1
        failed, add_points = _dollar_rule(tr, command, word_flags, dict_flags)
    elif rb == ord("-"):
        if letter == ord("-") or (letter == ord(" ") and (word_flags & K.FLAG_HYPHEN_AFTER)):
            add_points = 22 - distance_right
        else:
            failed = 1
    elif rb == K.RULE_SYLLABLE:
        syllable_count = 1
        while k < len(prog) and prog[k] == K.RULE_SYLLABLE:
            k += 1
            syllable_count += 1
        p = post_ptr + letter_xbytes
        vowel_count = 0
        vowel = 0
        lw = letter_w
        while lw != K.RULE_SPACE and lw != 0:
            if vowel == 0 and tr.is_letter(lw, K.LETTERGP_VOWEL2):
                vowel_count += 1
            vowel = tr.is_letter(lw, K.LETTERGP_VOWEL2)
            lw, nb = _utf8_in(buf, p)
            p += nb
        if syllable_count <= vowel_count:
            add_points = 18 + syllable_count - distance_right
        else:
            failed = 1
    elif rb == K.RULE_NOVOWELS:
        p = post_ptr + letter_xbytes
        lw = letter_w
        ok = True
        while lw != K.RULE_SPACE and lw != 0:
            if tr.is_letter(lw, K.LETTERGP_VOWEL2):
                failed = 1
                ok = False
                break
            lw, nb = _utf8_in(buf, p)
            p += nb
        if ok and not failed:
            add_points = 19 - distance_right
    elif rb == K.RULE_INC_SCORE:
        post_ptr -= 1
        add_points = 20
    elif rb == K.RULE_DEC_SCORE:
        post_ptr -= 1
        add_points = -20
    elif rb == K.RULE_DEL_FWD:
        pass  # del_fwd handled minimally (rare; English 'e' replacement)
    elif rb == K.RULE_ENDING:
        # 3 bytes: flags(16-23), flags(8-15), length|0x80 -> end_type
        et = (prog[k] << 16) | ((prog[k + 1] & 0x7f) << 8) | (prog[k + 2] & 0x7f)
        k += 3
        # LANG=tr: don't match a suffix if no previous syllable (LOPT_SUFFIX). en: off.
        if (tr.word_vowel_count == 0) and not (et & K.SUFX_P) and \
                (tr.config.get("param_suffix", 0) & 1):
            failed = 1
        else:
            end_type = et
    elif rb == K.RULE_NO_SUFFIX:
        if word_flags & K.FLAG_SUFFIX_REMOVED:
            failed = 1
        else:
            post_ptr -= 1
            add_points = 1
    else:
        if letter == rb:
            if (letter & 0xc0) != 0x80:
                add_points = 21 - distance_right
        else:
            failed = 1
    return failed, add_points, post_ptr, k, end_type


def _match_pre(tr, rb, prog, k, buf, letter, letter_w, letter_xbytes,
               last_letter_w, distance_left, distance_right, pre_ptr, word_flags, dict_flags):
    failed = 0
    add_points = 0
    if rb == K.RULE_LETTERGP:
        letter_group = _letter_group_no(prog[k]); k += 1
        if tr.is_letter(letter_w, letter_group):
            lg_pts = 20
            if letter_group == 2:
                lg_pts = 19
            add_points = lg_pts - distance_left
            pre_ptr -= letter_xbytes
        else:
            failed = 1
    elif rb == K.RULE_LETTERGP2:
        letter_group = _letter_group_no(prog[k]); k += 1
        n_bytes = _is_letter_group(tr, buf, pre_ptr, letter_group, 1)
        if n_bytes >= 0:
            add_points = 20 - distance_right
            pre_ptr -= (n_bytes - 1)
        else:
            failed = 1
    elif rb == K.RULE_NOTVOWEL:
        if not tr.is_letter(letter_w, 0):
            add_points = 20 - distance_left
            pre_ptr -= letter_xbytes
        else:
            failed = 1
    elif rb == K.RULE_DOUBLE:
        if letter_w == last_letter_w:
            add_points = 21 - distance_left
            pre_ptr -= letter_xbytes
        else:
            failed = 1
    elif rb == K.RULE_DIGIT:
        if is_digit(letter_w):
            add_points = 21 - distance_left
            pre_ptr -= letter_xbytes
        else:
            failed = 1
    elif rb == K.RULE_NONALPHA:
        if not is_alpha(letter_w):
            add_points = 21 - distance_right
            pre_ptr -= letter_xbytes
        else:
            failed = 1
    elif rb == K.RULE_DOLLAR:
        pre_ptr += 1
        command = prog[k]; k += 1
        if (command == K.DOLLAR_LIST) or ((command & 0xf0) == 0x20):
            failed, add_points = _dollar_rule(tr, command, word_flags, dict_flags)
    elif rb == K.RULE_SYLLABLE:
        syllable_count = 1
        while k < len(prog) and prog[k] == K.RULE_SYLLABLE:
            k += 1
            syllable_count += 1
        if syllable_count <= tr.word_vowel_count:
            add_points = 18 + syllable_count - distance_left
        else:
            failed = 1
    elif rb == K.RULE_STRESSED:
        pre_ptr += 1
        if tr.word_stressed_count > 0:
            add_points = 19
        else:
            failed = 1
    elif rb == K.RULE_IFVERB:
        pre_ptr += 1
        if tr.expect_verb:
            add_points = 1
        else:
            failed = 1
    elif rb == K.RULE_CAPITAL:
        pre_ptr += 1
        if word_flags & K.FLAG_FIRST_UPPER:
            add_points = 1
        else:
            failed = 1
    elif rb == ord("-"):
        if letter == ord("-") or (letter == ord(" ") and (word_flags & K.FLAG_HYPHEN)):
            add_points = 22 - distance_right
        else:
            failed = 1
    else:
        if letter == rb:
            if letter == K.RULE_SPACE:
                add_points = 4
            elif (letter & 0xc0) != 0x80:
                add_points = 21 - distance_left
        else:
            failed = 1
    return failed, add_points, pre_ptr, k


def _dollar_rule(tr, command, word_flags, dict_flags):
    # Port of the RULE_DOLLAR branch of MatchRule. $w_alt is gated on the word's dict
    # $alt flags. $p_alt / $list need a part-word *_list lookup (DollarRule) and are not
    # yet wired, so they fail (rare in core words).
    if command == K.DOLLAR_NOPREFIX:
        if word_flags & K.FLAG_PREFIX_REMOVED:
            return 1, 0
        return 0, 1
    if command == K.DOLLAR_UNPR:
        return 0, 0
    if (command & 0xf0) == 0x10:  # $w_alt / $w_alt1..6
        if dict_flags & (1 << (K.BITNUM_FLAG_ALT + (command & 0xf))):
            return 0, 23
        return 1, 0
    return 1, 0


def translate_rules(tr, word, mnem_index, word_flags=0, want_endings=False, dict_flags=0):
    """Port of TranslateRules (dictionary.c:2080) for a single space-free word.

    Returns (phonemes, end_type, end_phonemes). When `want_endings` and a standard
    suffix/prefix ending rule wins, translation stops, `end_phonemes` holds the affix
    pronunciation, and `end_type` encodes the affix (the caller removes it and
    retranslates the stem). Otherwise end_type=0.
    (Accent removal, spell-word fallback, and language-switch are not yet wired.)
    """
    rules = tr.rules
    wb = word.encode("utf-8")
    buf = b"\x00 " + wb + b" \x00"
    p = 2                       # index of first letter
    end = len(buf) - 2          # index of trailing space
    phonemes = ""
    tr.word_vowel_count = 0
    tr.word_stressed_count = 0
    any_alpha = 0

    while p < len(buf) and buf[p] not in (0, ord(" ")):
        wc, wc_bytes = _utf8_in(buf, p)
        if is_alpha(wc):
            any_alpha += 1
        c = buf[p]

        # digit -> look up "_<digit>" in the list (minimal; falls back to nothing)
        if is_digit(wc):
            num_ph = tr.lookup_num_digit(chr(wc)) if hasattr(tr, "lookup_num_digit") else ""
            phonemes = _append(tr, phonemes, num_ph, mnem_index)
            p += wc_bytes
            continue

        found = False
        match1 = None

        # 2-letter group (keyed by the two bytes at this position, as espeak's c12)
        two = bytes(buf[p:p + 2])
        if not found and two in rules.groups2:
            g2 = rules.groups2[two]
            m2, p2 = match_rule(tr, buf, p, 2, g2, word_flags, dict_flags)
            if m2.points > 0:
                m2.points += 35
            g1 = rules.groups1.get(c)
            if g1 is not None:
                m1, p1 = match_rule(tr, buf, p, 1, g1, word_flags, dict_flags)
            else:
                m1, p1 = MatchRecord(), p
            if m2.points >= m1.points:
                match1, p = m2, p2
            else:
                match1, p = m1, p1
            found = True

        if not found:
            g1 = rules.groups1.get(c)
            if g1 is not None:
                match1, p = match_rule(tr, buf, p, 1, g1, word_flags, dict_flags)
            else:
                match1, p = match_rule(tr, buf, p, 0, rules.default, word_flags, dict_flags)
                if match1.points == 0:
                    # unrecognised character: skip it (full fallback handling TODO)
                    p += (wc_bytes - 1)

        if match1 is None or match1.phonemes is None:
            continue
        if match1.points > 0:
            end_type = match1.end_type & ~K.SUFX_UNPRON
            if want_endings and end_type != 0:
                # a standard ending matched: stop, return the affix phonemes + type
                if (end_type & K.SUFX_P) and (word_flags & K.FLAG_NO_PREFIX):
                    pass  # ignore the prefix match
                else:
                    if (end_type & K.SUFX_P) and ((end_type & 0x7f) == 0):
                        end_type |= (p - 2)  # prefix length = chars consumed so far
                    return phonemes, end_type, match1.phonemes
            phonemes = _append(tr, phonemes, match1.phonemes, mnem_index)

    return phonemes, 0, ""


def _append(tr, phonemes, ph, mnem_index):
    if not ph:
        return phonemes
    count_vowels(tr, ph, mnem_index)
    return phonemes + ph  # AppendPhonemes uses strcat (no separator)


_ADD_E_EXCEPTIONS = ("ion",)
_ADD_E_ADDITIONS = ("c", "rs", "ir", "ur", "ath", "ns", "u", "spong", "rang", "larg")


def remove_ending(tr, word, end_type):
    """Port of RemoveEnding (dictionary.c:2901). Returns (stem, end_flags).

    Removes a standard suffix indicated by the dictionary rules and (for English)
    reverses the y->i and e-dropping that adding the suffix performed.
    """
    chars = list(word.replace(chr(REPLACED_E), "e"))
    n_remove = end_type & 0x3f
    stem = chars[: len(chars) - n_remove] if n_remove else chars[:]
    ending = "".join(chars[len(chars) - n_remove:]) if n_remove else ""
    end_flags = (end_type & 0xfff0) | K.FLAG_SUFX

    if (end_type & K.SUFX_I) and stem and stem[-1] == "i":
        stem[-1] = "y"

    if end_type & K.SUFX_E and tr.translator_name == K.L("e", "n"):
        last = ord(stem[-1]) if stem else 0
        prev = ord(stem[-2]) if len(stem) >= 2 else 0
        added = False
        if tr.is_letter(prev, K.LETTERGP_VOWEL2) and tr.is_letter(last, 1):
            tail = "".join(stem[-3:])
            if not any(tail.endswith(ex) for ex in _ADD_E_EXCEPTIONS):
                added = True
        else:
            tail = "".join(stem)
            if any(tail.endswith(a) for a in _ADD_E_ADDITIONS):
                added = True
        if added:
            stem.append("e")
            end_flags |= K.FLAG_SUFX_E_ADDED

    if (end_type & K.SUFX_V) and tr.expect_verb == 0:
        tr.expect_verb = 1

    if ending in ("s", "es"):
        end_flags |= K.FLAG_SUFX_S

    return "".join(stem), end_flags


def _is_letter_group(tr, buf, ix, group, pre):
    items = tr.rules.letter_groups.get(group) if getattr(tr, "rules", None) else None
    if not items:
        return -1
    for item in items:
        if item == "~":
            return 0
        ib = item.encode("utf-8")
        if pre:
            # match backwards: the bytes ending at ix
            length = len(ib)
            start = ix - length + 1
            if start < 0:
                continue
            if bytes(buf[start:ix + 1]) == ib:
                return length
        else:
            if bytes(buf[ix:ix + len(ib)]) == ib:
                return len(ib)
    return -1
