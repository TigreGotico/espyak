"""Stress placement around the Indic word-final inherent schwa and the Malay vowel-hiatus
break, verified byte-exact against the espeak-ng oracle.

* Indic inherent schwa (ph V): a language whose V phoneme deletes the word-final schwa
  (`IF thisPh(isWordEnd) ... THEN ChangePhoneme(NULL)`, e.g. bn/hi/kn) drops it BEFORE the
  word's stress is placed, so GetVowelStress never counts it as the final syllable. A
  STRESSPOSN_1L word therefore lands its clause tonic on the last REAL vowel, not on the
  schwa that is about to vanish (bn করছিলাম -> kˌɔɾɔtʃʰˈilam). A word whose only real vowels
  precede the schwa still takes syllable 1 (bn আমার -> ˈamaɾ). Languages whose V program has
  NO word-final deletion PRONOUNCE the schwa and keep it counted (ta பூத -> bˈuːdʌ, pa).

* Malay vowel hiatus: the id-table vowels insert a `_|` break between adjacent vowels
  (InsertPhoneme(_|)). Inserting the break before the tonic vowel loses that vowel's primary,
  which is promoted back onto the nearest preceding vowel that already carries a stress — so an
  explicit secondary is raised to the single primary (ms bersesuaian -> bərsˈəsuaɪan) rather
  than leaving a stray secondary beside a fresh primary. With no preceding stressed vowel the
  primary falls on the immediately preceding syllable (ms kesesuaian -> kəsəsˈuaɪan; the spelled
  acronyms klci/cimb keep their letter-name primaries).
"""
import unicodedata

import pytest

from espyak.api import G2P


CASES = [
    # bn: word-final inherent schwa deleted before stress -> tonic on the last real vowel
    ("bn", "করছিলাম", "kˌɔɾɔtʃʰˈilam"),
    # bn: no real vowel after the schwa -> ordinary 1L syllable 1
    ("bn", "আমার", "ˈamaɾ"),
    # ta/pa: V has no word-final deletion, schwa is pronounced and stays counted
    ("ta", "பூத", "bˈuːdʌ"),
    ("ta", "பரத", "bˈʌɹʌdʌ"),
    ("pa", "ਅ", "ˈɛrʌ"),
    # ms: hiatus break loses the post-break tonic; an explicit secondary is promoted to primary
    ("ms", "bersesuaian", "bərsˈəsuaɪan"),
    # ms: no preceding stress -> primary on the syllable just before the break
    ("ms", "kesesuaian", "kəsəsˈuaɪan"),
    ("ms", "buaian", "bˈuaɪan"),
    ("ms", "suai", "sˈuaɪ"),
    # ms: spelled acronyms keep their letter-name primaries across the inserted breaks
    ("ms", "klci", "kˌeəlsˈiːaɪ"),
    ("ms", "cimb", "sˌiːaɪˌɛmbˈiː"),
]


@pytest.mark.parametrize("lang,word,expected", CASES)
def test_matches_oracle(oracle, lang, word, expected):
    got = unicodedata.normalize("NFC", G2P(lang).phonemize(word))
    assert got == expected
    assert unicodedata.normalize("NFC", oracle(word, lang, "ipa")) == expected
