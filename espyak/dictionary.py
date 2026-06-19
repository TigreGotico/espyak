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
import unicodedata
from espyak import constants as K
from espyak.phoneme_tab import phVOWEL, phSTRESS, phLIQUID, phSTOP, Phoneme

# A no-tie barrier ('|' in phoneme strings): keep it as a passthrough token through
# set_word_stress so the downstream phoneme parser doesn't greedily merge the phonemes it
# separates (pt acronym 's|;' must stay s + ; = sʲ, not the single phoneme 's;' = ʂ). It is
# type phINVALID, so it is never counted as a vowel or treated as a stress mark.
_BARRIER = Phoneme("|")


def _nfc(s):
    return unicodedata.normalize("NFC", s)

REPLACED_E = ord("E")

# remove_accent[] (dictionary.c:66), indexed by codepoint-0xC0: the 7-bit base letter an
# accented char reduces to. espeak, on finding no rule for a letter, substitutes this base
# and re-translates the word (dictionary.c:2228). Covers 0xC0..0x25D.
_REMOVE_ACCENT = bytes.fromhex(
    "61616161616161636565656569696969646e6f6f6f6f6f006f7575757579747361616161616161636565656569696969646e6f6f6f6f6f006f757575757974796161616161616363636363636363646464646565656565656565656567676767676767676868686869"
    "69696969696969696969696a6a6b6b6b6c6c6c6c6c6c6c6c6c6c6e6e6e6e6e6e6e6e6e6f6f6f6f6f6f6f6f727272727272737373737373737374747474747475757575757575757575757577777979797a7a7a7a7a7a736262626200006f6363646464646465656566"
    "6667676869696b6b6c6c6d6e6e6f6f6f6f6f70707900007373747474747575757679797a7a7a7a7a7a7a000000777474746b6464646c6c6c6e6e6e616169696f6f7575757575757575757565616161616161676767676b6b6f6f6f6f7a7a6a646464676777776e6e61"
    "6161616f6f6161616165656565696969696f6f6f6f727272727575757573737474797968686e646f6f7a7a616165656f6f6f6f6f6f6f6f79796c6e746a64716163636c74737a000062757665656a6a717172727979616161626f636464656565656565"
)

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
        self.u_clause_final = config.get("u_clause_final", False)
        self.it_lengthen = config.get("it_lengthen", 0)  # LOPT_IT_LENGTHEN
        self.translator_name = config.get("translator_name", 0)
        # voice `dictrules N M ...` permanently set those numbered conditions, so `?N`-gated
        # dict entries match (sr `?2 w -> duplo` for the W letter name needs condition 2).
        for _n in config.get("dictrules", ()):
            self.dict_condition |= (1 << _n)
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
        # non-Latin scripts: letter_bits indexed by (char - offset) code values
        self.letter_bits_offset = config.get("letter_bits_offset", 0)
        for group, codes in config.get("letter_bits_codes", []):
            for code in codes:
                if 0 <= code < 256:
                    self.letter_bits[code] |= (1 << group)
        # SetLetterBitsRange(group, first, last): OR a contiguous code range (Indic)
        for group, first, last in config.get("letter_bits_ranges", []):
            for code in range(first, last + 1):
                if 0 <= code < 256:
                    self.letter_bits[code] |= (1 << group)
        # wchar vowel override (SetLetterVowel over a list of >255 codepoints, e.g. the 72
        # Vietnamese tone-marked vowels): a letter_groups[] entry takes precedence over the
        # 256-wide letter_bits in is_letter, so vowel groups can hold non-Latin-1 chars.
        vov = config.get("vowels_override")
        if vov:
            vset = frozenset(vov)
            self.letter_groups[K.LETTERGP_A] = vset
            self.letter_groups[K.LETTERGP_VOWEL2] = vset

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
        elif 0xc0 <= letter < 0xc0 + len(_REMOVE_ACCENT):
            # accented Latin letter inherits its base letter's groups (dictionary.c:788):
            # ò counts as a vowel because o does -> gd `A) p (_` fires (ròp -> …b), ga IsVowel.
            base = _REMOVE_ACCENT[letter - 0xc0]
            return 1 if (self.letter_bits[base] & (1 << group)) else 0
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
        self.cased_keys = set()  # original-case keys (espeak's letter lookup is case-sensitive)
        self.text_mode = False

    def has_exact(self, key):
        """True if `key` existed verbatim (case-sensitive). espeak's LookupLetter is
        case-sensitive: a lowercase letter must not match an uppercase `_X` name entry
        (smj `_O o:` is the name of UPPERCASE O; lowercase o spells via the rules -> oɔ)."""
        return _nfc(key) in self.cased_keys

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
        # a condition can precede the word, e.g. "?!3 _0and  @n"
        leading_cond = []
        while line and line[0] == "?":
            ctok, _, line = line.partition(" ")
            line = line.lstrip()
            neg = len(ctok) > 1 and ctok[1] == "!"
            num = "".join(ch for ch in ctok if ch.isdigit())
            if num:
                leading_cond.append(int(num) + (132 if neg else 100))
        if not line:
            return
        flag_codes.extend(leading_cond)
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
        # a standalone `$textmode` / `$phonememode` line is a SECTION directive (ro abbreviations:
        # etc -> etcetera, udmr -> udemere are replacement text, not phonemes), not a word entry.
        if word in ("$textmode", "$phonememode") and not tokens:
            self.text_mode = (word == "$textmode")
            return
        phon_tokens = []
        for tok in tokens:
            # a condition marker is "?N" or "?!N" (? + digit); a token like "?ila:h" is
            # phonemes beginning with the glottal-stop phoneme `?` (Arabic hamza), NOT a
            # condition — misreading it dropped the pronunciation of hamza-initial words.
            if tok.startswith("?") and len(tok) > 1 and (
                    tok[1].isdigit() or (tok[1] == "!" and tok[2:3].isdigit())):
                neg = tok[1] == "!"
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
        # espeak's _list value is a SINGLE phoneme string (word breaks use ||, not spaces); a second
        # whitespace-separated token is a separate field that EncodePhonemes does not consume (mt
        # `lil hinn<TAB>lil:in:` -> lil maps to `hinn`, the trailing `lil:in:` dropped, not hinnlilin).
        phonemes = phon_tokens[0] if phon_tokens else ""
        if self.text_mode:
            flag_codes.append(_MNEM_FLAGS["$text"])  # within a $textmode section -> FLAG_TEXTMODE
        entry = DictEntry(phonemes, flag_codes, multiword, rest_words)
        # NFC-normalize keys so NFD source lists (e.g. ko_list conjoining jamo) match an
        # NFC-normalized lookup; idempotent for the usual NFC/ASCII entries.
        self.words.setdefault(_nfc(word.lower()), []).append(entry)
        self.cased_keys.add(_nfc(word))

    def lookup(self, word, ctx):
        """Return (phonemes_or_None, flags1) or (None, None) if not found.

        Port of LookupDict2 selection: iterate entries last-in-file first, apply
        condition/flag checks against the context (an LookupContext). A returned
        phonemes of "" with flags1!=None means flags-only (use rules).
        """
        entries = self.words.get(word.lower()) or self.words.get(_nfc(word.lower()))
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
            if ph[i] == "|":
                toks.append(("|", _BARRIER))  # no-tie barrier: preserve through stressing
                i += 1
                continue
            if ph[i] in (" ", "\t"):
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
        if ph.type == phSTRESS and not mnem.isdigit():
            # digit-named phStress phonemes are tone marks (Vietnamese 1-7), not stress
            # markers — keep them in the phonetic stream rather than consuming them.
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
        if _ph_is_vowel(ph) and mnem != "@-":
            # @- is the "very short schwa" (linking/epenthetic, e.g. eo Cr clusters
            # septemb@-*o); it is not a syllable nucleus, so it must not be counted for
            # stress placement (else the penult shifts onto it).
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


