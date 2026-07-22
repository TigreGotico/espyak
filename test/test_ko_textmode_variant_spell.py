"""Korean $text respellings that carry a '/' variant marker are spelled letter by letter.

A Korean sandhi entry in ko_list may give two pronunciation variants separated by '/'
(곗날 -> 곈ː날/겐ː날). espeak re-injects a $text value as ONE whitespace-delimited word
(translate.c:150-193 splits on whitespace only, so the '/' stays embedded). Translating that
word, the '/' matches the en `/ slaS $max3` dictionary entry mid-word, which flags the whole
word FLAG_SPELLWORD. espeak then re-speaks the ORIGINAL source word letter by letter
(translate.c:1608-1617) — not the replacement — decomposing each Hangul syllable into jamo:
a consonant-initial jamo is spoken by its dictionary letter name (ᄀ -> gij'@q), every other
jamo by its rule sound. Because the ORIGINAL word is spelled, its final ㅅ yields the
unreleased t- that the replacement's final ㄴ never would.

Verified against espeak-ng 1.52.0 (`espeak-ng -q --ipa -v ko`).
"""
from espyak.api import G2P

# (original word, expected IPA) — the three '/'-variant entries in ko_list.
SLASH_VARIANT_CASES = [
    ("곗날", "ɡijˈʌq jˈe t- niˈɯn ˈɐ ɫ"),        # 곈ː날/겐ː날 ; final ㅅ of 곗 -> t-
    ("툇마루", "thiˈɯt- wˈe t- miˈɯm ˈɐ ɾiˈɯrɹ ˈu"),  # 퇸ː마루/퉨ː마루
    ("가ᅬᆺᅵᆯ", "ɡijˈʌq ˈɐ wˈe t- ˈi ɫ"),          # 가ᅬᆫ닐/가ᅰᆫ닐 (mixed-jamo original)
]

# A $text respelling WITHOUT a '/' is pronounceable and renders as ordinary syllables — the
# spell-through must not fire for these (adversarial guard against over-triggering).
NON_SLASH_SYLLABLE_CASES = [
    ("고랫재", "ɡˌoɾɛd-tɕˈɛ"),   # 고랟째
    ("제삿날", "tɕesˈɐnnɐɫ"),    # 제ː삳날
    ("훗날", "hˈunnɐɫ"),         # 훈ː날
    ("곳간", "ɡˈod-q-ɐn"),       # 곧깐
]


def test_ko_slash_variant_is_spelled_from_original_word():
    g = G2P("ko")
    for word, expected in SLASH_VARIANT_CASES:
        assert g.phonemize(word) == expected, word


def test_ko_non_slash_respelling_stays_syllabic():
    g = G2P("ko")
    for word, expected in NON_SLASH_SYLLABLE_CASES:
        assert g.phonemize(word) == expected, word
