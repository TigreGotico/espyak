"""Cardinal-number translation (port of the common path of numbers.c).

Reads the language's `_list` number fragments (`_0`.._19 units/teens, `_Nx` tens,
`_0c` hundred, `_0m1`.._0m10 magnitudes, `_0and` the connective "and") and assembles
them with the standard grouping. This covers the NUM_HUNDRED_AND default (English et
al.); the many per-language NUM_* variants (decimal-comma, ordinals, swap-tens,
myriads, …) are not yet modelled — see numbers.c.

Word breaks between components use `||` so the renderer emits a space, matching how the
`_Nx` tens fragments already carry a trailing `||`.
"""
from espyak import constants as K
from espyak.dictionary import LookupContext


def _num_ctx(tr_dict):
    """A LookupContext carrying the voice's dict_condition, so `?N`-gated number fragments
    (pt `?1_14` "catorze", `?1_4X` "quarenta") are selected. The condition bits are stamped
    onto the DictList by the owning Translator (Translator.dict setter)."""
    return LookupContext(dict_condition=getattr(tr_dict, "dict_condition", 0))


def _frag(tr_dict, key, ctx):
    """Look up a `_<key>` number fragment; '' if absent."""
    ph, _flags = tr_dict.lookup("_" + key.lower(), ctx)
    return ph or ""


def _digit(tr_dict, value, ctx, final):
    """A single digit; when not final (followed by hundreds/thousands) prefer the `_Na`
    variant if the language has one (German "ein" before a magnitude vs "eins")."""
    if not final:
        alt = _frag(tr_dict, "%da" % value, ctx)
        if alt:
            return alt
    return _frag(tr_dict, str(value), ctx)


# espeak phoneme-mnemonic vowel letters (as they appear in the *_list fragments). Used by
# NUM_SINGLE_VOWEL to decide whether a fragment starts/ends on a vowel. espeak inspects the
# compiled phoneme table (phVOWEL); the *_list mnemonics only ever end a tens word (or begin a
# unit word) on one of these single-letter vowels, so a letter test is exact here.
_VOWEL_LETTERS = set("aeiouyAEIOUYQ@3&")
_STRESS_MARKS = "',%=_"


def _first_vowel_start(ph):
    """True if the fragment's first real phoneme (skipping leading stress marks) is a vowel."""
    core = ph.lstrip(_STRESS_MARKS)
    return bool(core) and core[0] in _VOWEL_LETTERS


