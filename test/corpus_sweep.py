"""Second parity measurement: real words from espeak's own language-pronunciation.test.

The primary sweep (sweep.py) samples <lang>_list headwords, which only exist for ~86 of
espeak's 117 rule-languages — the non-Latin-script langs (Indic/CJK/Semitic/…) have only
single-character letter-name entries, so they go unmeasured. espeak ships UDHR-style
sentences per language in tests/language-pronunciation.test; this tool extracts that input
text, tokenises it into words, and compares our output to the oracle binary per word.

Usage: python test/corpus_sweep.py [lang ...]   (no args = every lang in the corpus)
"""
import sys, os, re, shlex, subprocess

ORACLE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "oracle", "espeak-ng"))
TESTF = os.path.join(ORACLE, "tests", "language-pronunciation.test")
_WORD_SPLIT = re.compile(r"[\s,.;:!?()«»\"'、。।॥،؟]+")


def corpus():
    """lang -> list[word] extracted from language-pronunciation.test input text."""
    raw = re.sub(r"\\\n", " ", open(TESTF, encoding="utf-8").read())
    out = {}
    for line in raw.split("\n"):
        line = line.strip()
        if not line.startswith("test_phon"):
            continue
        try:
            parts = shlex.split(line)
        except ValueError:
            continue
        if len(parts) < 4:
            continue
        lang, text = parts[1], parts[3]
        words = [w for w in _WORD_SPLIT.split(text) if w]
        if words:
            out.setdefault(lang, [])
            for w in words:
                if w not in out[lang]:
                    out[lang].append(w)
    return out


def oracle_words(words, lang):
    r = subprocess.run([os.path.join(ORACLE, "src", "espeak-ng"), "-q", "--ipa", "-v", lang],
                       input="\n".join(words) + "\n", capture_output=True, text=True,
                       env={**os.environ, "ESPEAK_DATA_PATH": ORACLE})
    return [x.strip() for x in r.stdout.split("\n")][:len(words)]


def main(argv):
    from espyak.api import G2P
    data = corpus()
    langs = argv or sorted(data)
    rules_dir = os.path.join(ORACLE, "dictsource")
    total_ok = total = 0
    rows = []
    skipped = []
    for lang in langs:
        words = data.get(lang, [])[:40]
        if not words:
            continue
        # voice variants (en-US, en-GB-x-rp, hyw, …) have no own _rules file — they reuse
        # a base lang's rules; skip them, the base lang is measured under its own name.
        if not os.path.exists(os.path.join(rules_dir, lang + "_rules")):
            skipped.append(lang)
            continue
        try:
            g = G2P(lang)
        except Exception as e:
            rows.append((lang, 0, len(words), "G2P FAIL: %s" % e))
            continue
        ora = oracle_words(words, lang)
        ok = sum(1 for i in range(min(len(words), len(ora)))
                 if g.phonemize(words[i]) == ora[i])
        rows.append((lang, ok, len(words), ""))
        total_ok += ok
        total += len(words)
    rows.sort(key=lambda r: r[1] / max(r[2], 1))
    for lang, ok, n, err in rows:
        print("%-5s %3d/%-3d %3d%%  %s" % (lang, ok, n, 100 * ok // max(n, 1), err))
    print("=== corpus langs: %d | words %d/%d = %.1f%% | skipped variants: %d ===" % (
        len(rows), total_ok, total, 100 * total_ok / max(total, 1), len(skipped)))


if __name__ == "__main__":
    main(sys.argv[1:])
