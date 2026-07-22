"""The phonSYLLABIC marker `-` (phsource `phoneme -`) counts as a syllable slot.

espeak's GetVowelStress (dictionary.c:876-879) counts the `-` virtual phoneme as an
extra syllable and its output loop (dictionary.c:1391, `*p == phonSYLLABIC`) places that
syllable's stress before the consonant it follows. Two consequences must both hold:

* A bare `-` after a vowel (ar/fa spelled letter names) inserts a phantom slot that shifts
  the following real vowels' stress one place to the right — which is how espeak lands the
  secondary (ar ى -> mˌaqs̪, fa ة -> ...aʔnˌis).
* A `-` after a consonant (a genuine syllabic consonant, de -tʃn̩) keeps `v` aligned with
  the vowel_stress array, so nothing downstream desyncs.
"""
import pytest

from espyak.api import G2P

# byte-exact against espeak-ng 1.52; verified with `espeak-ng -q --ipa -v <lang>` on stdin.
CASES = [
    # bare `-` after a vowel: the phantom slot shifts the secondary one syllable right
    ("ar", "ى", "ʔˈalif mˌaqs̪-ˈuːrah"),
    ("fa", "ة", "tˈɑjetaʔnˌis"),
    # genuine syllabic consonant (`-` after a consonant): no desync, stays byte-exact
    ("de", "bratschen", "bɾˈaːtʃn̩"),
    ("eo", "Km", "kˈilomˈet-ɾoɪ"),
    ("sw", "n", "ˈen"),
    # onset cluster without a bare `-` is unaffected (guards against over-counting @-)
    ("la", "probo", "prˈɔbɔ"),
]


# A bare `-` after a vowel inserts a phantom vowel_stress slot that the SetWordStress output
# loop never reads (the preceding vowel already advanced `v`), orphaning any stress marked on
# a later syllable at that shifted index. espeak keeps the orphan and its clause nucleus falls
# back to the last OUTPUT-reachable max-stress syllable, so the tonic must be placed in the
# output-reachable range, not the raw vowel_count range. da barrikade (rules -> `bA-?ik'&:D@-`,
# the `A-` = vowel A + phonSYLLABIC `-`): the explicit primary on `&:` is orphaned past the
# reachable range, so the tonic lands on the first syllable (bˈɑ), not left unstressed.
VOWEL_DASH_TONIC = [
    ("da", "barrikade", "bˈɑʔikaaðə"),
]


@pytest.mark.parametrize("lang,word,expected", VOWEL_DASH_TONIC)
def test_vowel_dash_tonic_orphan(oracle, lang, word, expected):
    assert G2P(lang, force_compat=True).phonemize(word) == expected
    assert G2P(lang).phonemize(word) == expected
    assert expected == oracle(word, lang, "ipa")


@pytest.mark.parametrize("lang,word,expected", CASES)
def test_syllabic_marker_stress(oracle, lang, word, expected):
    assert G2P(lang, force_compat=True).phonemize(word) == expected
    assert expected == oracle(word, lang, "ipa")
