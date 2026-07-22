"""Cardinal-number translation vs the espeak-ng oracle (English core)."""
import unicodedata

import pytest
from espyak.api import G2P


def _nfc(s):
    return unicodedata.normalize("NFC", s)

# cardinal core (NUM_HUNDRED_AND). NUM_THOUSAND_AND ("one million and five"), ordinals,
# decimals/years and the per-language NUM_* variants are not yet modelled.
CASES = ["0", "5", "7", "21", "42", "100", "105", "999",
         "1000", "1234", "1000000", "2000000", "1005000", "13", "19", "80",
         "3.14", "0.5", "2.0", "42.5", "100.25",
         "1st", "2nd", "3rd", "4th", "5th", "8th", "12th", "20th", "21st",
         "30th", "42nd", "100th", "1000th",
         "1005", "2034", "1234567"]  # thousand-and


@pytest.fixture(scope="module")
def en():
    return G2P("en")


@pytest.mark.parametrize("num", CASES)
def test_cardinal_matches_oracle(en, oracle, num):
    assert en.phonemize(num) == oracle(num, "en")


# German: NUM_SWAP_TENS (units-and-tens) + the _Na "ein"-before-magnitude form
DE_CASES = ["5", "21", "35", "99", "100", "105", "1000", "1234"]


@pytest.fixture(scope="module")
def de():
    return G2P("de")


@pytest.mark.parametrize("num", DE_CASES)
def test_german_cardinal_matches_oracle(de, oracle, num):
    assert de.phonemize(num) == oracle(num, "de")


# Spanish: lexicalised hundreds (cien/ciento/doscientos), exact tens (veinte), "mil".
# Compound tens+units (21, 31) need NUM_SINGLE_STRESS reassignment — not yet modelled.
ES_CASES = ["5", "20", "30", "100", "105", "200", "300", "500", "1000"]


@pytest.fixture(scope="module")
def es():
    return G2P("es")


@pytest.mark.parametrize("num", ES_CASES)
def test_spanish_cardinal_matches_oracle(es, oracle, num):
    assert es.phonemize(num) == oracle(num, "es")


# Decimal-fraction reading is per-language (the NUM_DFRACTION_* bits). Digit-by-digit languages
# (nl/de/sv/da/el/an, and ru with its "и"…"десятых" frame) spell each fraction digit; the
# whole-cardinal languages (fr/es/it/pt/ro/pl/cs/fi/tr/ca) read the fraction as one number when it
# is short enough. These probes are byte-exact against the oracle across both readings.
DFRACTION_CASES = [
    ("sv", "3,14"), ("sv", "0,5"), ("sv", "12,345"), ("sv", "0,05"), ("sv", "100,25"),
    ("da", "3,14"), ("da", "0,5"), ("da", "12,345"), ("da", "0,05"), ("da", "7,7"),
    ("an", "3,14"), ("an", "0,5"), ("an", "12,345"), ("an", "0,05"), ("an", "100,25"),
    ("ru", "3,14"), ("ru", "0,5"), ("ru", "12,345"), ("ru", "0,05"), ("ru", "0,123"),
    ("it", "3,14"), ("it", "0,5"), ("it", "12,345"), ("it", "0,05"), ("it", "2,0"),
    ("ca", "3,14"), ("ca", "0,5"), ("ca", "0,05"), ("ca", "100,25"), ("ca", "0,123"),
    ("ro", "3,14"), ("ro", "0,5"), ("ro", "0,05"), ("ro", "2,0"), ("ro", "7,7"),
    ("el", "0,5"), ("el", "12,345"), ("el", "0,05"), ("el", "2,0"), ("el", "0,123"),
]


@pytest.mark.parametrize("lang,num", DFRACTION_CASES)
def test_decimal_fraction_matches_oracle(oracle, lang, num):
    assert G2P(lang).phonemize(num) == oracle(num, lang)