def _tens_units(tr_dict, value, ctx, flags=0, final=True, femin=False):
    """1..99 -> phonemes. Honours NUM_SWAP_TENS (units before tens, e.g. German
    "ein-und-zwanzig"), NUM_AND_UNITS ("and" between tens and units), NUM_VIGESIMAL
    (French 73 = "soixante-treize" = 60+13) and NUM_SINGLE_VOWEL (Italian settanta+uno ->
    settantuno).

    `femin` is LookupNum2's control bit 3 (numbers.c:1051 "use feminine form of '2' (for
    thousands)"): the COUNT of a magnitude whose thousandplex the language marks in numbers2
    takes a variant (feminine) numeral — ru 1000 "однa тысяча" (`_1f`), 2000 "две тысячи"
    (`_2f`), not "один"/"два"."""
    if femin:
        # numbers.c:1053 — try the whole 2-digit value (`_21fx`, then `_21f`) before decomposing.
        var = _frag(tr_dict, "%dfx" % value, ctx) or _frag(tr_dict, "%df" % value, ctx)
        if var:
            return _single_stress(var) if (flags & K.NUM_SINGLE_STRESS) else var
    if value < 10:
        return _digit(tr_dict, value, ctx, final)
    if value < 20:
        # A lexicalised teen ("eleven", "veinte"…) wins; where the language has none the teen is
        # built from the tens fragment plus the unit (Welsh "deg"+"un", numbers.c LookupNum2
        # falling through _%d to the _%dX + unit path).
        lex = _digit(tr_dict, value, ctx, final)
        if lex:
            return lex
    tens, units = divmod(value, 10)
    # espeak's LookupNum2 first tries a lexicalised whole-value form "_%d" for the entire 2-digit
    # number (numbers.c:1102) before decomposing — French "_21" vingt-et-un / "_71" soixante-onze,
    # Italian "_28" ventotto, and every exact ten "_20"/"_30". Only if that misses does it build
    # the number from the tens fragment + unit.
    whole = _frag(tr_dict, str(value), ctx)
    if whole:
        return _single_stress(whole) if (flags & K.NUM_SINGLE_STRESS) else whole
    ph_tens = _frag(tr_dict, "%dx" % tens, ctx)
    unit_val = units
    if not ph_tens and (flags & K.NUM_VIGESIMAL):
        # tens fragment not found: speak vigesimally (numbers.c:1133) — 73 = 60+13, 70 = 60+10,
        # 95 = 80+15. The tens digit is rounded down to the nearest even ten and the remainder
        # (0..19, possibly a teen) becomes the unit.
        unit_val = value % 20
        ph_tens = _frag(tr_dict, "%dx" % (tens & 0xFE), ctx)
    if unit_val == 0:
        # exact ten (whole form absent): the combining tens form (en "twenty", fr vigesimal 60).
        return ph_tens
    if unit_val >= 10:
        # a teen remainder from the vigesimal split (soixante-"treize")
        ph_units = _frag(tr_dict, str(unit_val), ctx)
    else:
        # numbers.c:1150: with control bit 3 the UNIT digit also takes its variant form first.
        ph_units = ((_frag(tr_dict, "%df" % unit_val, ctx) if femin else "")
                    or _digit(tr_dict, unit_val, ctx, final))
    if flags & K.NUM_SWAP_TENS:
        # units "and" tens (German "ein-und-zwanzig", Faroese "seks-og-tríati"). espeak
        # concatenates units+_0and+tens directly (numbers.c:1198); any word break comes from
        # the `_0and` fragment itself (de `||_|Unt` breaks, fo `u-o` joins as one word). The unit
        # takes its pre-magnitude form (German "ein" not "eins": _digit final=False).
        ph_and = _frag(tr_dict, "0and", ctx)
        out = ((_frag(tr_dict, "%df" % units, ctx) if femin else "")
               or _digit(tr_dict, units, ctx, False)) + ph_and + ph_tens
    else:
        ph_and = _frag(tr_dict, "0and", ctx) if (flags & K.NUM_AND_UNITS) else ""
        if (flags & K.NUM_SINGLE_VOWEL) and ph_tens and _first_vowel_start(ph_units) \
                and ph_tens[-1] in _VOWEL_LETTERS:
            # Italian: drop the final vowel of the tens fragment before a vowel-initial unit
            # (settanta+uno -> settant'uno, numbers.c:1203).
            ph_tens = ph_tens[:-1]
        out = ph_tens + ph_and + ph_units
    if flags & K.NUM_SINGLE_STRESS:
        out = _single_stress(out)
    return out


def _single_stress(ph):
    """NUM_SINGLE_STRESS: keep only the last primary stress ("'"), demoting earlier ones to
    secondary (",") — Spanish/French "treinta y uno" -> tɾˌeɪntaiˈuno."""
    marks = [i for i, c in enumerate(ph) if c == "'"]
    if len(marks) <= 1:
        return ph
    chars = list(ph)
    for i in marks[:-1]:
        chars[i] = ","
    return "".join(chars)


