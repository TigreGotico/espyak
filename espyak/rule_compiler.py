"""Compile espeak-ng ``<lang>_rules`` source into in-memory rule groups.

Faithful port of the relevant parts of ``compiledict.c``:
  - copy_rule_string  (special-character encoding for pre/post sections)
  - compile_rule      (assembly: match + condition + pre[reversed] + post)
  - output_rule_group (group name stripping, phoneme-string sort)
  - compile_lettergroup / .replace parsing

Difference from upstream: phoneme strings are kept as **mnemonic text** (the renderer
consumes mnemonics), not encoded to phoneme-table byte codes. The instruction stream
that ``MatchRule`` walks is reproduced exactly (same command bytes, same pre-reversal),
so scoring and longest-match behavior are identical. The RULE_PH_COMMON storage
optimization is skipped (every rule carries its own phoneme string — identical result).

Reference: espeak-ng 1.52.0.
"""
from espyak import constants as K

# $-command mnemonics (compiledict.c mnem_rules) -> value byte
_MNEM_RULES = [
    ("unpr", K.DOLLAR_UNPR),
    ("noprefix", K.DOLLAR_NOPREFIX),
    ("list", K.DOLLAR_LIST),
    ("w_alt1", 0x11), ("w_alt2", 0x12), ("w_alt3", 0x13),
    ("w_alt4", 0x14), ("w_alt5", 0x15), ("w_alt6", 0x16), ("w_alt", 0x11),
    ("p_alt1", 0x21), ("p_alt2", 0x22), ("p_alt3", 0x23),
    ("p_alt4", 0x24), ("p_alt5", 0x25), ("p_alt6", 0x26), ("p_alt", 0x21),
]

# letter-group letters A B C (D E) F G H Y  ->  LETTERGP_* (compiledict.c lettergp_letters)
_LETTERGP_LETTERS = [
    K.LETTERGP_A, K.LETTERGP_B, K.LETTERGP_C, 0, 0,
    K.LETTERGP_F, K.LETTERGP_G, K.LETTERGP_H, K.LETTERGP_Y,
]


def _is_hex_digit(c):
    if "0" <= c <= "9":
        return ord(c) - ord("0")
    if "a" <= c <= "f":
        return ord(c) - ord("a") + 10
    if "A" <= c <= "F":
        return ord(c) - ord("A") + 10
    return -1


def _isspace2(c):
    return c in (" ", "\t", "\n", "\r", "\0", "")


class CompiledRule:
    __slots__ = ("prog", "phonemes", "match_str", "sortkey")

    def __init__(self, prog, phonemes, match_str):
        self.prog = prog            # bytes: instruction stream MatchRule walks
        self.phonemes = phonemes    # str: mnemonic phoneme string
        self.match_str = match_str  # str: the match letters incl. group name (debug/sort)
        self.sortkey = (phonemes, match_str)

    def __repr__(self):
        return "CompiledRule(match=%r, ph=%r)" % (self.match_str, self.phonemes)


