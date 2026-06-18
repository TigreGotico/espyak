"""Cardinal-number translation (port of the common path of numbers.c).

Reads the language's `_list` number fragments (`_0`.._19 units/teens, `_Nx` tens,
`_0c` hundred, `_0m1`.._0m10 magnitudes, `_0and` the connective "and") and assembles
them with the standard grouping. This covers the NUM_HUNDRED_AND default (English et
al.); the many per-language NUM_* variants (decimal-comma, ordinals, swap-tens,
myriads, …) are not yet modelled — see numbers.c.

Word breaks between components use `||` so the renderer emits a space, matching how the
`_Nx` tens fragments already carry a trailing `||`.
"""
from espyak.dictionary import LookupContext


def _frag(tr_dict, key, ctx):
    """Look up a `_<key>` number fragment; '' if absent."""
    ph, _flags = tr_dict.lookup("_" + key.lower(), ctx)
    return ph or ""


def _tens_units(tr_dict, value, ctx):
    """1..99 -> phonemes."""
    if value < 20:
        return _frag(tr_dict, str(value), ctx)
    tens, units = divmod(value, 10)
    out = _frag(tr_dict, "%dx" % tens, ctx)
    if units:
        out += _frag(tr_dict, str(units), ctx)
    return out


def _three_digit(tr_dict, value, ctx, hundred_and):
    """0..999 -> phonemes (no leading/trailing magnitude)."""
    hundreds, tens_units = divmod(value, 100)
    out = ""
    if hundreds:
        out += _frag(tr_dict, str(hundreds), ctx) + _frag(tr_dict, "0c", ctx)
        if tens_units and hundred_and:
            out += _frag(tr_dict, "0and", ctx) + "||"
    if tens_units:
        out += _tens_units(tr_dict, tens_units, ctx)
    return out


def translate_number(tr_dict, digits, ctx=None, hundred_and=True):
    """Translate a run of decimal digits to a phoneme string with `||` word breaks."""
    if ctx is None:
        ctx = LookupContext()
    n = int(digits)
    if n == 0:
        return _frag(tr_dict, "0", ctx)
    groups = []
    while n > 0:
        groups.append(n % 1000)
        n //= 1000
    parts = []
    for thousandplex in range(len(groups) - 1, -1, -1):
        gv = groups[thousandplex]
        if gv == 0:
            continue
        part = _three_digit(tr_dict, gv, ctx, hundred_and)
        if thousandplex > 0:
            mag = _frag(tr_dict, "0m%d" % thousandplex, ctx)
            if mag:
                part += "||" + mag
        parts.append(part)
    return "||".join(p for p in parts if p)