def _three_digit(tr_dict, value, ctx, flags=0, final=True, femin=False):
    """0..999 -> phonemes (no leading/trailing magnitude)."""
    hundreds, tens_units = divmod(value, 100)
    out = ""
    if hundreds:
        # lexicalised hundreds (es cien/ciento/doscientos): _NC0 exact, else _NC
        lex = (_frag(tr_dict, "%dc0" % hundreds, ctx) if tens_units == 0 else "") \
            or _frag(tr_dict, "%dc" % hundreds, ctx)
        if lex:
            out += lex
        else:
            if not (hundreds == 1 and (flags & K.NUM_OMIT_1_HUNDRED)):
                out += _digit(tr_dict, hundreds, ctx, final=False)  # before "hundred"
            out += _frag(tr_dict, "0c", ctx)
    if tens_units:
        if hundreds:
            if flags & K.NUM_HUNDRED_AND:
                out += _frag(tr_dict, "0and", ctx)
            out += "||"  # break between hundreds and the tens/units
        out += _tens_units(tr_dict, tens_units, ctx, flags, final, femin)
    return out


ORDINAL_SUFFIXES = ("st", "nd", "rd", "th")

# --- Roman numerals (TranslateRoman, numbers.c:756) --------------------------

# The valid Roman letters and their values (numbers.c:773 `roman_numbers`/`roman_values`).
# Keyed lowercase — espeak lowercases the word before TranslateRoman (the original case is
# carried in the word flags), so the table is inspected against lowercase letters.
_ROMAN_VALUES = {"i": 1, "x": 10, "c": 100, "m": 1000, "v": 5, "l": 50, "d": 500}


def parse_roman(word):
    """Validate `word` as a Roman numeral and return its integer value, else None.

    Faithful port of the parse/validation loop (numbers.c:791-822): the subtractive-notation
    rules, the max-3-repeat rule, the `prev>1 && prev!=10 && prev!=100` guard, and the
    `acc%10`/`prev*10` subtract guards. Any violation returns None ("not a Roman numeral", the
    caller then falls through to ordinary translation). `word` must already be lowercased and
    contain no surrounding spaces (the C loop runs until a space; here the whole string is the
    token)."""
    acc = 0
    prev = 0
    subtract = 0x7FFF
    repeat = 0
    for c in word:
        value = _ROMAN_VALUES.get(c)
        if value is None:
            return None
        if value == prev:
            repeat += 1
            if repeat >= 3:
                return None
        else:
            repeat = 0
        if prev > 1 and prev != 10 and prev != 100:
            if value >= prev:
                return None
        if prev != 0 and prev < value:
            if (acc % 10) != 0 or (prev * 10) < value:
                return None
            subtract = prev
            value -= subtract
        elif value >= subtract:
            return None
        else:
            acc += prev
        prev = value
    acc += prev
    return acc


