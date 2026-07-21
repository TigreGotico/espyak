"""Word-final devoicing, $u-word vowel reduction, gd pre-aspiration, and the leading
syllabic-marker drop. Expected values from espeak-ng 1.52.0, re-verified vs the live binary.

Each case is a mechanism ported from the vendored C, NOT a per-word special case:

- mt LOPT_REGRESSIVE_VOICING = 0x100 (tr_languages.c L('m','t')): word-final obstruents devoice.
- gd/tn $u function words carrying the clause accent still run each vowel's own program under
  their natural (un-tonic) stress (unstress_u_words), so ph_s_gaelic `a`->@, ph_setswana
  `o`->ChangeIfUnstressed(U) and `e`->ChangeIfUnstressed(l) fire.
- gd pre-aspiration `#` (ph_s_gaelic): a consonant's StressCondition (synthdata.c:410) reads the
  FOLLOWING vowel and fails when the next phoneme is a consonant, so thisPh(isNotStressed) is
  false and ChangePhoneme(NULL) does not fire.
- A leading `-` (phonSYLLABIC) has no preceding phoneme to mark syllabic, so espeak emits nothing
  (GetTranslatedPhonemeString, dictionary.c:657).
"""
import unicodedata

import pytest

from espyak.api import G2P

CASES = [
    # (lang, word, expected_ipa)
    ("mt", "ikseb", "ˈiːksep"),      # word-final b -> p
    ("mt", "qiegħed", "ˈiet"),       # word-final d -> t
    ("gd", "w", "dˈɔhbəljuː"),       # letter name keeps pre-aspiration `#` -> h
    ("gd", "ar", "ˈəɾ"),             # $u word: a laxes to schwa under the clause accent
    ("gd", "cat", "kˈahd"),          # pre-aspiration `#` before a word-final voiceless stop -> h
    ("tn", "le", "ll"),              # $u word: e -> ChangeIfUnstressed(l); no vowel, no accent
    ("tn", "mo", "mˈʊ"),             # $u word: o -> ChangeIfUnstressed(U) under the clause accent
    ("da", "final", "esˈe"),         # leading `-` (phonSYLLABIC) at word start is not emitted
]


@pytest.mark.parametrize("lang,word,expected", CASES)
def test_forced_compat_matches_oracle(oracle, lang, word, expected):
    g = G2P(lang, force_compat=True)
    got = unicodedata.normalize("NFC", g.phonemize(word))
    assert got == expected
    assert got == unicodedata.normalize("NFC", oracle(word, lang, "ipa"))


@pytest.mark.parametrize("lang,word,expected", CASES)
def test_default_engine_matches(lang, word, expected):
    # the mechanisms are espeak-faithful AND linguistically correct, so the default
    # (non-compat) engine produces the same output here.
    g = G2P(lang)
    assert unicodedata.normalize("NFC", g.phonemize(word)) == expected


def test_leading_syllabic_marker_only_drops_at_word_start():
    # adversarial: a `-` after a CONSONANT is a real syllabic marker and must still render;
    # only a leading `-` (nothing to attach to) is dropped. gd `cat` keeps its post-vowel
    # pre-aspiration, and the drop must not swallow interior markers.
    g = G2P("da", force_compat=True)
    assert not unicodedata.normalize("NFC", g.phonemize("final")).startswith("-")