# A multi-word number is ONE stress domain: espeak builds the whole phrase into a single phoneme
# buffer and runs SetWordStress once over it, so the language's stress flags reconcile the
# per-fragment primaries across the word breaks. fr/es keep only the tonic primary and diminish the
# earlier number words (fr trois·virgule -> unmarked; es demotes the decimal-separator word to
# secondary), while nl (S_FIRST_PRIMARY) keeps the FIRST primary and drops the rest to secondary.
# de/it/ru/ro carry every fragment's primary (their flags force no reduction). pl/cs must keep the
# space after the decimal-separator word (przecinek/čárka), whose pause-plus-word-break must not
# collapse. Byte-exact against the oracle.
PHRASE_STRESS_CASES = [
    ("fr", "3,14"), ("fr", "3,05"), ("fr", "9,81"),
    ("es", "3,14"), ("es", "2,5"),
    ("nl", "3,14"), ("nl", "2,5"),
    ("pl", "3,14"), ("pl", "3,05"), ("pl", "9,81"),
    ("cs", "3,14"), ("cs", "9,5"),
    ("de", "3,14"), ("it", "3,14"), ("ru", "3,14"), ("ro", "3,14"),
]


@pytest.mark.parametrize("lang,num", PHRASE_STRESS_CASES)
def test_number_phrase_stress_matches_oracle(oracle, lang, num):
    assert G2P(lang).phonemize(num) == oracle(num, lang)


# Welsh counts in tens: 20 = "dau ddeg", 42 = "pedwar deg dau" (tens fragment before the unit),
# and the teens are "deg" + unit with no dedicated _10.._19 entries. 100 drops the leading "un".
CY_CARDINAL_CASES = ["1", "2", "9", "10", "11", "12", "15", "16", "18", "19", "100",
                     # the tens 20-99 embed "deg" (10) as a secondary-stressed component; its
                     # explicit long vowel eː must survive (ðˌeːɡ, not the reduced ðˌɛɡ) because
                     # the number fragments come from the `_list` dictionary (SFLAG_DICTIONARY),
                     # which exempts them from the ChangeIfNotStressed(E) reduction.
                     "20", "22", "23", "30", "40", "42", "50", "55", "60", "66",
                     "70", "77", "80", "88", "90", "99"]


@pytest.fixture(scope="module")
def cy():
    return G2P("cy")


@pytest.mark.parametrize("num", CY_CARDINAL_CASES)
def test_welsh_cardinal_matches_oracle(cy, oracle, num):
    assert cy.phonemize(num) == oracle(num, "cy")


@pytest.mark.parametrize("num,unit_core", [("42", "aɨ"), ("55", "øm"), ("23", "iː")])
def test_welsh_tens_precede_units(cy, num, unit_core):
    # The tens word ("pedwar deg", "dau ddeg", …) comes before the unit — regression guard against
    # the units-first ordering.
    out = cy.phonemize(num)
    assert "ðˌ" in out  # the "deg" tens marker is present
    assert out.index("ðˌ") < out.rindex(unit_core)


@pytest.mark.parametrize("num", ["20", "42", "60", "99"])
def test_welsh_tens_component_keeps_long_vowel(cy, num):
    # The tens "deg" (10) is only secondary-stressed inside the compound, but its long eː must
    # not be reduced to ɛ: number fragments are dictionary-sourced, so ChangeIfNotStressed(E)
    # does not fire on them (StressCondition control&1 / SFLAG_DICTIONARY).
    out = cy.phonemize(num)
    assert "ðˌeːɡ" in out
    assert "ðˌɛɡ" not in out


@pytest.mark.parametrize("word,expected", [
    # `e (d`->e: must win over the `e (CC` / `e (C` consonant-group rules — that only happens
    # once SetLetterVowel(w) removes `w` from the consonant group, so `pedwar` (e+d+w) matches
    # `e (d` not `e (CC`. Regression guard for the long-vowel rule-scoring fix.
    ("pedwar", "pˈeːdwar"),
    ("deg", "dˈeːɡ"),
    ("peth", "pˈeːθ"),
    ("pedwar deg dau", "pˈeːdwar dˈeːɡ dˈaɨ"),
])
def test_welsh_word_long_vowel(cy, oracle, word, expected):
    assert cy.phonemize(word) == expected
    assert cy.phonemize(word) == oracle(word, "cy")