def _num2_ordinal(tr_dict, value, ctx, flags, flags2, ph_ord2, ph_ord2x):
    """Ordinal reading of a 1..99 value (port of LookupNum2's is_ordinal path, numbers.c:1006).

    Called with control bits ordinal|final|tens-units-only (0x7) — the state TranslateNumber
    passes for a standalone <100 ordinal, which is every Roman ordinal in an/it/da/bg/fo/kl
    (max_roman<=49) and the <100 range for hu. `ph_ord2` is the ordinal ending suffix
    (Lookup `_#<roman_suffix>`, e.g. it/an "º"->"o"/"eno"); `ph_ord2x` its alternate
    (`_x#<suffix>`, used with the special `_%dox` standalone forms, LANG=an)."""
    units = value % 10
    tens = value // 10
    ph_ordinal = ph_ord2
    ph_tens = ""
    ph_digits = ""
    found = False
    found_ordinal = False
    ord_type = "o"
    # control&4 (tens+units only): a special standalone ordinal `_%dox` (irregular ordinals —
    # it primo/terzo/quarto, an) wins over the regular `_%do` stem.
    s = _frag(tr_dict, "%d%sx" % (value, ord_type), ctx)
    if s:
        found = True
        ph_digits = s
        if ph_ord2x:
            ph_ordinal = ph_ord2x
    if not found:
        s = _frag(tr_dict, "%d%s" % (value, ord_type), ctx)  # _%do
        if s:
            found = True
            ph_digits = s
    found_ordinal = found
    if not found and value < 20:
        # A teen/unit with no ordinal stem: read the whole value as its cardinal and let a generic
        # ordinal ending (`_ord`) carry the ordinal (da/kl "fjortende"). Only for value < 20 — a
        # >=20 value is always decomposed into tens + ordinal-unit (espeak never lexicalises a
        # tens+units ordinal, it 29 -> venti+novesimo, not the lexical "ventinove").
        if not ((flags2 & K.NUM2_NO_TEEN_ORDINALS) and 10 < value < 20):
            s = _frag(tr_dict, "%d" % value, ctx)  # cardinal `_%d`
            if s:
                found = True
                ph_digits = s
    if found:
        ph_tens = ""
    else:
        ph_tens = _frag(tr_dict, "%dX%s" % (tens, ord_type), ctx)  # ordinal tens `_%dXo`
        if ph_tens:
            found_ordinal = True
            if units != 0 and (flags2 & K.NUM2_MULTIPLE_ORDINAL):
                ph_tens += ph_ord2
        if not found_ordinal:
            ph_tens = _frag(tr_dict, "%dX" % tens, ctx)
        if not ph_tens and (flags & K.NUM_VIGESIMAL):
            units = value % 20
            ph_tens = _frag(tr_dict, "%dX" % (tens & 0xFE), ctx)
        ph_digits = ""
        if units > 0:
            u = ""
            if not (flags & K.NUM_SWAP_TENS):
                u = _frag(tr_dict, "%d%s" % (units, ord_type), ctx)  # ordinal unit `_%do`
                if u:
                    found_ordinal = True
            if not u:
                u = _frag(tr_dict, "%d" % units, ctx)
            ph_digits = u
    if not found_ordinal and not ph_ordinal:
        # no ordinal stem was available: append a generic ordinal ending (`_ord20` for exact
        # tens / swap-tens, else `_ord`) — da/kl "-ende", the Danish/Greenlandic path.
        if value >= 20 and (value % 10 == 0 or (flags & K.NUM_SWAP_TENS)):
            ph_ordinal = _frag(tr_dict, "ord20", ctx)
        if not ph_ordinal:
            ph_ordinal = _frag(tr_dict, "ord", ctx)
    if (flags & (K.NUM_SWAP_TENS | K.NUM_AND_UNITS)) and ph_tens and ph_digits:
        ph_and = _frag(tr_dict, "0and", ctx)
        if flags2 & K.NUM2_ORDINAL_NO_AND:
            ph_and = ""
        if flags & K.NUM_SWAP_TENS:
            out = ph_digits + ph_and + ph_tens + ph_ordinal
        else:
            out = ph_tens + ph_and + ph_digits + ph_ordinal
    else:
        if ((flags & K.NUM_SINGLE_VOWEL) and ph_tens and ph_digits
                and _first_vowel_start(ph_digits) and ph_tens[-1] in _VOWEL_LETTERS):
            ph_tens = ph_tens[:-1]
        out = ph_tens + ph_digits + ph_ordinal
    if flags & K.NUM_SINGLE_STRESS:
        out = _single_stress(out)
    return out


def roman_number_phonemes(tr_dict, value, ctx, flags, flags2, ordinal,
                          ph_ord2, ph_ord2x, break_numbers=K.BREAK_THOUSANDS):
    """The spoken-number phonemes for a Roman value: ordinal reading when `ordinal`, else the
    plain cardinal (translate_number). The `_roman` word and any AFTER placement are added by
    the caller (api._render_word)."""
    if ordinal and value < 100:
        return _num2_ordinal(tr_dict, value, ctx, flags, flags2, ph_ord2, ph_ord2x)
    # value >= 100 ordinal (only hu's dotted range) and every cardinal Roman: read as a plain
    # cardinal. hu's >=100 ordinal reading is not modelled (see api._translate_roman residual).
    return translate_number(tr_dict, str(value), ctx, flags, flags2=flags2,
                            break_numbers=break_numbers)


