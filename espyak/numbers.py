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


def _tens_units(tr_dict, value, ctx, flags=0, final=True):
    """1..99 -> phonemes. Honours NUM_SWAP_TENS (units before tens, e.g. German
    "ein-und-zwanzig") and NUM_AND_UNITS ("and" between tens and units)."""
    if value < 20:
        return _digit(tr_dict, value, ctx, final)
    tens, units = divmod(value, 10)
    if units == 0:
        # exact ten: a lexicalised full form if the language has one (es "veinte"),
        # otherwise the combining tens form (en "twenty").
        return _frag(tr_dict, str(value), ctx) or _frag(tr_dict, "%dx" % tens, ctx)
    ph_tens = _frag(tr_dict, "%dx" % tens, ctx)
    if flags & K.NUM_SWAP_TENS:
        # units "and" tens (German "ein-und-zwanzig", Faroese "seks-og-tríati"). espeak
        # concatenates units+_0and+tens directly (numbers.c:1198); any word break comes from
        # the `_0and` fragment itself (de `||_|Unt` breaks, fo `u-o` joins as one word).
        ph_and = _frag(tr_dict, "0and", ctx)
        out = _digit(tr_dict, units, ctx, False) + ph_and + ph_tens
    else:
        ph_and = _frag(tr_dict, "0and", ctx) if (flags & K.NUM_AND_UNITS) else ""
        out = ph_tens + ph_and + _digit(tr_dict, units, ctx, final)
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


def _three_digit(tr_dict, value, ctx, flags=0, final=True):
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
        out += _tens_units(tr_dict, tens_units, ctx, flags, final)
    return out


ORDINAL_SUFFIXES = ("st", "nd", "rd", "th")


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
        ctx = LookupContext()
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


def translate_number(tr_dict, digits, ctx=None, flags=K.NUM_HUNDRED_AND, decimal_sep="."):
    """Translate a number (optionally with a decimal part) to a phoneme string with `||`
    word breaks. `flags` is the language's langopts.numbers bitfield (NUM_*). The fractional
    part is read per the language's NUM_DFRACTION_* bits — see `_translate_fraction`."""
    if ctx is None:
        ctx = LookupContext()
    if decimal_sep in digits:
        intpart, _, frac = digits.partition(decimal_sep)
        out = translate_number(tr_dict, intpart or "0", ctx, flags)
        out += "||" + _frag(tr_dict, "dpt", ctx)
        out += _translate_fraction(tr_dict, frac, ctx, flags)
        return out
    n = int(digits)
    if n == 0:
        return _frag(tr_dict, "0", ctx)
    groups = []
    while n > 0:
        groups.append(n % 1000)
        n //= 1000
    parts = []
    higher_emitted = False
    for thousandplex in range(len(groups) - 1, -1, -1):
        gv = groups[thousandplex]
        if gv == 0:
            continue
        if thousandplex == 1 and gv == 1 and (flags & K.NUM_OMIT_1_THOUSAND):
            part = ""  # "mil" not "one thousand" (es)
        else:
            part = _three_digit(tr_dict, gv, ctx, flags, final=(thousandplex == 0))
        if thousandplex == 0 and higher_emitted and gv < 100 and (flags & K.NUM_HUNDRED_AND):
            # "and" before a final tens/units group after higher magnitudes (one thousand
            # AND five). espeak doubles the space when a middle group was skipped.
            part = _frag(tr_dict, "0and", ctx) + "||" + part
        if thousandplex > 0:
            mag = _frag(tr_dict, "0m%d" % thousandplex, ctx)
            if mag:
                part += ("||" if part else "") + mag
            higher_emitted = True
        parts.append(part)
    return "||".join(p for p in parts if p)