@pytest.mark.parametrize("word", ["wrth", "hwn", "hwnnw", "shwd", "rhwng"])
def test_welsh_w_words_pronounced_not_spelled(cy, oracle, word):
    # With `w` a vowel (SetLetterVowel), a w-initial/w-medial word still has a vowel nucleus and
    # must be pronounced, not spelled letter-by-letter. Guards the pronounceability check against
    # forgetting that set_letter_vowel letters count as vowels.
    out = cy.phonemize(word)
    assert out == oracle(word, "cy")
    # a spelled-out word produces one stress mark per letter name; a pronounced one has a single
    # primary and no spurious per-letter secondaries.
    assert out.count("ˈ") == 1 and "ˌ" not in out


CY_CIRCUMFLEX_WORDS = [
    ("tŷ", "tˈɨː"),
    ("dŵr", "dˈuːr"),
    ("tŷ mawr", "tˈɨː mˈaʊr"),
]


@pytest.mark.parametrize("word,ipa", CY_CIRCUMFLEX_WORDS)
def test_cy_circumflex_vowels_pronounced(word, ipa):
    assert G2P("cy", force_compat=True).phonemize(word) == ipa


# Portuguese: teens, tens and hundreds live in `?N`-gated `_list` entries whose condition prefix
# is glued to the key ("?1_14", "?1_4X", "?1_2C"). The voice's `dictrules 1` sets condition 1,
# so those entries must load AND be selected by the number path (which builds its own lookup
# context). The tens/units connective is NUM_AND_UNITS ("vinte e um"); the thousands use the
# combined `_1M1` "mil" and `_1M2` "um milhão" forms.
PT_CARDINAL_EXACT = {
    "13": "tɹˈezɨ", "14": "kɐtˈorzɨ", "15": "kˈiŋzɨ", "40": "kwɐɾˈeŋtɐ",
    "100": "sˈeɪŋ", "21": "vˈiŋtɨiˈum", "24": "vˈiŋtɨikwˈatɹu",
    "1000": "mˈil", "2000": "dˈoɪʒ mˈil", "1005": "mˈil i sˈiŋku",
    # "um milhão": ũ/ɐ̃/ʊ̃ are base letter + U+0303 combining tilde (espeak's un-normalised form).
    "1000000": "ˈũmiljˈɐ̃ʊ̃",
}


@pytest.fixture(scope="module")
def pt():
    return G2P("pt")


@pytest.mark.parametrize("num,expected", sorted(PT_CARDINAL_EXACT.items()))
def test_portuguese_cardinal_exact(pt, num, expected):
    assert _nfc(pt.phonemize(num)) == _nfc(expected)


@pytest.mark.parametrize("num,expected", sorted(PT_CARDINAL_EXACT.items()))
def test_portuguese_cardinal_matches_oracle(pt, oracle, num, expected):
    assert pt.phonemize(num) == oracle(num, "pt")


@pytest.mark.parametrize("num", ["13", "14", "16", "17", "18", "19", "40", "60", "70", "90"])
def test_portuguese_conditional_number_entries_load(pt, num):
    # These cardinals only exist as condition-gated entries ("?1_14" etc.); before the glued
    # condition prefix parsed correctly they yielded an empty string.
    assert pt.phonemize(num) != ""


def test_portuguese_and_units_connective(pt):
    # NUM_AND_UNITS inserts the "e" (rendered "i") between tens and units: vinte + i + um.
    assert "tɨiˈum" in pt.phonemize("21")  # vˈiŋtɨiˈum
    assert "tɨiˈum" not in pt.phonemize("20")  # plain "vinte" has no connective/unit


def test_portuguese_thousand_omits_um(pt):
    # 1000 is "mil", never "um mil": the combined _1M1 form supersedes value+magnitude.
    out = pt.phonemize("1000")
    assert out == "mˈil"
    assert "um" not in out


def test_portuguese_million_singular_form(pt):
    # 1_000_000 uses the singular _1M2 "um milhão", not the plural _0M2 "milhões".
    assert _nfc(pt.phonemize("1000000")) == _nfc("ˈũmiljˈɐ̃ʊ̃")
    assert "õ" not in _nfc(pt.phonemize("1000000"))  # not the plural "milhões"



