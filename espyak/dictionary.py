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
from espyak.phoneme_tab import phVOWEL, phSTRESS

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
    """Minimal translator state for the rules engine (grows toward tr_languages.c)."""

    def __init__(self, phsource=None):
        self.letter_bits = [0] * 256
        self.letter_groups = [None] * 8     # wchar overrides per group (None = use bits)
        self.letter_bits_offset = 0
        self.dict_condition = 0
        self.expect_verb = 0
        self.word_vowel_count = 0
        self.word_stressed_count = 0
        self.phsource = phsource
        self._setup_default_letters()

    def _setup_default_letters(self):
        for group, letters in _DEFAULT_LETTER_BITS.items():
            bits = 1 << group
            for ch in letters:
                self.letter_bits[ord(ch)] |= bits

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
    """Greedy mnemonic lookup over a phoneme table (for vowel counting)."""

    def __init__(self, phoneme_table):
        self.table = phoneme_table.phonemes
        self.maxlen = max((len(m) for m in self.table), default=1)


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
                    failed, add_points, post_ptr, k = _match_post(
                        tr, rb, prog, k, buf, letter, letter_w, letter_xbytes,
                        last_letter_w, distance_right, post_ptr, word_flags)
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
                        last_letter_w, distance_left, distance_right, pre_ptr, word_flags)

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
                last_letter_w, distance_right, post_ptr, word_flags):
    failed = 0
    add_points = 0
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
        failed, add_points = _dollar_rule(tr, command, word_flags)
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
        # 3 bytes: flags hi, flags mid, length|0x80 — endings handled in TranslateRules
        failed = 1  # not yet wired through retranslation; skip ending rules for now
        k += 3
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
    return failed, add_points, post_ptr, k


def _match_pre(tr, rb, prog, k, buf, letter, letter_w, letter_xbytes,
               last_letter_w, distance_left, distance_right, pre_ptr, word_flags):
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
            failed, add_points = _dollar_rule(tr, command, word_flags)
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


def _dollar_rule(tr, command, word_flags):
    # $list / $p_alt / $w_alt — needs the *_list lookup (wired in api via LookupDict).
    # Until the list lookup is connected here, fail these rules (rare in core words).
    if command == K.DOLLAR_NOPREFIX:
        if word_flags & K.FLAG_PREFIX_REMOVED:
            return 1, 0
        return 0, 1
    if command == K.DOLLAR_UNPR:
        return 0, 0
    return 1, 0


def translate_rules(tr, word, mnem_index, word_flags=0):
    """Port of TranslateRules (dictionary.c:2080) for a single space-free word.

    Returns the accumulated mnemonic phoneme string. (Endings/retranslation, accent
    removal, spell-word fallback, and language-switch are not yet wired.)
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

        # 2-letter group
        if not found and (c, buf[p + 1]) in rules.groups2:
            g2 = rules.groups2[(c, buf[p + 1])]
            m2, p2 = match_rule(tr, buf, p, 2, g2, word_flags, 0)
            if m2.points > 0:
                m2.points += 35
            g1 = rules.groups1.get(c)
            if g1 is not None:
                m1, p1 = match_rule(tr, buf, p, 1, g1, word_flags, 0)
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
                match1, p = match_rule(tr, buf, p, 1, g1, word_flags, 0)
            else:
                match1, p = match_rule(tr, buf, p, 0, rules.default, word_flags, 0)
                if match1.points == 0:
                    # unrecognised character: skip it (full fallback handling TODO)
                    p += (wc_bytes - 1)

        if match1 is None or match1.phonemes is None:
            continue
        if match1.points > 0:
            phonemes = _append(tr, phonemes, match1.phonemes, mnem_index)

    return phonemes


def _append(tr, phonemes, ph, mnem_index):
    if not ph:
        return phonemes
    count_vowels(tr, ph, mnem_index)
    return phonemes + ph  # AppendPhonemes uses strcat (no separator)


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
