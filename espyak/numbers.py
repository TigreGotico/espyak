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


def _initial_stress(ph):
    """NUM_SINGLE_STRESS_I: keep only the FIRST primary stress ("'"), demoting later ones to
    secondary (",").

    The mirror image of _single_stress. Dutch (and Welsh) put the single accent of a compound
    numeral at the FRONT: "tweeënveertig" is tʋˈeːɛnfˌɪːrtəx, not tʋˌeːɛnfˈɪːrtəx, and
    "tweehonderd" is tʋˈeːhˌɔndərt. German, which otherwise shares NUM_SWAP_TENS, keeps a
    primary on both parts (tsvˈaɪhˈʊndɜt) and so must NOT set this flag.

    Applied per thousands-group by translate_number, matching espeak: 12345 is
    tʋˈaːlf dˌœyzɛnt drˈihˌɔndərt vˌɛɪfɛnfˌɪːrtəx -- one primary in "twaalf duizend",
    a second in "driehonderdvijfenveertig".
    """
    marks = [i for i, c in enumerate(ph) if c == "'"]
    if len(marks) <= 1:
        return ph
    chars = list(ph)
    for i in marks[1:]:
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


def translate_number(tr_dict, digits, ctx=None, flags=K.NUM_HUNDRED_AND, decimal_sep="."):
    """Translate a number (optionally with a decimal part) to a phoneme string with `||`
    word breaks. `flags` is the language's langopts.numbers bitfield (NUM_*). A fractional
    part is read as "point" then each digit individually."""
    if ctx is None:
        ctx = LookupContext()
    if decimal_sep in digits:
        intpart, _, frac = digits.partition(decimal_sep)
        out = translate_number(tr_dict, intpart or "0", ctx, flags)
        out += "||" + _frag(tr_dict, "dpt", ctx)
        for d in frac:
            if d.isdigit():
                out += "||" + _frag(tr_dict, d, ctx)
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
    out = "||".join(p for p in parts if p)
    if flags & K.NUM_SINGLE_STRESS_I:
        # One primary accent at the FRONT of the numeral (nl): "tweeënveertig" is
        # tʋˈeːɛnfˌɪːrtəx, not tʋˌeːɛnfˈɪːrtəx, and 1234 is dˈœyzɛn tʋˌeːhˌɔndərt
        # vˌirɛndˌɛrtəx. German shares NUM_SWAP_TENS but keeps a primary on both parts
        # (tsvˈaɪhˈʊndɜt), so it must not set this flag.
        #
        # Known limitation: espeak starts a SECOND primary when a higher group is itself a
        # multi-word numeral (12345 -> tʋˈaːlf dˌœyzɛnt drˈihˌɔndərt vˌɛɪfɛnfˌɪːrtəx). That
        # per-group rule is not modelled here; numbers above 9999 get a single primary.
        out = _initial_stress(out)
    return out