# Hungarian omits the leading "egy" before both hundred and thousand (NUM_OMIT_1_HUNDRED |
# NUM_OMIT_1_THOUSAND): 100 is "száz" not "egyszáz", 1000 is "ezer" not "egyezer".
HU_CARDINAL_CASES = ["100", "105", "200", "999", "1000", "1100", "1234", "20", "21", "3,14"]


@pytest.mark.parametrize("num", HU_CARDINAL_CASES)
def test_hungarian_cardinal_matches_oracle(oracle, num):
    assert _nfc(G2P("hu").phonemize(num)) == _nfc(oracle(num, "hu"))


# French numbers are vigesimal above 60 (70 = soixante-dix, 90 = quatre-vingt-dix) and have
# lexicalised direct entries for the whole 20-29 row (vingt-et-un `_21`), which win over
# tens+units decomposition.
FR_CARDINAL_CASES = ["20", "21", "22", "29", "31", "61", "70", "71", "73", "79",
                     "80", "81", "90", "91", "95", "99", "121", "171"]


@pytest.mark.parametrize("num", FR_CARDINAL_CASES)
def test_french_cardinal_matches_oracle(oracle, num):
    assert G2P("fr").phonemize(num) == oracle(num, "fr")
# Per-language numbers-flag audit against tr_languages.c (langopts.numbers). Each case is
# byte-exact against the oracle and exercises a specific mechanism:
#   nl/da  NUM_SWAP_TENS + NUM_OMIT_1_HUNDRED/THOUSAND (+ NUM_HUNDRED_AND for da)
#   sv/el/tr NUM_SINGLE_STRESS (one primary in a compound)
#   ru     NUM_OMIT_1_HUNDRED ("сто" not "один сто")
#   ro/pt  NUM_AND_UNITS (Romanian "și", Portuguese "e" between tens and units)
#   it     NUM_SINGLE_VOWEL (settanta+uno -> settantuno)
#   ca     NUM_SINGLE_STRESS + NUM_AND_UNITS + NUM_OMIT_1_HUNDRED/THOUSAND (es block)
#   fr     NUM_VIGESIMAL (70 = soixante-dix, 90 = quatre-vingt-dix) + NUM_SINGLE_STRESS
NUMBERS_FLAG_CASES = [
    ("nl", "20"), ("nl", "70"), ("nl", "100"), ("nl", "1000"),
    ("da", "21"), ("da", "42"), ("da", "71"), ("da", "100"), ("da", "105"),
    ("sv", "21"), ("sv", "42"), ("sv", "71"), ("sv", "95"),
    ("tr", "40"), ("tr", "44"), ("tr", "66"),
    ("el", "21"), ("el", "42"),
    ("ru", "100"), ("ru", "105"), ("ru", "200"),
    ("ro", "31"), ("ro", "35"), ("ro", "55"), ("ro", "61"),
    ("pt", "32"), ("pt", "33"), ("pt", "100"),
    ("it", "28"), ("it", "31"), ("it", "71"), ("it", "80"), ("it", "95"),
    ("ca", "21"), ("ca", "42"), ("ca", "70"), ("ca", "100"),
    ("fr", "21"), ("fr", "70"), ("fr", "71"), ("fr", "80"), ("fr", "90"), ("fr", "95"),
]


@pytest.mark.parametrize("lang,num", NUMBERS_FLAG_CASES)
def test_numbers_flags_match_oracle(oracle, lang, num):
    assert G2P(lang).phonemize(num) == oracle(num, lang)


# The non-decimal separator groups thousands only when each following group has exactly three
# digits (translate.c:1517); a non-binding separator splits the token into separate numbers.
GROUPED_NUMBER_CASES = [
    ("en", "1,000"), ("en", "12,345"), ("en", "1,000,000"), ("en", "3,14"),
    ("en", "5,5"), ("en", "0,5"), ("en", "1,23,456"), ("en", "12,345,67"),
    ("nl", "1.000"), ("nl", "3.14"), ("de", "1.000.000"), ("cy", "3,14"),
]


@pytest.mark.parametrize("lang,num", GROUPED_NUMBER_CASES)
def test_grouped_numbers_match_oracle(oracle, lang, num):
    assert _nfc(G2P(lang).phonemize(num)) == _nfc(oracle(num, lang))


