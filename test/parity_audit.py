#!/usr/bin/env python3
"""Full headword parity audit: espyak vs the espeak-ng oracle, ALL headwords, every language.

Unlike sweep.py (which samples alphabetic len>=3 headwords and prints only rates), this tests
*every* dictionary headword (the edge cases — single accented letters, ordinal suffixes,
U+ names — are where parity actually breaks) and dumps every mismatch for fixing.

    python3 test/parity_audit.py [--cap N] [--langs en,es,..] [--out NAME]

Oracle calls run one-word-per-process (newline-batching misaligns when espeak splits clauses)
but are fanned out across threads, so a full run is minutes, not an hour.
Writes test/<out>.jsonl (mismatches) + test/<out>.md (per-language table + category counts).
"""
import argparse
import json
import os
import signal
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor


def _alarm(sig, frame):
    raise TimeoutError("phonemize timed out")

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)
ORACLE_BIN = os.path.join(REPO, "oracle", "espeak-ng", "src", "espeak-ng")
ORACLE_ROOT = os.path.join(REPO, "oracle", "espeak-ng")
DICTSOURCE = os.path.join(REPO, "espyak", "data", "dictsource")
ENV = dict(os.environ, ESPEAK_DATA_PATH=ORACLE_ROOT)


def oracle_one(word, lang):
    try:
        r = subprocess.run([ORACLE_BIN, "-q", "--ipa", "-v", lang], input=word,
                           capture_output=True, text=True, env=ENV, timeout=30)
        return r.stdout.strip()
    except Exception:
        return None


import re
_COND = re.compile(r"^\?!?\d+")  # leading dict-condition prefix: "?3 z", "?3_.p"


def headwords(lang, cap):
    """Distinct real headwords from <lang>_list: strip a leading ?N condition, skip the
    internal keys (_punct, $directives, %stress, U+codepoint) — keep words/letters/numbers."""
    out, seen = [], set()
    path = os.path.join(DICTSOURCE, "%s_list" % lang)
    if not os.path.isfile(path):
        return out
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            s = line.strip()
            if not s or s.startswith("//"):
                continue
            toks = s.split()
            first = toks[0]
            m = _COND.match(first)
            if m:
                rest = first[m.end():]
                hw = rest if rest else (toks[1] if len(toks) > 1 else "")
            else:
                hw = first
            if not hw or hw[0] in "_$%@&" or hw[:2].lower() == "u+":
                continue
            if not (hw[0].isalpha() or hw[0].isdigit()) or hw in seen:
                continue
            seen.add(hw)
            out.append(hw)
            if cap and len(out) >= cap:
                break
    return out


def variant_map():
    """Map every loadable sub-dialect VARIANT voice code -> its base language (pt-br -> pt,
    en-029 -> en, ca-nw -> ca, ...). A variant is a lang/<group>/<code> voice file whose
    resolved base language differs from the code itself (voice.VoiceConfig.is_variant). The
    base language's headwords are run through G2P(variant) and `espeak-ng -v <variant>` so the
    dialect's `dictrules`/`replace`/phoneme-table layer is checked, not just the base dict."""
    from espyak import voice as _voice
    from espyak import data_paths
    out = {}
    for group in sorted(os.listdir(data_paths.LANG_DIR)):
        gdir = os.path.join(data_paths.LANG_DIR, group)
        if not os.path.isdir(gdir):
            continue
        for name in sorted(os.listdir(gdir)):
            if not os.path.isfile(os.path.join(gdir, name)):
                continue
            try:
                cfg = _voice.load(name)
            except Exception:
                continue
            if cfg.is_variant and headwords(cfg.base_lang, 1):
                out[name] = cfg.base_lang
    return out


