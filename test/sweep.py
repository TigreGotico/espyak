#!/usr/bin/env python3
"""Per-language pass-rate sweep against the espeak-ng oracle (P6).

For every language with a <lang>_rules file, sample headwords from its <lang>_list,
phonemize with espyak, compare to the oracle, and print a per-language pass-rate table
(also written to test/report.md). Use a small sample for a fast baseline.

    python3 test/sweep.py [N_words_per_lang]
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)
ORACLE_BIN = os.path.join(REPO, "oracle", "espeak-ng", "src", "espeak-ng")
ORACLE_ROOT = os.path.join(REPO, "oracle", "espeak-ng")
DICTSOURCE = os.path.join(REPO, "espyak", "data", "dictsource")


def oracle(words, lang):
    # one word per call — batching via newline misaligns when espeak merges/splits clauses
    env = dict(os.environ, ESPEAK_DATA_PATH=ORACLE_ROOT)
    out = []
    for w in words:
        r = subprocess.run(
            [ORACLE_BIN, "-q", "--ipa", "-v", lang], input=w,
            capture_output=True, text=True, env=env, timeout=30,
        )
        out.append(r.stdout.strip())
    return out


def sample_words(lang, n):
    words = []
    path = os.path.join(DICTSOURCE, "%s_list" % lang)
    if not os.path.isfile(path):
        return words
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("//") or line.startswith("_"):
                continue
            tok = line.split()[0]
            if tok and tok[0].isalpha() and tok.isalpha() and len(tok) >= 3:
                words.append(tok)
            if len(words) >= n:
                break
    return words


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    from espyak.api import G2P
    langs = sorted(f[:-6] for f in os.listdir(DICTSOURCE) if f.endswith("_rules"))
    rows = []
    for lang in langs:
        words = sample_words(lang, n)
        if not words:
            continue
        try:
            g = G2P(lang)
        except Exception as e:
            rows.append((lang, 0, len(words), "load-error:%s" % type(e).__name__))
            continue
        exp = oracle(words, lang)
        ok = err = 0
        for i, w in enumerate(words):
            e = exp[i] if i < len(exp) else ""
            try:
                m = g.phonemize(w)
            except Exception:
                err += 1
                continue
            if m == e:
                ok += 1
        pct = 100.0 * ok / len(words)
        rows.append((lang, ok, len(words), "%.0f%%" % pct + (" err=%d" % err if err else "")))

    rows.sort(key=lambda r: -(r[1] / max(r[2], 1)))
    lines = ["# Per-language pass rate (sample=%d)" % n, "",
             "| lang | pass | n | rate |", "| --- | --- | --- | --- |"]
    for lang, ok, tot, note in rows:
        lines.append("| %s | %d | %d | %s |" % (lang, ok, tot, note))
    report = "\n".join(lines) + "\n"
    with open(os.path.join(HERE, "report.md"), "w", encoding="utf-8") as fh:
        fh.write(report)
    # summary
    tot_ok = sum(r[1] for r in rows)
    tot_n = sum(r[2] for r in rows)
    hi = sum(1 for r in rows if r[1] / max(r[2], 1) >= 0.8)
    print("languages: %d  | overall %d/%d = %.1f%%  | >=80%%: %d langs"
          % (len(rows), tot_ok, tot_n, 100.0 * tot_ok / max(tot_n, 1), hi))
    print("top 15:", [r[0] for r in rows[:15]])
    print("bottom 15:", [(r[0], r[3]) for r in rows[-15:]])


if __name__ == "__main__":
    main()