def _copy_rule_string(string, state):
    """Port of copy_rule_string. Returns (out_bytes, next_state).

    state: 0=condition, 1=pre, 2=match, 3=post, 4=phonemes
    Only states 1 and 3 apply the special-character substitution.
    """
    next_state = {0: 2, 1: 2, 2: 4, 3: 4, 4: 4}[state]
    out = bytearray()
    sxflags = 0x808000
    p = list(string)
    i = 0
    hexdigit_input = False
    n = len(p)
    while True:
        literal = False
        if i >= n:
            out.append(0)
            break
        c = p[i]; i += 1
        # 0x.. hex byte prefix
        if c == "0" and i < n and p[i] == "x" and i + 2 < n and _is_hex_digit(p[i+1]) >= 0 and _is_hex_digit(p[i+2]) >= 0:
            hexdigit_input = True
            c = p[i+1]
            i += 2
        if c == "\\" and i < n:
            c = p[i]; i += 1
            if "0" <= c <= "3" and i + 1 < n and "0" <= p[i] <= "7" and "0" <= p[i+1] <= "7":
                c = chr((ord(c) - 48) * 64 + (ord(p[i]) - 48) * 8 + (ord(p[i+1]) - 48))
                i += 2
            literal = True
        if hexdigit_input:
            c2 = _is_hex_digit(c)
            c3 = _is_hex_digit(p[i]) if i < n else -1
            if c2 >= 0 and c3 >= 0:
                c = chr(c2 * 16 + c3)
                literal = True
                i += 1
            else:
                hexdigit_input = False

        cval = ord(c) if len(c) == 1 else c  # c is always 1 char here
        handled_special = False
        if state in (1, 3) and not literal:
            handled, extra, cval2, consumed, sxflags = _special_char(c, p, i, state, sxflags)
            if handled:
                out.extend(extra)
                cval = cval2
                i += consumed
                handled_special = True
        v = cval if isinstance(cval, int) else ord(cval)
        # A literal non-ASCII letter (>= 0x80, e.g. á/ä Latin-1 or Greek/Cyrillic) must be
        # emitted as its UTF-8 bytes to match the UTF-8 word — but NOT the special-encoded
        # bytes from _special_char (rule commands, ending length value|0x80) or explicit
        # \-octal/0x hex literals, which are real single bytes.
        if v >= 0x80 and not handled_special and not literal:
            out.extend(chr(v).encode("utf-8"))
        else:
            out.append(v & 0xff)
        if v == 0:
            break
    return bytes(out), next_state


def _is_command_byte(v):
    return v <= K.RULE_LAST_RULE


def _special_char(c, p, i, state, sxflags):
    """Handle one special character in a pre/post section.

    Returns (handled, extra_bytes_before, new_c_value_byte, chars_consumed_after, sxflags).
    Mirrors the switch in copy_rule_string (states 1=pre, 3=post).
    """
    n = len(p)
    extra = []
    consumed = 0

    if c == "_":
        return True, extra, K.RULE_SPACE, consumed, sxflags
    if c in "YABCHFG":
        cc = "I" if c == "Y" else c
        grp = _LETTERGP_LETTERS[ord(cc) - ord("A")] + ord("A")
        if state == 1:  # pre: group byte first, then RULE_LETTERGP
            extra.append(grp)
            return True, extra, K.RULE_LETTERGP, consumed, sxflags
        else:           # post: RULE_LETTERGP first, then group byte
            extra.append(K.RULE_LETTERGP)
            return True, extra, grp, consumed, sxflags
    simple = {
        "D": K.RULE_DIGIT, "K": K.RULE_NOTVOWEL, "N": K.RULE_NO_SUFFIX,
        "V": K.RULE_IFVERB, "Z": K.RULE_NONALPHA, "+": K.RULE_INC_SCORE,
        "<": K.RULE_DEC_SCORE, "@": K.RULE_SYLLABLE, "&": K.RULE_STRESSED,
        "%": K.RULE_DOUBLE, "#": K.RULE_DEL_FWD, "!": K.RULE_CAPITAL,
        "W": K.RULE_SPELLING, "X": K.RULE_NOVOWELS, "J": K.RULE_SKIPCHARS,
    }
    if c in simple:
        return True, extra, simple[c], consumed, sxflags
    if c == "T":
        extra.append(K.RULE_DOLLAR)
        return True, extra, 0x11, consumed, sxflags
    if c == "L":
        # expect two digits
        d1 = ord(p[i]) - ord("0") if i < n else -1
        d2 = ord(p[i+1]) - ord("0") if i + 1 < n else -1
        consumed = 2
        grp = d1 * 10 + d2 + ord("A")
        if state == 1:
            extra.append(grp)
            return True, extra, K.RULE_LETTERGP2, consumed, sxflags
        else:
            extra.append(K.RULE_LETTERGP2)
            return True, extra, grp, consumed, sxflags
    if c == "$":
        rest = "".join(p[i:])
        value = 0
        clen = 0
        for mnem, val in _MNEM_RULES:
            if rest.startswith(mnem):
                value = val
                clen = len(mnem)
                break
        if state == 1:
            extra.append(value)
            return True, extra, K.RULE_DOLLAR, clen, sxflags
        else:
            extra.append(K.RULE_DOLLAR)
            return True, extra, value, clen, sxflags
    if c in ("P", "S"):
        if c == "P":
            sxflags |= K.SUFX_P
        extra.append(K.RULE_ENDING)
        value = 0
        j = i
        while j < n and not _isspace2(p[j]):
            ch = p[j]; j += 1
            if ch == "e":
                sxflags |= K.SUFX_E
            elif ch == "i":
                sxflags |= K.SUFX_I
            elif ch == "p":
                sxflags |= K.SUFX_P
            elif ch == "v":
                sxflags |= K.SUFX_V
            elif ch == "d":
                sxflags |= K.SUFX_D
            elif ch == "f":
                sxflags |= K.SUFX_F
            elif ch == "q":
                sxflags |= K.SUFX_Q
            elif ch == "t":
                sxflags |= K.SUFX_T
            elif ch == "b":
                sxflags |= K.SUFX_B
            elif ch == "a":
                sxflags |= K.SUFX_A
            elif ch == "m":
                sxflags |= K.SUFX_M
            elif ch.isdigit():
                value = value * 10 + (ord(ch) - ord("0"))
        consumed = j - i
        extra.append((sxflags >> 16) & 0xff)
        extra.append((sxflags >> 8) & 0xff)
        return True, extra, (value | 0x80), consumed, sxflags
    return False, extra, ord(c), consumed, sxflags