# --- Render-layer number bugs (byte-verified against espeak-ng 1.52) --------------------------
#
# Timeless expected values (hard-coded, oracle-independent) for three render-layer fixes:
#
#  1. ru compound-number voicing: the regressive-voicing pass must NOT cross the boundary between
#     citation number fragments — сорок (k) + два keeps its word-final k (was voiced to ɡ). Gated
#     on the ru-only `number_skip_voicing` flag (Translator_Russian reads assembled number
#     fragments as separate words; cs/pl, same 0x03 regression, DO cross-voice and are unaffected).
#     The a/ʌ pair (двадцать|два -> …tsatʲ…) is the ru `V` phoneme resolving `nextVowel(isMaxStress)`
#     — fixed by evaluating nextVowel/prevVowel features at the scanned vowel and not crossing a
#     word boundary (synthdata.c:532-546).
RU_VOICING_CASES = [
    ("42", "sˈorɔkdvˈɑ"), ("49", "sˈorɔkdʲˈevɪtʲ"),
    ("22", "dvˈɑttsatʲdvˈɑ"), ("29", "dvˈɑttsatʲdʲˈevɪtʲ"),
    ("52", "pʲʌdʲdʲɪsʲˈjatdvˈɑ"), ("72", "sʲˈemdʲɛsʲatdvˈɑ"),
    ("999", "dʲɪvʲitsˈot dʲivʲɪnˈostɔdʲˈevɪtʲ"),
    ("21", "dvˈɑttsʌtʲʌdʲˈin"),   # един starts on a vowel -> V stays ʌ (control: no over-fire)
    ("145", "stˈo sˈorɔkpʲˈɑtʲ"),
]


@pytest.mark.parametrize("num,expected", RU_VOICING_CASES)
def test_ru_number_voicing(num, expected):
    assert _nfc(G2P("ru").phonemize(num)) == expected


#  2. tr vowel harmony at render (nextVowel/prevVowel feature-context fix): 100 -> jˈyz not jˈøz.
TR_HARMONY_CASES = [
    ("100", "jˈyz"), ("90", "doksˈan"), ("40", "kˈɯrk"), ("60", "aɫtmˈɯʃ"),
    ("10", "ˈon"), ("70", "jetmˈiʃ"),
]


@pytest.mark.parametrize("num,expected", TR_HARMONY_CASES)
def test_tr_number_vowel_harmony(num, expected):
    assert _nfc(G2P("tr").phonemize(num)) == expected


#  3. nl grouped-number phrase breaks: a "long" magnitude count (>= 10, or millions+) inserts a
#     phrase-break pause (phonPAUSE_NOLINK) before the following group. The pause blocks the
#     ph_dutch t/d cross-word degemination (duizend keeps its final t: dˌœyzɛnt drˈi, not
#     dˌœyzɛn trˌi) and gives that group its own primary stress. Short thousands counts (2345)
#     start no new phrase, and a plain decimal (3,14) and cross-word sentence degemination stay put.
NL_PHRASE_CASES = [
    ("12.345", "tʋˈaːlf dˌœyzɛnt drˈihˌɔndərt vˌɛɪfɛnfˌɪːrtəx"),
    ("12345", "tʋˈaːlf dˌœyzɛnt drˈihˌɔndərt vˌɛɪfɛnfˌɪːrtəx"),
    ("123.456", "hˈɔndər trˌiɛntʋˌɪntəx dˌœyzɛnt vˈirhˌɔndərt zˌɛsɛnvˌɛɪftəx"),
    ("1.234.567", "ˈeːn mˌiljun tʋˈeːhˌɔndərt vˌirɛndˌɛrtəx dˌœyzɛnt vˈɛɪfhˌɔndərt zˌeːvənɛnzˌɛstəx"),
    ("2345", "tʋˈeː dˌœyzɛn trˌihˌɔndərt vˌɛɪfɛnfˌɪːrtəx"),   # short count: no break, degeminates
    ("1234", "dˈœyzɛn tʋˌeːhˌɔndərt vˌirɛndˌɛrtəx"),
    ("1.000", "dˈœyzɛnt"),
    ("3,14", "drˈi kˌɔmaː ˌeːn vˌir"),   # plain decimal must stay byte-exact
]