def _ordinal_stem(tr_dict, value, ctx):
    """Ordinal stem for 1..99 (the `_#<suffix>` ending is appended by the caller).
    Uses a special `_No` stem where one exists (first/second/twentieth/…), otherwise the
    cardinal; for tens+units the tens stays cardinal and only the unit is ordinalised."""
    stem = _frag(tr_dict, "%do" % value, ctx)
    if stem:
        return stem
    if value < 20:
        return _frag(tr_dict, str(value), ctx)
    tens, units = divmod(value, 10)
    if units == 0:
        return _frag(tr_dict, "%dx" % tens, ctx)
    return _frag(tr_dict, "%dx" % tens, ctx) + _ordinal_stem(tr_dict, units, ctx)


def translate_ordinal(tr_dict, digits, suffix, ctx=None, flags=K.NUM_HUNDRED_AND):
    """Translate an ordinal like '21st'/'100th': cardinal for the high part, ordinal stem
    for the final tens/units, then the suffix ending (`_#st` etc.)."""
    if ctx is None:
        ctx = _num_ctx(tr_dict)
    n = int(digits)
    tens_units = n % 100
    if n < 100:
        return _ordinal_stem(tr_dict, n, ctx) + _frag(tr_dict, "#" + suffix, ctx)
    out = translate_number(tr_dict, str(n - tens_units), ctx, flags)
    if tens_units:
        return (out + "||" + _ordinal_stem(tr_dict, tens_units, ctx)
                + _frag(tr_dict, "#" + suffix, ctx))
    # round hundred/thousand: the ending is a separate word ("hundred  th")
    return out + "||" + _frag(tr_dict, "#" + suffix, ctx)


def _whole_fraction(tr_dict, frac, ctx, flags):
    """The fractional part read as a single cardinal. LookupNum3 (numbers.c:1446) always emits a
    word break before a group's tens/units, which is leading — and so becomes a space after the
    decimal-point word — when the value has no hundreds digit (value < 100)."""
    ph = translate_number(tr_dict, frac, ctx, flags)
    n = int(frac)
    if 0 < n < 100:
        ph = "||" + ph
    return ph


def _translate_fraction(tr_dict, frac, ctx, flags):
    """Read the digits after the decimal point (numbers.c ~1712-1793). espeak varies the
    reading per language via the NUM_DFRACTION_* bits: digit-by-digit by default (nl/de/sv/…),
    or the fraction as a whole cardinal (fr/es/it/pt/ro/pl/cs/fi/tr/ca), sometimes with a
    "tenths"/"hundredths" suffix (hu/kk). The consumed-through index `i` tracks how many
    leading digits the DFRACTION branch spoke as a whole number; anything left is spoken
    digit-by-digit, and finally a `_dpt2` end-of-fraction word is appended if the language
    has one (ru "десятых")."""
    mode = flags & K.NUM_DFRACTION_BITS
    out = ""
    i = 0
    decimal_count = len(frac)
    if mode in (K.NUM_DFRACTION_2, K.NUM_DFRACTION_4):
        # French/Polish-style: strip and speak leading zeros, then the rest as one cardinal
        # if it is short enough (<=2 digits for _2, <=5 for _4).
        max_decimal_count = 5 if mode == K.NUM_DFRACTION_4 else 2
        while i < len(frac) and frac[i] == "0":
            out += _frag(tr_dict, "0", ctx)
            decimal_count -= 1
            i += 1
        if decimal_count <= max_decimal_count and i < len(frac):
            out += _whole_fraction(tr_dict, frac[i:], ctx, flags)
            i = len(frac)
    elif mode in (K.NUM_DFRACTION_1, K.NUM_DFRACTION_5, K.NUM_DFRACTION_6):
        # Italian/Hungarian/Kazakh: the whole fraction as a cardinal, with a
        # "tenths/hundredths/…" suffix (_0Z<count>) when there is a leading zero (it) or always
        # (hu/kk). If the suffix is missing, revert to digit-by-digit.
        num = _whole_fraction(tr_dict, frac, ctx, flags)
        reverted = False
        if frac[0] == "0" or mode != K.NUM_DFRACTION_1:
            suf = _frag(tr_dict, "0Z%d" % decimal_count, ctx)
            if not suf:
                reverted = True
            elif mode == K.NUM_DFRACTION_6:
                out += suf  # Kazakh says the suffix before the number
            else:
                num += suf
        if not reverted:
            out += num
            i = len(frac)
    elif mode == K.NUM_DFRACTION_3:
        # Romanian: the whole fraction as a cardinal when short and with no leading zero.
        if decimal_count <= 4 and frac[0] != "0":
            out += _whole_fraction(tr_dict, frac, ctx, flags)
            i = len(frac)
    elif mode == K.NUM_DFRACTION_7:
        # Sinhala: an alternate digit form (_<d>d) for every digit except the last.
        while decimal_count - 1 > 0:
            alt = _frag(tr_dict, "%sd" % frac[i], ctx)
            if not alt:
                break
            out += alt
            i += 1
            decimal_count -= 1
    # any remaining digits are spoken individually
    while i < len(frac) and frac[i].isdigit():
        out += "||" + _frag(tr_dict, frac[i], ctx)
        i += 1
    # end-of-fraction word (ru "десятых"); joined directly, matching the C strcat
    out += _frag(tr_dict, "dpt2", ctx)
    return out


