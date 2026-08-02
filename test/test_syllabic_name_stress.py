"""Syllabic-consonant marker (`-`, phonSYLLABIC) in a dictionary phoneme string.

espeak-ng's `-` phoneme marks the PRECEDING phoneme as a syllabic consonant, so it heads its
own syllable and takes a vowel_stress slot (GetVowelStress, dictionary.c:868). When the `-`
follows a word break (`||`), no real consonant precedes it, so the planted syllable slot is
never consumed by the output loop — every following vowel then reads a vowel_stress index one
earlier, shifting the primary onto the final syllable.

Italian spells some foreign letters with this device: й = "i breve" (`'I||-b@-*'eve`) and
ъ = "jer dura" (`jEr||-d'uRa`). Both reassign the second word's dict-explicit penult stress to
its final syllable (brˈeve -> brevˈe, dˈura -> dʊrˈa, the now-unstressed `u` laxing to ʊ).
The expected IPA is captured from espeak-ng 1.52.0 and re-verified against the live oracle.
"""
import pytest

from espyak.api import G2P


@pytest.fixture(scope="module")
def it():
    return G2P("it")


# (letter, expected_ipa) — MATCHES espeak-ng 1.52.0 exactly. The primary sits on the FINAL
# syllable of the trailing name word, not the dict entry's explicit penult mark.
NAME_STRESS = [
    ("й", "ɪ brevˈe"),
    ("ъ", "jer dʊrˈa"),
]


@pytest.mark.parametrize("letter,ipa", NAME_STRESS)
def test_name_stress(it, letter, ipa):
    assert it.phonemize(letter) == ipa


@pytest.mark.parametrize("letter,ipa", NAME_STRESS)
def test_name_stress_matches_oracle(oracle, it, letter, ipa):
    assert it.phonemize(letter) == oracle(letter, "it", "ipa")
    assert it.phonemize(letter) == ipa


def test_final_not_penult(it):
    # the shift is the whole point: the primary must NOT stay on the dict's explicit penult
    # mark (brˈeve / dˈura), and the destressed `u` of "dura" must lax to ʊ.
    assert it.phonemize("й") != "ɪ brˈeve"
    assert it.phonemize("ъ") != "jer dˈura"
    assert "dʊr" in it.phonemize("ъ")