def set_word_stress(tr, phoneme_str, mnem_index, dict_flags=0, tonic=-1, control=0,
                    suffix_vowels=0):
    """Port of SetWordStress (dictionary.c:919) for stress_rule=STRESSPOSN_2R and the
    common path. Returns the phoneme string with stress mnemonics inserted.

    `suffix_vowels` is the number of trailing vowels that belong to a removed suffix:
    espeak runs GetVowelStress on the stem only and appends the suffix unstressed, so
    those vowels are excluded from the auto-secondary loop (ro unele -> ˈunele not ˈunelˌe).
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

    max_stress_input = max_stress  # max explicit stress before the stress rule fires

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
    elif tr.stress_rule == K.STRESSPOSN_1SL:  # Malayalam: 1st syllable, unless the 1st vowel
        # is short and the 2nd is long (then the 2nd): കഠോര -> kɐʈʰˈoːɾɐ (1st a short, 2nd o: long).
        if stressed_syllable == 0:
            stressed_syllable = 1
            if vowel_length[1] == 0 and vowel_count > 2 and vowel_length[2] > 0:
                stressed_syllable = 2
            vowel_stress[stressed_syllable] = STRESS_IS_PRIMARY
            max_stress = STRESS_IS_PRIMARY
    elif tr.stress_rule == K.STRESSPOSN_1R:
        if stressed_syllable == 0:
            stressed_syllable = vowel_count - 1
            while stressed_syllable > 0:
                if vowel_stress[stressed_syllable] < STRESS_IS_DIMINISHED:
                    vowel_stress[stressed_syllable] = STRESS_IS_PRIMARY
                    break
                stressed_syllable -= 1
            max_stress = STRESS_IS_PRIMARY
    elif tr.stress_rule == K.STRESSPOSN_3R:  # antepenultimate (e.g. Macedonian)
        if stressed_syllable == 0:
            stressed_syllable = vowel_count - 3
            if stressed_syllable < 1:
                stressed_syllable = 1
            vowel_stress[stressed_syllable] = STRESS_IS_PRIMARY
            max_stress = STRESS_IS_PRIMARY
    elif tr.stress_rule == K.STRESSPOSN_EU:  # Basque: primary on 2nd syllable, secondary on last
        if stressed_syllable == 0 and vowel_count > 2:
            for ix in range(1, vowel_count):
                vowel_stress[ix] = STRESS_IS_DIMINISHED
            stressed_syllable = 2
            if max_stress <= STRESS_IS_DIMINISHED:
                vowel_stress[2] = STRESS_IS_PRIMARY
            max_stress = STRESS_IS_PRIMARY
            if vowel_count > 3:
                vowel_stress[vowel_count - 1] = STRESS_IS_SECONDARY
    elif tr.stress_rule == K.STRESSPOSN_SYLCOUNT:  # Russian: guess stress from syllable count
        # port of dictionary.c case STRESSPOSN_SYLCOUNT — for words without an explicit
        # (dictionary) stress, guess from the syllable count and the final phoneme type.
        if stressed_syllable == 0:
            guess_ru = (0, 0, 1, 1, 2, 3, 3, 4, 5, 6, 7, 7, 8, 9, 10, 11)
            guess_ru_v = (0, 0, 1, 1, 2, 2, 3, 3, 4, 5, 6, 7, 7, 8, 9, 10)  # final = vowel
            guess_ru_t = (0, 0, 1, 2, 3, 3, 3, 4, 5, 6, 7, 7, 7, 8, 9, 10)  # final = unvoiced stop
            stressed_syllable = vowel_count - 3
            if vowel_count < 16:
                final_type = phonetic[-1][1].type if phonetic else None
                if final_type == phVOWEL:
                    stressed_syllable = guess_ru_v[vowel_count]
                elif final_type == phSTOP:
                    stressed_syllable = guess_ru_t[vowel_count]
                else:
                    stressed_syllable = guess_ru[vowel_count]
            if stressed_syllable < 1:
                stressed_syllable = 1
            vowel_stress[stressed_syllable] = STRESS_IS_PRIMARY
            max_stress = STRESS_IS_PRIMARY
    elif tr.stress_rule == K.STRESSPOSN_2LLH:  # Korean: 1st if heavy, else 2nd
        # port of dictionary.c case STRESSPOSN_2LLH -> STRESSPOSN_2L: keep stress on the
        # first syllable unless it is light and the second is heavy, then move to the second.
        if stressed_syllable == 0:
            if not (syllable_weight[1] > 0 or syllable_weight[2] == 0) and vowel_count > 2:
                stressed_syllable = 2
                vowel_stress[2] = STRESS_IS_PRIMARY
                max_stress = STRESS_IS_PRIMARY
    elif tr.stress_rule == K.STRESSPOSN_1RH:  # last heaviest syllable, excl. final (hi/mr)
        if stressed_syllable == 0:
            max_weight = -1
            for ix in range(1, vowel_count - 1):
                if vowel_stress[ix] < STRESS_IS_DIMINISHED:
                    wt = syllable_weight[ix]
                    if wt >= max_weight:
                        max_weight = wt
                        stressed_syllable = ix
            if syllable_weight[vowel_count - 1] == 2 and max_weight < 2:
                stressed_syllable = vowel_count - 1
            elif max_weight <= 0:
                stressed_syllable = 1
            vowel_stress[stressed_syllable] = STRESS_IS_PRIMARY
            max_stress = STRESS_IS_PRIMARY
    elif tr.stress_rule == K.STRESSPOSN_1RU:  # last syllable, or before an explicit
        if stressed_syllable == 0:             # unstressed vowel (Turkish/Azerbaijani)
            stressed_syllable = vowel_count - 1
            for ix in range(1, vowel_count):
                if vowel_stress[ix] == STRESS_IS_UNSTRESSED:
                    stressed_syllable = ix - 1
                    break
            vowel_stress[stressed_syllable] = STRESS_IS_PRIMARY
            max_stress = STRESS_IS_PRIMARY

    # S_FINAL_VOWEL_UNSTRESSED: don't allow stress on a word-final vowel (eu/ro)
    if ((stressflags & K.S_FINAL_VOWEL_UNSTRESSED) and (control & 2) == 0
            and vowel_count > 2 and max_stress_input < STRESS_IS_SECONDARY
            and vowel_stress[vowel_count - 1] == STRESS_IS_PRIMARY):
        if phonetic and _ph_is_vowel(phonetic[-1][1]):
            vowel_stress[vowel_count - 1] = STRESS_IS_UNSTRESSED
            vowel_stress[vowel_count - 2] = STRESS_IS_PRIMARY

    # guess complete stress pattern (secondary stresses)
    stress = STRESS_IS_PRIMARY if max_stress < STRESS_IS_PRIMARY else STRESS_IS_SECONDARY
    done = False
    first_primary = 0
    # exclude a removed suffix's trailing vowels from the auto-secondary pass (espeak runs
    # this on the stem only); never go below 1 so a stem vowel is still considered.
    sec_count = max(1, vowel_count - suffix_vowels) if suffix_vowels else vowel_count
    for v in range(1, sec_count):
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
                # S_2_TO_HEAVY (et/fi): don't put secondary on a light syllable if a heavy one
                # follows (within the word, excluding the last syllable), nor on a light syllable
                # directly followed by a heavy one (följetonist: light 'o' before heavy 'nist'
                # -> no ˌo, so fˈøʎjetonist not fˈøʎjetˌonist).
                if v > 1 and (stressflags & K.S_2_TO_HEAVY) and syllable_weight[v] == 0:
                    if any(syllable_weight[i] > 0 for i in range(v, vowel_count - 1)):
                        continue
                    if syllable_weight[v + 1] > 0:
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
        # A first-syllable-stress (1L) CONTENT word with no inherent stress (every vowel
        # diminished/unstressed, e.g. ga arsa -> @rs@) takes the clause tonic on syllable 1,
        # following the language's stress direction — not the last syllable max_stress_posn
        # (last-wins ties) selects. A $u function word (nl onze) keeps the last, so exclude it.
        if (max_stress <= STRESS_IS_UNSTRESSED and vowel_count > 1
                and tr.stress_rule == K.STRESSPOSN_1L and not unstressed_word):
            max_stress_posn = 1
        if (tonic > max_stress) or (max_stress <= STRESS_IS_PRIMARY):
            vowel_stress[max_stress_posn] = tonic
        max_stress = tonic
        # el: a multi-syllable $u (function) word carrying the clause accent takes it on the
        # LAST syllable, its lexical accent dropping to secondary (είμαστε -> ˌimastˈe). Short
        # $u words (<=2 vowels) keep the accent on the accented syllable (είμαι -> ˈime).
        if (getattr(tr, "u_clause_final", False) and unstressed_word
                and tonic >= STRESS_IS_PRIMARY and vowel_count >= 4
                and max_stress_posn != vowel_count - 1):
            vowel_stress[max_stress_posn] = STRESS_IS_SECONDARY
            vowel_stress[vowel_count - 1] = tonic
            max_stress_posn = vowel_count - 1
        # haw (Hawaiian): a long (macron) vowel carrying the lexical primary on a NON-final
        # syllable drops to secondary and the clause nucleus moves to the final syllable
        # (kākou: k'a:kou -> kˌaːkoˈu, the long ā demoted, primary on the final u).
        if (tr.config.get("macron_clause_final") and tonic >= STRESS_IS_PRIMARY
                and max_stress_posn != vowel_count - 1
                and 1 <= max_stress_posn < len(vowel_length)
                and vowel_length[max_stress_posn] > 0):
            # only a long MONOPHTHONG (macron, kākou a:) demotes; a DIPHTHONG carrying the
            # primary (maila ai, also vowel_length>0) keeps its accent (mˈaila, not mˌailˈa).
            _vi = 0
            _msp_ph = None
            for _m, _p in phonetic:
                if _ph_is_vowel(_p) and _m != "@-":
                    _vi += 1
                    if _vi == max_stress_posn:
                        _msp_ph = _p
                        break
            if _msp_ph is not None and _msp_ph.starttype == _msp_ph.endtype:
                vowel_stress[max_stress_posn] = STRESS_IS_SECONDARY
                vowel_stress[vowel_count - 1] = tonic
                max_stress_posn = vowel_count - 1

    # produce output: walk phonetic, insert stress mnemonic before each vowel
    opt_length = getattr(tr, "it_lengthen", 0)  # LOPT_IT_LENGTHEN
    out = []
    v = 1
    prev_v = 0
    prev_v_stress = 0
    for mnem, ph in phonetic:
        if (opt_length & 1) and mnem == ":":
            # remove a lengthen indicator from a non-stressed (or non-max-stress) syllable
            if opt_length & 0x10:
                shorten = prev_v != max_stress_posn
            else:
                shorten = prev_v_stress < STRESS_IS_PRIMARY
            if shorten:
                continue
        if _ph_is_vowel(ph) and mnem != "@-":
            # @- is excluded from the vowel count in get_vowel_stress, so it must also be
            # skipped here or `v` desyncs and the stress mark lands on it (before an onset
            # liquid: eo pra -> pˈra instead of prˈa).
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
            # Emit the diminished "%%" marker too: espeak carries the DIMINISHED level into
            # the phoneme list so ChangeIfDiminished programs fire (uk unstressed e -> ɪ via
            # ChangeIfDiminished(I2) on mid-word vowels). The renderer still shows no mark for
            # it (GetTranslatedPhonemeString only marks stress > 1), so visible output only
            # changes for phonemes that actually carry a ChangeIfDiminished program.
            if v_stress > STRESS_IS_UNSTRESSED or v_stress == STRESS_IS_DIMINISHED:
                out.append(_STRESS_MNEM.get(v_stress, ""))
            prev_v = v
            prev_v_stress = v_stress
            v += 1
        out.append(mnem)
    return "".join(out)


def _compute_weights(phonetic, vowel_length, syllable_weight):
    # port of the heavy/light syllable loop (dictionary.c:1002-1026).
    # espeak's consonant_types[16] = {0,0,0,1,1,1,1,1,1,1,0,...} indexed by phoneme type
    # (phVOWEL=2 -> 0): a *consonant* is phLIQUID..phVIRTUAL. phVOWEL is NOT a consonant, so a
    # following vowel does NOT close the syllable (hiatus). Including phVOWEL here wrongly made
    # V.V syllables heavy (ko su-+u- -> 2LLH stressed the wrong syllable; 키스의 -> khˈisɯˌɯj).
    consonant_types = {phLIQUID, K.phSTOP, K.phVSTOP,
                       K.phFRICATIVE, K.phVFRICATIVE, K.phNASAL, K.phVIRTUAL}
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
    elif rb == K.RULE_SPELLING:
        # 'W': zero-width assertion — matches only while spelling the word letter-by-letter
        # (pt 'm (_W -> Em;' palatalises a spelled consonant before the next letter). Undo
        # the speculative letter read since this consumes no input.
        post_ptr -= (1 + letter_xbytes)
        if getattr(tr, "_spelling", False):
            add_points = 20 - distance_right
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
    elif rb == K.RULE_SKIPCHARS:
        # '(Jxy': skip word characters until the next rule element (xy) matches it
        # (dictionary.c:1788). The target prog[k] is NOT consumed here — the next iteration
        # matches it. Used by lv `L25) e (CJL18_` (skip 'tflīģeļ' to the L18 suffix 'u').
        p = post_ptr - 1            # first byte of the current letter
        lw = letter_w
        target = prog[k]
        is_lg = (target == K.RULE_LETTERGP2)
        tgroup = _letter_group_no(prog[k + 1]) if is_lg else None
        while lw != K.RULE_SPACE and lw != 0:
            if is_lg:
                if _is_letter_group(tr, buf, p, tgroup, 0) >= 0:
                    break
            elif lw == target:
                break
            _, nb = _utf8_in(buf, p)
            p += nb
            lw, _ = _utf8_in(buf, p)
        if lw == K.RULE_SPACE or lw == 0:
            failed = 1
        else:
            post_ptr = p            # next iteration reads the match and processes prog[k]
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
    elif rb == K.RULE_NOVOWELS:
        # X) — no vowel between here and the start of the word (scanning backward)
        p = pre_ptr - letter_xbytes
        lw = letter_w
        ok = True
        while lw != K.RULE_SPACE and lw != 0:
            if tr.is_letter(lw, K.LETTERGP_VOWEL2):
                failed = 1
                ok = False
                break
            lw, nb = _utf8_back(buf, p - 1)
            p -= nb
        if ok and not failed:
            add_points = 3
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


def _apply_replacements(reps, word):
    """Apply the `.replace` table (port of SubstituteChar, translate.c:784) before rule
    matching: longest source-string first, matched case-insensitively (espeak lowercases
    the char to look it up), output lowercase. Used for Cyrillic->Latin transliteration in
    Serbo-Croatian (hr/bs/sr) and digraph normalisation elsewhere."""
    if not reps:
        return word
    rep_sorted = sorted(reps, key=lambda fr: -len(fr[0]))
    out = []
    i = 0
    n = len(word)
    while i < n:
        for frm, to in rep_sorted:
            seg = word[i:i + len(frm)]
            if seg and seg.lower() == frm.lower():
                out.append(to)
                i += len(frm)
                break
        else:
            out.append(word[i])
            i += 1
    return "".join(out)


def translate_rules(tr, word, mnem_index, word_flags=0, want_endings=False, dict_flags=0):
    """Port of TranslateRules (dictionary.c:2080) for a single space-free word.

    Returns (phonemes, end_type, end_phonemes). When `want_endings` and a standard
    suffix/prefix ending rule wins, translation stops, `end_phonemes` holds the affix
    pronunciation, and `end_type` encodes the affix (the caller removes it and
    retranslates the stem). Otherwise end_type=0.
    (Accent removal, spell-word fallback, and language-switch are not yet wired.)
    """
    rules = tr.rules
    word = _apply_replacements(getattr(rules, "replacements", None), word)
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
        p_start = p  # char start; match_rule below reassigns p past the (failed) match

        # single >=3-byte char (Korean jamo, etc.): dispatch by codepoint via groups3
        if wc_bytes >= 3 and wc in rules.groups3:
            match1, p = match_rule(tr, buf, p, wc_bytes, rules.groups3[wc],
                                   word_flags, dict_flags)
            found = True

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
                    # no rule: espeak strips the accent and re-translates the word
                    # (dictionary.c:2228). Only when the char isn't the whole word (a lone
                    # accented letter is spelled out instead). Fire for ASCII-letter bases.
                    base = (_REMOVE_ACCENT[wc - 0xC0]
                            if 0xC0 <= wc < 0xC0 + len(_REMOVE_ACCENT) else 0)
                    if 0x61 <= base <= 0x7A and len(wb) > wc_bytes:
                        # slice from the CHAR START (p_start), not the advanced p: the failed
                        # default match leaves p mid-character, which split the multi-byte
                        # accented char and corrupted the re-translated word (sjn fëanor).
                        new_word = (buf[2:p_start] + bytes([base])
                                    + buf[p_start + wc_bytes:end]).decode("utf-8", "replace")
                        return translate_rules(tr, new_word, mnem_index, word_flags,
                                               want_endings, dict_flags)
                    # unrecognised ASCII letter in a multi-letter word: espeak sets
                    # FLAG_SPELLWORD and re-translates as individual letters (dictionary.c:2274).
                    # mto foreign names (no rule for 'd' in amsterdam). Scoped to ASCII so non-ASCII
                    # special letters (es ª ordinal) take their own path instead.
                    if any_alpha > 1 and is_alpha(wc) and wc < 0x80:
                        tr._spell_word = True
                        return phonemes, 0, ""
                    # unrecognised character: skip it
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
    # espeak stores .Lnn group members longest-first and takes the longest match (compiledict.c):
    # .L01 has both 'u' and the diphthong 'ui', so 'ui' must win (sjn Arvedui: e (CL01X matches
    # the 'ui' so X reaches the word end -> the =E retraction fires). Return the LONGEST match.
    best = -1
    has_null = False
    for item in items:
        if item == "~":
            has_null = True
            continue
        ib = item.encode("utf-8")
        length = len(ib)
        if pre:
            # match backwards: the bytes ending at ix
            start = ix - length + 1
            if start >= 0 and bytes(buf[start:ix + 1]) == ib and length > best:
                best = length
        elif bytes(buf[ix:ix + length]) == ib and length > best:
            best = length
    if best >= 0:
        return best
    return 0 if has_null else -1