def _split_groups(digits, break_numbers):
    """Split a digit string into magnitude groups, LOW group first (index == thousandplex).

    Port of the number-splitting loop in translate.c:1539. `break_numbers` is a bitmask over
    the count of digits still to come: a set bit means "start a new magnitude word here".
    BREAK_THOUSANDS marks every third digit (…,000,000); the Indian BREAK_LAKH_* masks mark
    2-digit groups above the first thousand (1,00,00,000 = crore/lakh/thousand). A group
    narrower than three digits is zero-padded back to three (translate.c:1568) so the
    3-digit reader below sees a normal hundreds/tens/units value.

    espeak only splits a token of more than four digits (translate.c:1540); up to four digits
    the whole value goes to LookupNum3, whose internal `hundreds >= 10` branch (numbers.c:1305)
    speaks the thousands the same way, so the plain thousands split is equivalent there.
    """
    digits = digits.lstrip("0") or "0"
    n = len(digits)
    if n <= 4 or break_numbers == K.BREAK_THOUSANDS:
        n_val = int(digits)
        groups = []
        while n_val > 0:
            groups.append(n_val % 1000)
            n_val //= 1000
        return groups
    groups, cur, nx = [], "", n
    for c in digits:
        cur += c
        nx -= 1
        if nx > 0 and (break_numbers >> nx) & 1:
            groups.append(cur)
            cur = ""
            if (break_numbers >> (nx - 1)) & 1:
                cur += "00"  # the next group has only 1 digit, make it three
            if nx >= 2 and (break_numbers >> (nx - 2)) & 1:
                cur += "0"  # the next group has only 2 digits (Indian languages), make it three
    groups.append(cur)
    return [int(g) for g in reversed(groups)]


def _leading_zeros(tr_dict, digits, ctx):
    """The `ph_zeros` prefix (numbers.c:1596): a number token written with leading zeros speaks
    each of them ("05" -> "zero five", "007" -> "zero zero seven"). The loop stops one short of
    the end, so the last digit is always read as a number — "00" is one spoken zero plus the
    value zero. The zeros are glued to each other but a word break separates them from the
    value, which LookupNum3 emits with a leading phonEND_WORD (numbers.c:1448)."""
    out = ""
    for c in digits[:-1]:
        if c != "0":
            break
        out += _frag(tr_dict, "0", ctx)
    return out


