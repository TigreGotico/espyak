#!/usr/bin/env python3
"""Diff espyak against the real espeak-ng binary, if it is installed.

    python examples/compare_oracle.py es díganme hola buenos

Prints espyak's output next to `espeak-ng -q --ipa -v <lang>` and flags any mismatch.
espyak targets byte-for-byte parity, so a mismatch is a bug worth reporting.
"""
import shutil
import subprocess
import sys

from espyak import G2P


def oracle(lang, word):
    espeak = shutil.which("espeak-ng") or shutil.which("espeak")
    if not espeak:
        return None
    out = subprocess.run(
        [espeak, "-q", "--ipa", "-v", lang],
        input=word + "\n", capture_output=True, text=True,
    )
    return out.stdout.strip()


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    lang, words = argv[0], argv[1:]
    g2p = G2P(lang)
    any_diff = False
    for w in words:
        mine = g2p.phonemize(w)
        ref = oracle(lang, w)
        if ref is None:
            print(f"{w:16} espyak={mine!r}   (espeak-ng not installed; skipping diff)")
            continue
        ok = "OK " if mine == ref else "DIFF"
        any_diff |= mine != ref
        print(f"[{ok}] {w:16} espyak={mine!r}  oracle={ref!r}")
    return 1 if any_diff else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
