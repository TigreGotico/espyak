"""Per-language translator configuration, lifted from tr_languages.c SelectTranslator.

Each entry overrides the NewTranslator defaults (English-like). Only the fields that
affect G2P *output* are modelled here (stress, letter classification, conditions);
length/amplitude/intonation are synthesis-only and omitted.

This is the data half of tr_languages.py. Start with the pilot set; extend per tranche.

Reference: espeak-ng 1.52.0 src/libespeak-ng/tr_languages.c.
"""
from espyak import constants as K

# NewTranslator defaults (tr_languages.c:271+)
DEFAULTS = {
    "stress_rule": K.STRESSPOSN_2R,
    "stress_flags": 0,
    "unstressed_wd1": 1,
    "unstressed_wd2": 3,
    "max_initial_consonants": 3,
    # letter_bits groups (SetLetterBits default, lines 277-284)
    "letter_bits": {
        K.LETTERGP_A: "aeiou",
        K.LETTERGP_B: "bcdfgjklmnpqstvxz",
        K.LETTERGP_C: "bcdfghjklmnpqrstvwxz",
        K.LETTERGP_H: "hlmnr",
        K.LETTERGP_F: "cfhkpqstx",
        K.LETTERGP_G: "bdgjlmnrvwyz",
        K.LETTERGP_Y: "eiy",
        K.LETTERGP_VOWEL2: "aeiouy",
    },
    # extra vowels added to groups A and VOWEL2 via SetLetterVowel (per-language)
    "extra_vowels": "",
    "spelling_stress": False,
    "encoding": "utf-8",
}