def translate_number(tr_dict, digits, ctx=None, flags=K.NUM_HUNDRED_AND, decimal_sep=".",
                     flags2=0, break_numbers=K.BREAK_THOUSANDS, leading_zeros=True):
    """Translate a number (optionally with a decimal part) to a phoneme string with `||`
    word breaks. `flags` is the language's langopts.numbers bitfield (NUM_*). The fractional
    part is read per the language's NUM_DFRACTION_* bits — see `_translate_fraction`."""
    if ctx is None:
        ctx = _num_ctx(tr_dict)
    if decimal_sep in digits:
        intpart, _, frac = digits.partition(decimal_sep)
        out = translate_number(tr_dict, intpart or "0", ctx, flags,
                               flags2=flags2, break_numbers=break_numbers)
        out += "||" + _frag(tr_dict, "dpt", ctx)
        out += _translate_fraction(tr_dict, frac, ctx, flags)
        # A spoken-number word break is a REAL word boundary (espeak spaces it via sourceix),
        # but the decimal-point word and the fraction digit fragments carry a trailing `_`
        # word-gap phoneme, leaving `_||` at the join. A bare `_` immediately before `||` is a
        # compound-join pause that SWALLOWS the break's space (render.encode_phoneme_string) —
        # correct for a dict compound (bestseller `_||`), wrong here. Reorder to `||_`: the pause
        # moves past the break so the space renders, while still blocking cross-boundary voicing
        # assimilation (pl `trzy przecinek zero…`: k stays k, not ɡ, and the space is kept).
        return out.replace("_||", "||_")
    # numbers.c:1585: a leading zero makes the token speak its zeros; only up to three digits,
    # a longer zero-led string is spoken digit by digit by the caller instead.
    if leading_zeros and len(digits) > 1 and digits[0] == "0" and len(digits) <= 3:
        zeros = _leading_zeros(tr_dict, digits, ctx)
        body = translate_number(tr_dict, digits.lstrip("0") or "0", ctx, flags, decimal_sep,
                                flags2, break_numbers, leading_zeros=False)
        return zeros + "||" + body if zeros else body
    if int(digits) == 0:
        return _frag(tr_dict, "0", ctx)
    groups = _split_groups(digits, break_numbers)
    parts = []
    higher_emitted = False
    pause_next = False  # a preceding magnitude group whose count >= 10 forces an inter-group pause
    for thousandplex in range(len(groups) - 1, -1, -1):
        gv = groups[thousandplex]
        if gv == 0:
            continue
        if thousandplex == 0:
            part = _three_digit(tr_dict, gv, ctx, flags, final=True)
            if higher_emitted and gv < 100 and (flags & K.NUM_HUNDRED_AND):
                # "and" before a final tens/units group after higher magnitudes ("mil e cinco",
                # "one thousand AND five"); the `_0and` fragment carries its own word breaks.
                part = _frag(tr_dict, "0and", ctx) + "||" + part
            if pause_next:
                part = "_!" + part
            parts.append(part)
            continue
        # A magnitude group (thousands/millions/…). LookupThousands (numbers.c:917) FIRST tries a
        # combined `_<value>M<thousandplex>` form that lexicalises value+magnitude together —
        # pt `_1M1` "mil" (not "um mil"), `_1M2` "um milhão" (singular). Only when no combined
        # form exists is the value spoken separately before the magnitude word
        # `_<M_Variant>M<thousandplex>` (pt `_0M1` "mil", `_0M2` "milhões" plural).
        # A magnitude fragment may end in the `_` word-gap phoneme (pt `_1M1` "m'il_"); it marks
        # the break to the next spoken group, which the `||` join already provides, so drop it.
        combined = _frag(tr_dict, "%dM%d" % (gv, thousandplex), ctx).rstrip("_")
        if combined:
            part = combined
        else:
            # `_0of` ("of") is spoken before the magnitude word when the count carries tens
            # (numbers.c:952); absent in most languages, so the lookup is normally empty.
            of = _frag(tr_dict, "0of", ctx) if (gv % 100) >= 20 else ""
            mag = _frag(tr_dict, "%s%d" % (_m_variant(gv, flags2), thousandplex), ctx)
            if not mag:
                # numbers.c:975 fallback chain: a magnitude word the language does not name
                # (uk has no `_1MA1`, sl no `_0MB1`) falls back to the plain thousand entries —
                # "say millions if neither this name nor the next lower is available", then
                # repeat "thousand". Without it the magnitude word would vanish entirely.
                if thousandplex > 3 and not _frag(tr_dict, "0M%d" % (thousandplex - 1), ctx):
                    mag = _frag(tr_dict, "0M2", ctx)
                if not mag:
                    mag = (_frag(tr_dict, "%dM1" % gv, ctx) or _frag(tr_dict, "0M1", ctx))
            mag = of + mag.rstrip("_")
            if gv == 1 and thousandplex == 1 and (flags & K.NUM_OMIT_1_THOUSAND):
                body = ""  # "mil" not "one thousand" (es)
            else:
                # numbers.c:1317: the count of a magnitude the language marks in numbers2 uses
                # the variant (feminine) numeral — ru "две тысячи", not "два тысячи".
                femin = bool(flags2 & (1 << thousandplex)) and thousandplex <= 3
                body = _three_digit(tr_dict, gv, ctx, flags, final=False, femin=femin)
            part = body
            if mag:
                part += ("||" if part else "") + mag
        if pause_next:
            part = "_!" + part
        # A "long" magnitude count (>= 10, i.e. carrying tens/hundreds) starts a fresh
        # intonation phrase: espeak sets off the FOLLOWING group with a pause (phonPAUSE_NOLINK)
        # — nl 12345 -> "twaalf duizend_ driehonderd…" keeps duizend's final t (the pause blocks
        # the ph_dutch t/d cross-word degemination, dˌœyzɛnt drˈi not dˌœyzɛn trˌi) and gives that
        # next group its own primary stress; a short count (2345, tʋˈeː dˌœyzɛn trˌi) does not. A
        # higher magnitude than thousand (millions+, thousandplex >= 2) always breaks the phrase
        # ("één miljoen_ tweehonderd…" -> tʋˈeː primary), as does any magnitude group once a higher
        # one has already been spoken (1002345 -> "…miljoen tʋˈeː dˌœyzɛnt drˈi…": the twee-duizend
        # section keeps its own phrase even though its count is < 10).
        pause_next = gv >= 10 or thousandplex >= 2 or higher_emitted
        higher_emitted = True
        parts.append(part)
    return "||".join(p for p in parts if p)


