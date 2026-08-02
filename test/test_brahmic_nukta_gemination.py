"""Byte-exact force_compat parity for the Brahmic/Indic nukta + gemination tail.

Each case pins a mechanism that used to diverge from espeak-ng 1.52.0 (oracle):

- Nukta letters (Devanagari base+U+093C and the precomposed U+095C/U+095F …) are Unicode
  FULL-COMPOSITION-EXCLUSIONS: NFC(U+095C) DEcomposes to ड+़ instead of composing. espeak
  hashes the RAW dict bytes, so a decomposed source key (kok ड़ = ड+़ -> r.) and the
  distinct precomposed entry (U+095C -> r-) must stay separate — NFC-collapsing the keys
  let the precomposed r- shadow the decomposed r. in a shared bucket. So the exact source
  form of the lookup word selects the exact entry:
    kok  ड+़  (U+0921 U+093C) -> r.ˈə   (retroflex flap)
    kok  ड़    (U+095C)        -> r̩ˈə   (syllabic, the r- entry)

- hi रेलगाड़ी / बैलगाड़ी: the dict KEY is stored decomposed (ड+़), but hi's `.replace`
  composes the runtime word's nukta to U+095C. espeak hashes raw bytes, so the composed
  word MISSES the decomposed key and falls through to the RULES (गाड़ी -> ...ɡˈaːr.i with a
  retroflex flap and a secondary-stressed long first vowel). The dict lookup must NOT
  NFC-bridge the composed word back onto the decomposed key.

- hi य़ुघ्दविराम: the dict value's leading `j:` is a clause-initial geminate GLIDE (palatal
  semivowel, a phLIQUID with a vocalic starttype rendered via its formant program). espeak's
  phonemelist doubling is skipped at the clause boundary (`j > 0` guard), so it keeps its
  length mark and renders jː — not the doubled jj a mid-clause geminate glide would take.

- ADVERSARIAL ar عمرو: a clause-initial geminate voiced FRICATIVE (ʕ, `A:`) still DOUBLES
  (ʕʕ) — the glide-only length guard must not suppress a true fricative/nasal/liquid
  gemination, whether clause-initial or not.
"""
import unicodedata

import pytest

from espyak.api import G2P

CASES = [
    # (lang, word, expected-IPA)
    ("kok", "ड़", "r.ˈə"),          # decomposed DDA + NUKTA -> retroflex flap
    ("kok", "ड़", "r̩ˈə"),                 # precomposed RRA -> syllabic (r- entry)
    ("bpy", "ড়", "r.ˈo"),                 # Bengali RRA -> retroflex flap
    ("hi", "रेलगाड़ी", "ɾˌeːlɡˈaːr.i"),        # composed word -> rules (retroflex flap)
    ("hi", "बैलगाड़ी", "bˌɛːlɡˈaːr.i"),
    ("hi", "य़ुघ्दविराम", "jːudhhʋˈiɾˈaːm"),    # clause-initial geminate glide -> jː
    ("ar", "عمرو", "ʕʕmr"),                   # adversarial: fricative gemination still doubles
]


def _nfc(s):
    return unicodedata.normalize("NFC", s)


@pytest.mark.parametrize("lang,word,expected", CASES)
def test_brahmic_nukta_gemination(oracle, lang, word, expected):
    got = _nfc(G2P(lang, force_compat=True).phonemize(word))
    assert got == expected
    assert got == _nfc(oracle(word, lang, "ipa"))
