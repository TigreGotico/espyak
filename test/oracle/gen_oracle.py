#!/usr/bin/env python3
"""Generate ground-truth phoneme fixtures from the espeak-ng oracle binary.

For each language and each input word, run the pinned ``espeak-ng`` binary in a few
output modes and record ``word -> expected`` into ``test/fixtures/<lang>/<mode>.jsonl``.
These fixtures are the byte-exact target the Python engine must reproduce.

Usage:
    python3 test/oracle/gen_oracle.py --lang en              # default sample corpus
    python3 test/oracle/gen_oracle.py --lang en --words FILE
    python3 test/oracle/gen_oracle.py --all                  # every dictsource lang
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "test"))
from oracle_source import find  # noqa: E402
DICTSOURCE = os.path.join(REPO, "espyak", "data", "dictsource")
FIXTURES = os.path.join(REPO, "test", "fixtures")

# Output modes: name -> extra espeak-ng args. All run with -q (quiet, no audio).
MODES = {
    "ipa": ["--ipa"],
    "ipa_sep": ["--ipa=3", "--sep=_"],
    "kirshenbaum": ["-x"],
}


def run_espeak(text, lang, extra):
    binary, data_root = find()
    env = dict(os.environ, ESPEAK_DATA_PATH=data_root)
    cmd = [binary, "-q", "-v", lang, *extra]
    out = subprocess.run(
        cmd, input=text, capture_output=True, text=True, env=env, timeout=30,
    )
    return out.stdout.strip("\n")


def sample_words(lang):
    """Default per-language corpus: headwords from <lang>_list (free test cases)."""
    words = []
    path = os.path.join(DICTSOURCE, "%s_list" % lang)
    if os.path.isfile(path):
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("//"):
                    continue
                tok = line.split()[0]
                # skip rule/flag pseudo-entries (start with _ or $ or contain %)
                if tok and tok[0].isalpha() and "$" not in tok:
                    words.append(tok)
    # de-dup, cap
    seen, uniq = set(), []
    for w in words:
        if w not in seen:
            seen.add(w)
            uniq.append(w)
    return uniq[:2000]


def gen_lang(lang, words):
    outdir = os.path.join(FIXTURES, lang)
    os.makedirs(outdir, exist_ok=True)
    for mode, extra in MODES.items():
        rows = []
        for w in words:
            rows.append({"word": w, "expected": run_espeak(w, lang, extra)})
        with open(os.path.join(outdir, "%s.jsonl" % mode), "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("  %s: %d words x %d modes" % (lang, len(words), len(MODES)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", help="language code")
    ap.add_argument("--words", help="file with one word per line")
    ap.add_argument("--all", action="store_true", help="all dictsource languages")
    args = ap.parse_args()

    try:
        find()
    except RuntimeError as problem:
        sys.exit(str(problem))

    if args.all:
        langs = sorted(
            f[:-6] for f in os.listdir(DICTSOURCE) if f.endswith("_rules")
        )
    elif args.lang:
        langs = [args.lang]
    else:
        sys.exit("specify --lang or --all")

    for lang in langs:
        if args.words:
            with open(args.words, encoding="utf-8") as fh:
                words = [w.strip() for w in fh if w.strip()]
        else:
            words = sample_words(lang)
        if not words:
            print("  %s: no words, skipped" % lang)
            continue
        gen_lang(lang, words)


if __name__ == "__main__":
    main()