@pytest.mark.parametrize("num,expected", NL_PHRASE_CASES)
def test_nl_grouped_number_phrase_breaks(num, expected):
    assert _nfc(G2P("nl").phonemize(num)) == expected


def test_nl_sentence_degemination_preserved():
    # cross-word sentence degemination must remain (kost twintig -> kˈɔs tʋˈɪntəx)
    assert _nfc(G2P("nl").phonemize("kost twintig")) == "kˈɔs tʋˈɪntəx"


# --- Indian lakh/crore grouping (translate.c break_numbers = BREAK_LAKH_*) -----------------
# Above the first thousand group the digits group in PAIRS, so the magnitude words are lakh
# (1,00,000) and crore (1,00,00,000) — never "million". A wrong grouping is off by a factor
# of ten with the RIGHT magnitude word, so each case pins the count as well as the word.
HI_LAKH_CASES = [
    ("1000", "ˈeːk hˈʌɟaːɾ"),
    ("10000", "dˈʌs hˈʌɟaːɾ"),
    ("100000", "ˈeːk lˈaːkʰ"),
    ("1000000", "dˈʌs lˈaːkʰ"),
    ("2000000", "bˈiːs lˈaːkʰ"),
    ("10000000", "ˈeːk kəɾˈoːr."),
    ("100000000", "dˈʌs kəɾˈoːr."),
    ("12345678", "ˈeːk kəɾˈoːr. tˈeːis lˈaːkʰ paɪntˈaːlis hˈʌɟaːɾ cʰˈʌhsˈɔː ʌthˈʌtːəɾ"),
]


@pytest.mark.parametrize("num,expected", HI_LAKH_CASES)
def test_hi_lakh_crore_grouping(num, expected):
    assert _nfc(G2P("hi", force_compat=True).phonemize(num).strip()) == expected


# --- Slavic magnitude inflection (numbers.c M_Variant + the feminine count) ----------------
# The magnitude word inflects by the count it follows (1 / 2-4 / 5+), teens always taking the
# 5+ form, and in ru the count before "thousand" is feminine ("одна/две", not "один/два").
RU_VAR_CASES = [
    ("1000", "ʌdnˈɑ tˈysʲitʃʲʌ"),
    ("2000", "dvʲˈe tˈysʲitʃʲi"),
    ("5000", "pʲˈɑtʲ tˈysʲitʃʲ"),
    ("11000", "ɔdʲˈinnʌttsʌtʲ tˈysʲitʃʲ"),      # teen count -> the 5+ form
    ("21000", "dvˈɑttsʌtʲʌdnˈɑ tˈysʲitʃʲʌ"),    # 21 ends in 1 -> the "1" form again
    ("1000000", "ʌdʲˈin mʲˌɪɭʲɪˈon"),           # millions are NOT feminine
    ("2000000", "dvˈɑ mʲˌɪɭɪˈona"),
    ("5000000", "pʲˈɑtʲ mʲˌɪɭɪˈonʌf"),
    ("12000000", "dvʲɪnˈɑttsʌtʲ mʲˌɪɭɪˈonʌf"),
    ("1000000000", "ʌdʲˈin mʲˌɪɭɪˈjart"),
]


@pytest.mark.parametrize("num,expected", RU_VAR_CASES)
def test_ru_magnitude_grammatical_number(num, expected):
    assert _nfc(G2P("ru", force_compat=True).phonemize(num).strip()) == expected


PL_CS_VAR_CASES = [
    ("pl", "2000", "dvˈa tɨɕˈɔntsɛ"),
    ("pl", "5000", "pʲˈɛɲtɕ tɨɕˈɛntsɨ"),
    ("pl", "12000000", "dvanˈaɕtɕɛ mʲiljˈɔnuf"),   # teen -> 5+ form, not the 2-4 form
    ("pl", "22000", "dvadʑˈɛɕtɕadvˈa tɨɕˈɔntsɛ"),
    ("cs", "2000000", "dvˈa mˈiliˌoːni"),
    ("cs", "5000000", "pjˈet mˈiliˌoːnuː"),
    ("cs", "22000", "dvˈatseddvˈa cˈisiːts"),      # cs varies on the WHOLE count, not its last digit
    ("cs", "4000000000", "tʃtˈir̝i mˈiliˌardi"),
]