def _m_variant(value, flags2):
    """Port of M_Variant (numbers.c:872): the magnitude-word key stem `0M` for a value, or a
    grammatical-number variant (`0MA`/`0MB`/`1M`/`1MA`) for the languages that inflect the
    thousand/million word by the count it follows.

    Slavic (and Baltic) magnitude words take a different case/number after 1, after 2-4 and
    after 5+ — ru "один миллион" / "два миллиона" / "пять миллионов". The variant is selected
    by the NUM2_THOUSANDS_VAR_* bits of langopts.numbers2; a teen count (11-19, and 111-119…)
    always takes the plain 5+ form. Every other language uses the plain `0M` stem."""
    teens = 10 < (value % 100) < 20
    var = flags2 & K.NUM2_THOUSANDS_VAR_BITS
    if var == K.NUM2_THOUSANDS_VAR1:  # ru, be
        if not teens:
            if value % 10 == 1:
                return "1MA"
            if 2 <= value % 10 <= 4:
                return "0MA"
    elif var == K.NUM2_THOUSANDS_VAR2:  # cs, sk, mk
        if 2 <= value <= 4:
            return "0MA"
    elif var == K.NUM2_THOUSANDS_VAR3:  # pl
        if not teens and 2 <= value % 10 <= 4:
            return "0MA"
    elif var == K.NUM2_THOUSANDS_VAR4:  # lt, sl
        if teens or value % 10 == 0:
            return "0MB"
        if value % 10 == 1:
            return "0MA"
    elif var == K.NUM2_THOUSANDS_VAR5:  # bs, hr, sr
        if not teens:
            if value % 10 == 1:
                return "1M"
            if 2 <= value % 10 <= 4:
                return "0MA"
    return "0M"