# Per-language overrides (merged onto DEFAULTS). Keyed by language code.
LANGS = {
    "en": {
        # tr_languages.c case L('e','n'): first-syllable stress, not the 2R default
        "stress_rule": K.STRESSPOSN_1L,
        "stress_flags": 0x08,  # diminish consecutive unstressed syllables (unstressed words)
        "suffix_add_e": "e",
        "set_letter_bits": [(K.LETTERGP_Y, "aeiouy")],  # group Y = all vowels incl. y
    },
    "eo": {
        "stress_rule": K.STRESSPOSN_2R,
        "stress_flags": K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2,
        "unstressed_wd2": 2,
        # Esperanto special consonants (x-less, single chars in ISO-8859-3 / UTF-8)
        "extra_consonants": "ĉĝĥĵŝ",
        "extra_vowels": "ŭ",
        "encoding": "iso-8859-3",
    },
    "es": {
        "stress_rule": K.STRESSPOSN_2R,
        "stress_flags": K.S_FINAL_SPANISH | K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2,
        "unstressed_wd1": 0,
        "unstressed_wd2": 2,
        "extra_vowels": "áéíóúü",
        "encoding": "iso-8859-1",
        "numbers": K.NUM_SINGLE_STRESS | K.NUM_AND_UNITS | K.NUM_OMIT_1_HUNDRED
        | K.NUM_OMIT_1_THOUSAND | K.NUM_DECIMAL_COMMA,
    },
    "de": {
        "stress_rule": K.STRESSPOSN_1L,   # German: first syllable (set in tr_languages)
        "stress_flags": 0,
        "extra_vowels": "äöü",
        "encoding": "iso-8859-1",
        "numbers": K.NUM_SWAP_TENS | K.NUM_DECIMAL_COMMA,
    },
    "fr": {
        "stress_rule": K.STRESSPOSN_1R,   # French: final syllable
        "stress_flags": K.S_NO_AUTO_2 | K.S_FINAL_DIM,
        "extra_vowels": "àâäéèêëîïôöùûü",
        "encoding": "iso-8859-1",
        "numbers": K.NUM_OMIT_1_HUNDRED | K.NUM_DECIMAL_COMMA,
    },
    # South Slavic (tr_languages.c case L('s','r'), shared by hr/bs): initial stress,
    # spelling stress on the first letter.
    "sr": {"stress_rule": K.STRESSPOSN_1L, "stress_flags": K.S_FINAL_NO_2,
           "spelling_stress": True, "extra_consonants": "čćšžđ"},
    "hr": {"stress_rule": K.STRESSPOSN_1L, "stress_flags": K.S_FINAL_NO_2,
           "spelling_stress": True, "extra_consonants": "čćšžđ"},
    "bs": {"stress_rule": K.STRESSPOSN_1L, "stress_flags": K.S_FINAL_NO_2,
           "spelling_stress": True, "extra_consonants": "čćšžđ"},
    "cs": {"stress_rule": K.STRESSPOSN_1L, "spelling_stress": True,
           "extra_vowels": "áéíóúůýě", "extra_consonants": "čďňřšťž"},
    "hu": {"stress_rule": K.STRESSPOSN_1L, "spelling_stress": True,
           "stress_flags": K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2 | K.S_NO_AUTO_2
           | 0x8000 | K.S_HYPEN_UNSTRESS, "extra_vowels": "áéíóöőúüű"},
    "ht": {"stress_rule": K.STRESSPOSN_1R,  # Haitian Creole: final-syllable stress
           "stress_flags": K.S_NO_AUTO_2 | K.S_FINAL_DIM, "extra_vowels": "àèéò"},
    "it": {"stress_rule": K.STRESSPOSN_2R, "extra_vowels": "àèéìíîòóùú",
           "stress_flags": K.S_NO_AUTO_2 | K.S_FINAL_DIM_ONLY | K.S_PRIORITY_STRESS,
           "it_lengthen": 2},  # remove length from unstressed/non-penultimate
    "sl": {"stress_rule": K.STRESSPOSN_2R, "stress_flags": K.S_NO_AUTO_2,
           "it_lengthen": 1, "extra_consonants": "čšž"},
    "la": {"stress_rule": K.STRESSPOSN_2R, "stress_flags": K.S_NO_AUTO_2},
    "lt": {"stress_rule": K.STRESSPOSN_2R, "stress_flags": K.S_NO_AUTO_2,
           "extra_vowels": "ąęėįųū", "extra_consonants": "čšž"},
    "az": {"stress_rule": K.STRESSPOSN_1RU, "stress_flags": K.S_NO_AUTO_2,
           "extra_vowels": "əıöü", "extra_consonants": "çğş"},
    "kk": {"stress_rule": K.STRESSPOSN_1RU, "stress_flags": K.S_NO_AUTO_2},
    "ro": {"stress_rule": K.STRESSPOSN_1R,
           "stress_flags": K.S_FINAL_VOWEL_UNSTRESSED | K.S_FINAL_DIM_ONLY,
           "extra_vowels": "ăâîșț"},
    "mk": {"stress_rule": K.STRESSPOSN_3R, "extra_consonants": "ѓќџљњ"},  # antepenultimate
    "eu": {"stress_rule": K.STRESSPOSN_2R,
           "stress_flags": K.S_FINAL_VOWEL_UNSTRESSED | K.S_MID_DIM, "extra_consonants": "ñ"},
    # vi (Vietnamese) deferred: needs the full tone subsystem (default-tone insertion,
    # tone-phoneme flow through set_word_stress, digit->IPA conversion) — not just config.
    "pt": {"stress_rule": K.STRESSPOSN_2R, "stress_flags": K.S_FINAL_SPANISH,
           "extra_vowels": "àáâãçéêíóôõú", "encoding": "iso-8859-1"},
    "nl": {"stress_rule": K.STRESSPOSN_1L, "extra_vowels": "äëïöüáéíóú"},
    "pl": {"stress_rule": K.STRESSPOSN_2R, "extra_vowels": "ąćęłńóśźż"},
}

# --- Cyrillic-script setup (tr_languages.c SetCyrillicLetters, offset 0x420) ----------
_RU_VOWELS = [0x10, 0x15, 0x31, 0x18, 0x1e, 0x23, 0x2b, 0x2d, 0x2e, 0x2f,
              0xb9, 0xc9, 0x91, 0x8f, 0x36]
_RU_CONSONANTS = [0x11, 0x12, 0x13, 0x14, 0x16, 0x17, 0x19, 0x1a, 0x1b, 0x1c, 0x1d,
                  0x1f, 0x20, 0x21, 0x22, 0x24, 0x25, 0x26, 0x27, 0x28, 0x29, 0x2a,
                  0x2c, 0x73, 0x7b, 0x83, 0x9b]
_CYRL_SOFT = [0x2c, 0x19, 0x27, 0x29]
_CYRL_HARD = [0x2a, 0x16, 0x26, 0x28]
_CYRL_NOTHARD = [0x11, 0x12, 0x13, 0x14, 0x17, 0x19, 0x1a, 0x1b, 0x1c, 0x1d, 0x1f,
                 0x20, 0x21, 0x22, 0x24, 0x25, 0x27, 0x29, 0x2c]
_CYRL_VOICED = [0x11, 0x12, 0x13, 0x14, 0x16, 0x17]
_CYRL_IVOWELS = [0x2c, 0x2e, 0x2f, 0x31]


