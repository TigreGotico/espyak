"""Command-line entry point: mirror a subset of espeak-ng's G2P invocation.

Currently exposes the render path (phoneme-string -> IPA/Kirshenbaum). Full text
translation is wired as the matcher lands.
"""
import argparse
import sys

from espyak.api import G2P


def main(argv=None):
    ap = argparse.ArgumentParser(prog="espyak", description="espeak-ng G2P (pure Python)")
    ap.add_argument("-v", "--lang", default="en", help="language/voice code")
    ap.add_argument("-x", action="store_true", help="Kirshenbaum output (default: IPA)")
    ap.add_argument("--sep", help="separator character between phonemes")
    ap.add_argument("--tie", help="tie character within multi-char phonemes")
    ap.add_argument("--phonemes", action="store_true",
                    help="treat input as a phoneme mnemonic string (render path)")
    ap.add_argument("text", nargs="?", help="input text (or '-' for stdin)")
    args = ap.parse_args(argv)

    text = args.text
    if text in (None, "-"):
        text = sys.stdin.read()
    text = text.strip()

    g = G2P(args.lang)
    if args.phonemes:
        out = g.render(text, ipa=not args.x, tie=args.tie, separator=args.sep)
    else:
        out = g.phonemize(text, ipa=not args.x, tie=args.tie, separator=args.sep)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