@pytest.mark.parametrize("lang,num,expected", PL_CS_VAR_CASES)
def test_pl_cs_magnitude_grammatical_number(lang, num, expected):
    assert _nfc(G2P(lang, force_compat=True).phonemize(num).strip()) == expected


def test_uk_unnamed_magnitude_variant_falls_back_to_thousand():
    # uk shares ru's variant bits but names no `_1MA1`; the magnitude word must fall back to
    # `_0M1` (numbers.c:975), not vanish.
    assert _nfc(G2P("uk", force_compat=True).phonemize("1000").strip()) == "odˈen tˈesjatʃa"


def test_sl_unnamed_magnitude_variant_falls_back_to_thousand():
    assert _nfc(G2P("sl", force_compat=True).phonemize("10000").strip()) == "dɛsˈeːt tˈiːsɔtʃ"


# --- leading zeros (numbers.c ph_zeros) ---------------------------------------------------
# A number token written with a leading zero speaks each zero, all inside ONE stress domain,
# so only the first keeps a primary. The loop stops one short of the end, so "00" is one
# spoken zero plus the value zero. `0H:MM` is the one exception espeak treats as a time.
LEADING_ZERO_CASES = [
    ("nl", "05", "nˈɵl vˌɛɪf"),
    ("nl", "005", "nˈɵlnˌɵl vˌɛɪf"),
    ("nl", "09:05", "nˈeːɣən nˈɵl vˌɛɪf"),
    ("nl", "09:00", "nˈeːɣən nˈɵl nˌɵl"),
    ("nl", "00:05", "nˈɵl nˈɵl vˌɛɪf"),
    ("nl", "09:5", "nˈɵl nˌeːɣən vˈɛɪf"),   # not a HH:MM shape -> the leading zero IS spoken
    ("nl", "02:30", "tʋˈeː dˈɛrtəx"),       # a time: leading zero omitted
    ("nl", "12:30", "tʋˈaːlf dˈɛrtəx"),
    ("en", "05", "zˈiəɹəʊ fˈaɪv"),
    ("en", "007", "zˈiəɹəʊzˈiəɹəʊ sˈɛvən"),
    ("en", "00", "zˈiəɹəʊ zˈiəɹəʊ"),
    ("en", "010", "zˈiəɹəʊ tˈɛn"),
    ("en", "09:05", "nˈaɪn zˈiəɹəʊ fˈaɪv"),
    ("en", "02:30", "tˈuː θˈɜːti"),
    ("de", "05", "nˈʊl fˈʏnf"),
]


@pytest.mark.parametrize("lang,num,expected", LEADING_ZERO_CASES)
def test_leading_zeros_spoken(lang, num, expected):
    assert _nfc(G2P(lang, force_compat=True).phonemize(num).strip()) == expected


# --- ja: the assembled number is ONE stress domain ----------------------------------------
# Every ja numeral fragment ends in a phonPAUSE_NOLINK (`_1  it_si_!`), which is an ordinary
# phoneme of that word, NOT a phrase break: espeak runs SetWordStress across the whole
# assembled number once, so non-final numerals are demoted instead of each keeping a primary.
JA_CASES = [
    ("11", "dzɯᵝˈitsi"),
    ("12", "dzˈɯᵝniː"),
    ("20", "nˈi dzɯᵝ"),
    ("21", "nˌi dzɯᵝˈitsi"),
    ("42", "jo̞n dzˈɯᵝniː"),
    ("99", "kʲɯᵝɯᵝ dzˈɯᵝkʲɯᵝɯᵝ"),
    ("100", "ˌitsiçˈäkɯᵝ"),
    ("101", "ˌitsiçˌäkɯᵝ ˈitsi"),
    ("1000", "itsˈi se̞n"),
    ("1000000", "ˌitsi çäkˈɯᵝmän"),
]


@pytest.mark.parametrize("num,expected", JA_CASES)
def test_ja_number_single_stress_domain(num, expected):
    assert _nfc(G2P("ja", force_compat=True).phonemize(num).strip()) == expected