def _cyrillic_config(stress_rule, stress_flags=0, **extra):
    cfg = {
        "stress_rule": stress_rule, "stress_flags": stress_flags,
        "regression": 0x03,  # regressive voicing assimilation (no final devoicing)
        "letter_bits": {},  # clear the default Latin letter bits
        "letter_bits_offset": 0x420,
        "letter_bits_codes": [
            (K.LETTERGP_A, _RU_VOWELS), (K.LETTERGP_VOWEL2, _RU_VOWELS),
            (K.LETTERGP_B, _CYRL_SOFT), (K.LETTERGP_C, _RU_CONSONANTS),
            (K.LETTERGP_H, _CYRL_HARD), (K.LETTERGP_F, _CYRL_NOTHARD),
            (K.LETTERGP_G, _CYRL_VOICED), (K.LETTERGP_Y, _CYRL_IVOWELS),
        ],
    }
    cfg.update(extra)
    return cfg


# Translator_Russian (shared by ru and uk): syllable-count stress, no auto-secondary.
LANGS["ru"] = _cyrillic_config(K.STRESSPOSN_SYLCOUNT, K.S_NO_AUTO_2)
# adds "е и є ї" to the Y (iotated/soft) group -> consonants palatalize (будем -> bˈudʲim)
LANGS["ru"]["letter_bits_codes"] = LANGS["ru"]["letter_bits_codes"] + [
    (K.LETTERGP_Y, [0x15, 0x18, 0x34, 0x37]),
]
LANGS["uk"] = _cyrillic_config(K.STRESSPOSN_SYLCOUNT, K.S_NO_AUTO_2)
LANGS["uk"]["letter_bits_codes"] = LANGS["uk"]["letter_bits_codes"] + [
    (K.LETTERGP_Y, [0x15, 0x18, 0x34, 0x37]),
]
LANGS["bg"] = _cyrillic_config(K.STRESSPOSN_2R, regression=0x107)  # + word-final devoicing
LANGS["tt"] = _cyrillic_config(K.STRESSPOSN_1R)

# --- Greek-script setup (tr_languages.c case L('e','l'), offset 0x380) ----------------
_EL_VOWELS = [0x10, 0x2c, 0x2d, 0x2e, 0x2f, 0x30, 0x31, 0x35, 0x37, 0x39, 0x3f, 0x45,
              0x49, 0x4a, 0x4b, 0x4c, 0x4d, 0x4e, 0x4f]
_EL_FVOWELS = [0x2d, 0x2e, 0x2f, 0x35, 0x37, 0x39, 0x45, 0x4d]
_EL_VOICELESS = [0x38, 0x3a, 0x3e, 0x40, 0x42, 0x43, 0x44, 0x46, 0x47]
_EL_CONSONANTS = [0x32, 0x33, 0x34, 0x36, 0x38, 0x3a, 0x3b, 0x3c, 0x3d, 0x3e, 0x40,
                  0x41, 0x42, 0x43, 0x44, 0x46, 0x47, 0x48]


def _greek_config(stress_rule, stress_flags):
    return {
        "stress_rule": stress_rule, "stress_flags": stress_flags,
        "letter_bits": {}, "letter_bits_offset": 0x380,
        "letter_bits_codes": [
            (K.LETTERGP_A, _EL_VOWELS), (K.LETTERGP_VOWEL2, _EL_VOWELS),
            (K.LETTERGP_B, _EL_VOICELESS), (K.LETTERGP_C, _EL_CONSONANTS),
            (K.LETTERGP_Y, _EL_FVOWELS),
        ],
    }


LANGS["el"] = _greek_config(K.STRESSPOSN_2R, K.S_FINAL_DIM_ONLY)
LANGS["grc"] = _greek_config(K.STRESSPOSN_2R, K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2)

# --- Indic (Brahmic) scripts: SetIndicLetters with per-script Unicode-block offset -----
_DEVA_VOWELS2 = [0x60, 0x61, 0x55, 0x56, 0x57, 0x62, 0x63]
_DEVA_CONSONANTS2 = [0x02, 0x03, 0x58, 0x59, 0x5a, 0x5b, 0x5c, 0x5d, 0x5e, 0x5f,
                     0x7b, 0x7c, 0x7e, 0x7f]
_INDIC_OFFSETS = {
    "hi": 0x900, "mr": 0x900, "ne": 0x900, "sa": 0x900, "sd": 0x900, "bpy": 0x900,
    "bn": 0x980, "as": 0x980, "pa": 0xa00, "gu": 0xa80, "or": 0xb00, "ta": 0xb80,
    "te": 0xc00, "kn": 0xc80, "ml": 0xd00, "si": 0xd80,
}