def categorize(word):
    if len(word) == 1:
        return "single-char" if word.isalpha() else "single-symbol"
    if not word.isalpha():
        return "non-alpha"
    if len(word) == 2:
        return "two-letter"
    return "word"


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap", type=int, default=0, help="max headwords per lang (0 = all)")
    ap.add_argument("--langs", default="", help="comma-separated subset")
    ap.add_argument("--out", default="parity_headwords")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--variants", action="store_true",
                    help="audit sub-dialect VARIANTS (pt-br, en-029, ca-nw, ...) instead of base "
                         "languages: base-language headwords through G2P(variant) vs "
                         "`espeak-ng -v <variant>`, so the dialect's dictrules/replace/table layer "
                         "is tracked. --langs filters to specific variant codes.")
    args = ap.parse_args(argv)
    if not os.path.isfile(ORACLE_BIN):
        print("oracle binary not built:", ORACLE_BIN, file=sys.stderr)
        return 2
    from espyak.api import G2P
    signal.signal(signal.SIGALRM, _alarm)  # guard against any single-input phonemize hang

    if args.variants:
        # each unit is (variant_code, base_lang); headwords come from the BASE language's _list,
        # but both espyak and the oracle run under the variant voice so the dialect layer applies.
        vmap = variant_map()
        if args.langs:
            # voice files are file-cased (pt-BR, en-GB-x-gbcwmd, ru-cl); match case-insensitively
            # so `--langs pt-br,en-029` selects them as espeak/G2P would (case-insensitive codes).
            wanted = {c.lower() for c in args.langs.split(",")}
            vmap = {v: b for v, b in vmap.items() if v.lower() in wanted}
        units = [(v, vmap[v]) for v in sorted(vmap)]
    else:
        if args.langs:
            langs = args.langs.split(",")
        else:
            langs = sorted(f[:-6] for f in os.listdir(DICTSOURCE) if f.endswith("_rules"))
        units = [(lang, lang) for lang in langs]

    rows, mismatches, cats = [], [], {}
    pool = ThreadPoolExecutor(max_workers=args.workers)
    for lang, base in units:
        words = headwords(base, args.cap)
        if not words:
            continue
        try:
            # parity is measured against espeak byte-for-byte, so run in force_compat mode (bugs
            # included); the default G2P is the linguistically correct engine (see docs/divergences.md)
            g = G2P(lang, force_compat=True)
        except Exception as e:
            rows.append((lang, 0, 0, "load-error:%s" % type(e).__name__))
            continue
        exp = list(pool.map(lambda w: oracle_one(w, lang), words))
        ok = err = 0
        for w, e in zip(words, exp):
            if e is None:
                err += 1
                continue
            signal.alarm(10)
            try:
                m = g.phonemize(w)
            except BaseException:  # TimeoutError or any engine error: count, don't abort the run
                err += 1
                continue
            finally:
                signal.alarm(0)
            if m == e:
                ok += 1
            else:
                c = categorize(w)
                cats[c] = cats.get(c, 0) + 1
                if sum(1 for x in mismatches if x["lang"] == lang) < 40:
                    mismatches.append({"lang": lang, "word": w, "espyak": m,
                                       "oracle": e, "cat": c})
        n = len(words)
        rows.append((lang, ok, n, "%.1f%%" % (100.0 * ok / max(n, 1)) + (" err=%d" % err if err else "")))
        label = "%s (%s)" % (lang, base) if lang != base else lang
        print("%-22s %5d/%-5d %s" % (label, ok, n, rows[-1][3]), flush=True)

    rows.sort(key=lambda r: (r[1] / max(r[2], 1), r[2]))
    with open(os.path.join(HERE, args.out + ".jsonl"), "w", encoding="utf-8") as fh:
        for m in mismatches:
            fh.write(json.dumps(m, ensure_ascii=False) + "\n")
    tot_ok = sum(r[1] for r in rows)
    tot_n = sum(r[2] for r in rows)
    kind = "dialect-variant" if args.variants else "base-language"
    lines = ["# Full-headword %s parity vs espeak-ng 1.52.0 (cap=%s)" % (kind, args.cap or "all"), "",
             "Overall **%d/%d = %.2f%%** across %d %s." % (
                 tot_ok, tot_n, 100.0 * tot_ok / max(tot_n, 1), len(rows),
                 "variants" if args.variants else "languages"), "",
             "Mismatch categories: " + ", ".join("%s=%d" % kv for kv in sorted(cats.items(), key=lambda x: -x[1])), "",
             "| lang | pass | n | rate |", "| --- | --- | --- | --- |"]
    for lang, ok, n, note in rows:
        lines.append("| %s | %d | %d | %s |" % (lang, ok, n, note))
    with open(os.path.join(HERE, args.out + ".md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("=" * 60)
    print("OVERALL %d/%d = %.2f%%  | %d langs | cats=%s" %
          (tot_ok, tot_n, 100.0 * tot_ok / max(tot_n, 1), len(rows), cats))
    print("worst 20:", [(r[0], r[3]) for r in rows[:20]])
    print("mismatches dumped:", len(mismatches), "->", args.out + ".jsonl")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