class _Sections:
    def __init__(self):
        self.cond = ""              # str
        self.pre = bytearray()      # encoded bytes (no trailing NUL kept)
        self.match = bytearray()
        self.post = bytearray()
        self.phonemes = ""          # mnemonic str


def _flush(sections, text, state):
    """Port of one copy_rule_string call. Returns the (possibly advanced) state.

    An empty `text` is a no-op and does NOT advance the state (matches the C
    `if (string[0]==0) return;`).
    """
    if text == "":
        return state
    if state == 4:
        sections.phonemes = _append_ph(sections.phonemes, text)
        return 4
    if state == 0:
        sections.cond += text
        return 2
    b, next_state = _copy_rule_string(text, state)
    body = b[:-1] if b.endswith(b"\0") else b  # drop terminator
    if state == 1:
        sections.pre += body
    elif state == 2:
        sections.match += body
    elif state == 3:
        sections.post += body
    return next_state


def compile_rule(line, group_name, group_raw=False):
    """Port of compile_rule. Returns a CompiledRule or None.

    The phoneme string is kept as mnemonic text.
    """
    sec = _Sections()
    state = 2
    p = []
    chars = list(line)
    n = len(chars)
    i = 0
    finish = False
    while not finish:
        c = chars[i] if i < n else "\0"
        if c == ")":            # end of pre section
            state = 1
            state = _flush(sec, "".join(p), state)
            p = []
        elif c == "(":          # start of post section
            state = 2
            state = _flush(sec, "".join(p), state)
            state = 3
            p = []
        elif c in ("\n", "\r", "\0"):
            _flush(sec, "".join(p), state)
            finish = True
        elif c in ("\t", " "):
            state = _flush(sec, "".join(p), state)
            p = []
        elif c == "?":
            if state == 2:
                state = 0
            else:
                p.append(c)
        else:
            p.append(c)
        i += 1

    match_s = sec.match.decode("utf-8", "replace")
    if match_s == "$group":
        match_s = group_name
        sec.match = bytearray(match_s.encode("utf-8"))
    if not sec.match:
        return None

    # assemble in-group instruction stream: match(minus group name) + cond + pre(rev) + post
    out = bytearray()
    if group_name in ("", "9"):
        len_name = 0
    else:
        len_name = len(group_name.encode("latin-1" if group_raw else "utf-8"))
    out += sec.match[len_name:]

    if sec.cond:
        if sec.cond[0] == "!":
            ix = int(sec.cond[1:] or 0) + 32
        else:
            ix = int(sec.cond or 0)
        if 0 < ix < 255:
            out.append(K.RULE_CONDITION)
            out.append(ix)

    if sec.pre:
        start = 0
        if sec.pre[0] == K.RULE_SPACE:
            out.append(K.RULE_PRE_ATSTART)
            start = 1
        else:
            out.append(K.RULE_PRE)
        for b in reversed(sec.pre[start:]):  # PRE stored in reverse byte order
            out.append(b)

    if sec.post:
        out.append(K.RULE_POST)
        out += sec.post

    return CompiledRule(bytes(out), sec.phonemes.strip(), match_s)


