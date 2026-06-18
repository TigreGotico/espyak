"""force_compat registry — gates deliberate divergences from upstream espeak-ng.

Every place where this port intentionally deviates from espeak-ng's observable
behavior (usually to fix an upstream bug) is registered here and gated at the call
site::

    if ctx.force_compat:
        result = _bug_for_bug_espeak()   # reproduces upstream exactly, bug included
    else:
        result = _corrected()            # documented improvement

With ``force_compat=True`` (the default) output is byte-for-byte identical to the
oracle. ``docs/divergences.md`` is generated from this registry so the divergence
list has a single source of truth.
"""

DIVERGENCES = {}


class Divergence:
    def __init__(self, div_id, c_ref, reason):
        self.id = div_id
        self.c_ref = c_ref  # espeak-ng reference: file:function (and line if useful)
        self.reason = reason

    def __repr__(self):
        return "Divergence(%r, %r)" % (self.id, self.c_ref)


def register(div_id, c_ref, reason):
    """Register a divergence point. Returns the Divergence for reference at the site."""
    div = Divergence(div_id, c_ref, reason)
    DIVERGENCES[div_id] = div
    return div


def render_docs():
    """Render docs/divergences.md content from the registry."""
    lines = [
        "# Divergences from espeak-ng",
        "",
        "Auto-generated from `espyak/compat.py`. Each entry is gated behind the",
        "`force_compat` flag (default `True` reproduces espeak-ng exactly).",
        "",
        "| id | espeak-ng reference | reason |",
        "| --- | --- | --- |",
    ]
    for div in sorted(DIVERGENCES.values(), key=lambda d: d.id):
        lines.append("| `%s` | `%s` | %s |" % (div.id, div.c_ref, div.reason))
    if not DIVERGENCES:
        lines.append("| _(none yet)_ | | |")
    return "\n".join(lines) + "\n"