def _indic_config(offset, stress_rule=K.STRESSPOSN_1L, stress_flags=0):
    return {
        "stress_rule": stress_rule, "stress_flags": stress_flags,
        "letter_bits": {}, "letter_bits_offset": offset,
        "letter_bits_ranges": [
            (K.LETTERGP_A, 0x04, 0x14), (K.LETTERGP_A, 0x3e, 0x4d),
            (K.LETTERGP_VOWEL2, 0x04, 0x14), (K.LETTERGP_VOWEL2, 0x3e, 0x4d),
            (K.LETTERGP_B, 0x3e, 0x4d), (K.LETTERGP_C, 0x15, 0x39),
            (K.LETTERGP_Y, 0x04, 0x14), (K.LETTERGP_Y, 0x3e, 0x4c),
        ],
        "letter_bits_codes": [
            (K.LETTERGP_A, _DEVA_VOWELS2), (K.LETTERGP_VOWEL2, _DEVA_VOWELS2),
            (K.LETTERGP_B, _DEVA_VOWELS2), (K.LETTERGP_C, _DEVA_CONSONANTS2),
            (K.LETTERGP_Y, _DEVA_VOWELS2),
        ],
    }


# per-language Indic stress_flags (tr_languages.c); default kn/ta-style.
_INDIC_STRESS = {
    "hi": K.S_MID_DIM | K.S_FINAL_DIM, "mr": K.S_MID_DIM | K.S_FINAL_DIM,
    "ne": K.S_MID_DIM | K.S_FINAL_DIM, "bn": K.S_MID_DIM | K.S_FINAL_DIM,
    "as": K.S_MID_DIM | K.S_FINAL_DIM,
}
_INDIC_STRESS_RULE = {"hi": K.STRESSPOSN_1RH, "mr": K.STRESSPOSN_1RH}
for _l, _off in _INDIC_OFFSETS.items():
    LANGS[_l] = _indic_config(
        _off, stress_rule=_INDIC_STRESS_RULE.get(_l, K.STRESSPOSN_1L),
        stress_flags=_INDIC_STRESS.get(_l, K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2))


# --- Arabic (tr_languages.c SetArabicLetters, SetLetterBitsUTF8 with offset 0x600) -----
def _ar_codes(s):
    return [ord(c) - 0x600 for c in s if not c.isspace()]


LANGS["ar"] = {
    "stress_rule": K.STRESSPOSN_2R, "stress_flags": 0,
    "letter_bits": {}, "letter_bits_offset": 0x600,
    "letter_bits_codes": [
        (K.LETTERGP_A, _ar_codes("َُِ")),       # fatha damma kasra
        (K.LETTERGP_VOWEL2, _ar_codes("َُِ")),
        (K.LETTERGP_B, _ar_codes("اوي")),                       # alef waw yeh
        (K.LETTERGP_C, _ar_codes("بپتةثجحخدذرزسشصضطظعغفقكلمنئؤءأآإه")),
        (K.LETTERGP_F, _ar_codes("صضطظ")),                      # thick (emphatic)
        (K.LETTERGP_G, _ar_codes("ّ")), (K.LETTERGP_H, _ar_codes("ّ")),
        (K.LETTERGP_Y, _ar_codes("ّ")),                    # shadda
    ],
}


# --- Korean (Hangul syllables decomposed to jamo; SetLetterBits at OFFSET_KOREAN) ------
LANGS["ko"] = {
    "stress_rule": K.STRESSPOSN_2R, "stress_flags": 0, "decompose_hangul": True,
    "letter_bits": {}, "letter_bits_offset": 0x1100,
    "letter_bits_ranges": [(K.LETTERGP_A, 0x61, 0x75), (K.LETTERGP_VOWEL2, 0x61, 0x75)],
    "letter_bits_codes": [
        (K.LETTERGP_Y, [0x63, 0x64, 0x67, 0x68, 0x6d, 0x72, 0x74, 0x75]),  # y/i vowels
        (K.LETTERGP_G, [0x02, 0x05, 0x06, 0xab, 0xaf, 0xb7, 0xbc]),        # voiced
    ],
}


def get_config(lang):
    cfg = dict(DEFAULTS)
    cfg["letter_bits"] = dict(DEFAULTS["letter_bits"])
    cfg["translator_name"] = K.L(lang[0], lang[1]) if len(lang) >= 2 else 0
    over = LANGS.get(lang)
    if over is None:
        # unknown language: defaults (English-like) — still usable
        over = {}
    cfg.update(over)
    return cfg