def _append_ph(existing, s):
    if not s:
        return existing
    return (existing + " " + s) if existing else s


class RuleSet:
    """Compiled pronunciation rules for one language (ported compile_dictrules)."""

    def __init__(self):
        self.groups1 = {}     # int(byte) -> list[CompiledRule]
        self.groups2 = {}     # bytes(2)  -> list[CompiledRule]
        self.groups3 = {}     # int(codepoint) -> list[CompiledRule]  (non-latin)
        self.default = []     # list[CompiledRule]   (bare .group)
        self.letter_groups = {}   # int(nn) -> list[str] items
        self.replacements = []    # list[(from_str, to_str)]
        self.letter_bits_offset = 0

    # -- compile a <lang>_rules file --------------------------------------------
    @classmethod
    def compile_file(cls, path, letter_bits_offset=0):
        rs = cls()
        rs.letter_bits_offset = letter_bits_offset
        group_name = ""
        group_raw = False
        group_rules = []
        mode = 0  # 0=none, 1=group, 2=replace

        def finish_group():
            if group_rules:
                rs._store_group(group_name, group_raw, group_rules)
            group_rules.clear()

        with open(path, encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                # strip // comments
                ix = raw.find("//")
                if ix >= 0:
                    raw = raw[:ix]
                line = raw.rstrip("\n")
                if line.startswith("."):
                    finish_group()
                    mode = 0
                    if line.startswith(".L") and len(line) > 2 and line[2].isdigit():
                        rs._parse_lettergroup(line[2:])
                    elif line.startswith(".replace"):
                        mode = 2
                    elif line.startswith(".group"):
                        mode = 1
                        group_name, group_raw = rs._parse_group_name(line[6:])
                    continue
                if mode == 1:
                    cr = compile_rule(line, group_name, group_raw)
                    if cr is not None:
                        group_rules.append(cr)
                elif mode == 2:
                    rs._parse_replace(line)
        finish_group()
        rs._sort_groups()
        return rs

    def _parse_group_name(self, rest):
        """Returns (name, raw). raw=True for 0x..-code names whose chars are raw byte
        values (latin-1); raw=False for normal UTF-8 group letters (e.g. ä, α)."""
        rest = rest.strip()
        name = ""
        for ch in rest:
            if ch <= " ":
                break
            name += ch
        if name.lower().startswith("0x"):
            code = int(name, 16)
            if code > 0x100:
                return bytes([(code >> 8) & 0xff, code & 0xff]).decode("latin-1"), True
            return chr(code), True
        return name[:2], False  # keep up to 2 characters (espeak truncates to 2 bytes)

    def _store_group(self, name, raw, rules):
        nb = name.encode("latin-1") if raw else name.encode("utf-8")
        rules = list(rules)
        if name == "":
            self.default.extend(rules)
        elif len(nb) == 1:
            self.groups1.setdefault(nb[0], []).extend(rules)
        elif len(nb) == 2:
            self.groups2.setdefault(bytes(nb), []).extend(rules)
        else:
            self.groups1.setdefault(nb[0], []).extend(rules)

    def _parse_lettergroup(self, rest):
        # ".L<nn>  item item item"  ('_' means word break -> space)
        nn = int(rest[0:2])
        items = []
        for tok in rest[2:].split():
            items.append(tok.replace("_", " "))
        self.letter_groups[nn] = items

    def _parse_replace(self, line):
        toks = line.split()
        if len(toks) >= 2:
            self.replacements.append((toks[0], toks[1]))

    def _sort_groups(self):
        # output_rule_group sorts each group's rules by (phoneme string, match data).
        # We approximate espeak's encoded-byte order with the mnemonic phoneme string.
        for d in (self.groups1, self.groups2, self.groups3):
            for k in d:
                d[k].sort(key=lambda r: r.sortkey)
        self.default.sort(key=lambda r: r.sortkey)


def _is_latin1_name(name):
    # group names decoded from 0x.. codes are stored as latin-1 byte chars
    return any(ord(ch) < 0x100 and ord(ch) >= 0x80 for ch in name)

