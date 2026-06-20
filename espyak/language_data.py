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
    # Catalan shares the es (Spanish) Translator block but the 'ca' voice adds S_NO_AUTO_2
    # (no automatic secondary stress — biocomsc -> biokˈɔmsk, no ˌi) and S_FIRST_PRIMARY
    # (reduce primaries after the first to secondary). tr_languages.c case L('c','a'),
    # name2==L('c','a').
    "ca": {
        "stress_rule": K.STRESSPOSN_2R,
        "stress_flags": (K.S_FINAL_SPANISH | K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2
                         | K.S_NO_AUTO_2 | K.S_FIRST_PRIMARY),
        "unstressed_wd1": 0,
        "unstressed_wd2": 2,
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
        "it_lengthen": 1,  # LOPT_IT_LENGTHEN: drop length from unstressed syllables (y -> iɡʁɛk)
        "extra_vowels": "àâäéèêëîïôöùûü",
        "encoding": "iso-8859-1",
        "numbers": K.NUM_OMIT_1_HUNDRED | K.NUM_DECIMAL_COMMA,
    },
    # South Slavic (tr_languages.c case L('s','r'), shared by hr/bs): initial stress,
    # spelling stress on the first letter.
    "sr": {"syllabic_consonants": "rl", "stress_rule": K.STRESSPOSN_1L, "stress_flags": K.S_FINAL_NO_2, "dictrules": [2, 4],
           "spelling_stress": True, "extra_consonants": "čćšžđ"},
    "hr": {"syllabic_consonants": "rl", "stress_rule": K.STRESSPOSN_1L, "stress_flags": K.S_FINAL_NO_2, "dictrules": [1],
           "spelling_stress": True, "extra_consonants": "čćšžđ"},
    "bs": {"syllabic_consonants": "rl", "stress_rule": K.STRESSPOSN_1L, "stress_flags": K.S_FINAL_NO_2, "dictrules": [3, 4],
           "spelling_stress": True, "extra_consonants": "čćšžđ"},
    "cs": {"syllabic_consonants": "rl", "stress_rule": K.STRESSPOSN_1L, "spelling_stress": True,
           "stress_flags": K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2,  # no spurious final secondary
           "regression": 0x3,  # LOPT_REGRESSIVE_VOICING (však -> fʃak)
           "extra_vowels": "áéíóúůýě", "extra_consonants": "čďňřšťž"},
    # Finnish/Estonian: fixed initial stress (espeak's zero-init default 1L; my default is 2R)
    # fi/et: fixed initial stress, secondary on alternating NON-final syllables. espeak's
    # case sets no stress_flags (flags=0) yet never auto-secondaries the final vowel —
    # it relies on the uninitialised vowel_stress[] sentinel (UB we can't reproduce without
    # regressing langs that DO take a trochaic final-2, e.g. bn/ko/ro/ar). S_FINAL_NO_2 is a
    # documented, behaviour-faithful divergence that suppresses it cleanly for fi/et only
    # (pieneksi -> pˈieneksɪ not pˈieneksˌi; meie -> mˈeije not mˈeijˌe).
    # fi/et stress_flags come from the VOICE file (stressOpt): S_FINAL_DIM_ONLY | S_FINAL_NO_2 |
    # S_2_TO_HEAVY — the last keeps secondary stress off light syllables (et följetonist ->
    # fˈøʎjetonist, no ˌo before the heavy final).
    "fi": {"stress_rule": K.STRESSPOSN_1L, "extra_vowels": "äöy",
           "stress_flags": K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2 | K.S_2_TO_HEAVY},
    "et": {"stress_rule": K.STRESSPOSN_1L, "extra_vowels": "äöüõ",
           "stress_flags": K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2 | K.S_2_TO_HEAVY},
    # Latvian: fixed initial stress. _list headwords carry explicit stress so they scored
    # 100% under the wrong 2R default, but rules-based words (Glāžšķūņa -> ɡlˈaːʒʃcuːɲa)
    # need 1L.
    "lv": {"stress_rule": K.STRESSPOSN_1L,
           "stress_flags": K.S_NO_AUTO_2 | K.S_FINAL_DIM | K.S_FINAL_DIM_ONLY | K.S_EO_CLAUSE1},
    # Ido (constructed, penultimate stress like Esperanto): no final auto-secondary.
    # Without S_FINAL_NO_2 the final vowel got a spurious ˌ (Jun/junio -> dʒˈuniˌo not dʒˈunio).
    "io": {"stress_rule": K.STRESSPOSN_2R, "stress_flags": K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2},
    # Slovak: fixed initial stress (shares espeak's cs block). No config -> wrong 2R default
    # (alebo -> alˈebo instead of ˈalebo). Regressive voicing assimilation (však -> fʃak).
    "sk": {"syllabic_consonants": "rl", "stress_rule": K.STRESSPOSN_1L, "spelling_stress": True,
           "stress_flags": K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2, "regression": 0x03,
           "extra_vowels": "áäéíóôúýyr", "extra_consonants": "čďľĺňŕšťž"},
    # fixed-initial-stress langs that had no config (-> wrong 2R default). espeak's per-lang
    # stress_rule (tr_languages.c); _list headwords are mostly dict-stressed so these were
    # already high, but rules-based words needed the right rule (af alebo-class, etc.).
    "af": {"stress_rule": K.STRESSPOSN_1L, "extra_vowels": "y"},
    "be": {"stress_rule": K.STRESSPOSN_1L, "stress_flags": K.S_NO_AUTO_2 | K.S_NO_DIM},
    "da": {"stress_rule": K.STRESSPOSN_1L, "extra_vowels": "y"},
    "gd": {"stress_rule": K.STRESSPOSN_1L, "stress_flags": K.S_NO_AUTO_2},
    "is": {"stress_rule": K.STRESSPOSN_1L, "stress_flags": K.S_FINAL_NO_2, "extra_vowels": "y"},
    "sv": {"stress_rule": K.STRESSPOSN_1L, "extra_vowels": "y"},
    "tr": {"stress_rule": K.STRESSPOSN_1RU, "stress_flags": K.S_NO_AUTO_2},
    # Papiamento: stress the last syllable unless the word ends in a vowel (1R +
    # S_FINAL_VOWEL_UNSTRESSED). No config -> wrong 2R default (algun -> ˈalɡuŋ not alɡˈuŋ).
    "pap": {"stress_rule": K.STRESSPOSN_1R, "unstressed_wd1": 0, "unstressed_wd2": 2,
            "stress_flags": (K.S_FINAL_VOWEL_UNSTRESSED | K.S_FINAL_DIM_ONLY
                             | K.S_FINAL_NO_2 | K.S_NO_AUTO_2)},
    # Albanian: stress the last syllable unless it ends in a vowel (1R +
    # S_FINAL_VOWEL_UNSTRESSED). No config -> wrong 2R default. Plain 1R regresses (final
    # vowels), but the flags move stress off a final vowel (muaji -> mˈuaɪi).
    "sq": {"stress_rule": K.STRESSPOSN_1R, "extra_vowels": "y",
           "stress_flags": (K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2 | K.S_FINAL_VOWEL_UNSTRESSED)},
    "hu": {"stress_rule": K.STRESSPOSN_1L, "spelling_stress": True,
           "stress_flags": K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2 | K.S_NO_AUTO_2
           | 0x8000 | K.S_HYPEN_UNSTRESS, "extra_vowels": "áéíóöőúüű"},
    "ht": {"stress_rule": K.STRESSPOSN_1R,  # Haitian Creole: final-syllable stress
           "stress_flags": K.S_NO_AUTO_2 | K.S_FINAL_DIM, "extra_vowels": "àèéò"},
    "it": {"stress_rule": K.STRESSPOSN_2R, "extra_vowels": "àèéìíîòóùú",
           "stress_flags": K.S_NO_AUTO_2 | K.S_FINAL_DIM_ONLY | K.S_PRIORITY_STRESS,
           "it_lengthen": 2,  # remove length from unstressed/non-penultimate
           "lopt_alt": True,  # ApplySpecialAttribute2: $alt/$alt2 shift the post-stress e<->E o<->O
           "reduce_dict_vowels": True},  # LOPT_REDUCE&1: reduce vowels even in it_list entries
    "sl": {"syllabic_consonants": "rl", "stress_rule": K.STRESSPOSN_2R, "stress_flags": K.S_NO_AUTO_2,
           "it_lengthen": 1, "regression": 0x103, "extra_consonants": "čšž", "lopt_alt": True,
           "unstress_u_words": True, "drop_u_length": True},  # $u words: short, open vowels
    "la": {"stress_rule": K.STRESSPOSN_2R, "stress_flags": K.S_NO_AUTO_2},
    "ga": {"stress_rule": K.STRESSPOSN_1L,  # Irish: initial stress, no secondary
           "stress_flags": K.S_NO_AUTO_2},
    "lt": {"stress_rule": K.STRESSPOSN_2R, "stress_flags": K.S_NO_AUTO_2,
           "extra_vowels": "ąęėįųū", "extra_consonants": "čšž"},
    "az": {"stress_rule": K.STRESSPOSN_1RU, "stress_flags": K.S_NO_AUTO_2,
           "extra_vowels": "əıöü", "extra_consonants": "çğş"},
    "kk": {"stress_rule": K.STRESSPOSN_1RU, "stress_flags": K.S_NO_AUTO_2},
    "ku": {"stress_rule": K.STRESSPOSN_1RU, "extra_vowels": "êîû", "extra_consonants": "çş"},
    # Welsh: $u function words reduce (clear y -> obscure: fy -> vˈø not vˈɨː); default 2R suits
    # the penultimate stress, so only the $u-reduction flag is needed.
    "cy": {"unstress_u_words": True, "extra_vowels": "wy"},  # Welsh: w and y are vowels
                                                              # (SetLetterVowel w/y) -> wy digraph wins
    "smj": {"stress_rule": K.STRESSPOSN_1L,  # Lule Saami: first syllable
            "stress_flags": K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2 | K.S_2_TO_HEAVY,
            "spelling_stress": True, "extra_vowels": "áä", "extra_consonants": "ŋđ",
            "unstress_u_words": True},  # $u function words reduce despite the clause accent
    "ro": {"stress_rule": K.STRESSPOSN_1R,
           "stress_flags": K.S_FINAL_VOWEL_UNSTRESSED | K.S_FINAL_DIM_ONLY,
           "extra_vowels": "ăâîșț"},
    "mk": {"stress_rule": K.STRESSPOSN_3R, "extra_consonants": "ѓќџљњ",  # antepenultimate
           "unstress_u_words": True},  # $u function words reduce despite the clause accent
    "eu": {"stress_rule": K.STRESSPOSN_EU,  # Basque: primary 2nd syllable, secondary last
           "stress_flags": K.S_FINAL_VOWEL_UNSTRESSED | K.S_MID_DIM, "extra_consonants": "ñ"},
    "vi": {"stress_rule": K.STRESSPOSN_1L, "unstressed_wd1": 2, "unstressed_wd2": 2,
           "tonic_stress": 3, "tone_language": 1,  # secondary stress + default-tone pass
           # all tone-marked vowels are vowels (espeak vowels_vi[]) so glide rules fire
           # (o before a vowel -> w: hoặc -> hwˌa6c)
           "vowels_override": "aàáảãạăằắẳẵặâầấẩẫậeèéẻẽẹêềếểễệiìíỉĩịoòóỏõọôồốổỗộơờớởỡợuùúủũụưừứửữựyỳýỷỹỵ"},
    "pt": {"stress_rule": K.STRESSPOSN_1R,  # final syllable (tr_languages.c L('p','t'))
           "stress_flags": K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2 | K.S_INITIAL_2 | K.S_PRIORITY_STRESS,
           "lopt_alt": True, "extra_vowels": "àáâãçéêíóôõú", "encoding": "iso-8859-1"},
    "nl": {"stress_rule": K.STRESSPOSN_1L, "extra_vowels": "äëïöüáéíóú",
           "regression": 0x100},  # LOPT_REGRESSIVE_VOICING: devoice at end of word (heb->hɛp)
    "pl": {"stress_rule": K.STRESSPOSN_2R, "extra_vowels": "ąćęłńóśźż",
           "regression": 0x9},  # LOPT_REGRESSIVE_VOICING (usb -> uɛzbɛ)
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
LANGS["el"]["u_clause_final"] = True  # 3+-syll $u words take the clause accent on the last syllable
LANGS["grc"] = _greek_config(K.STRESSPOSN_2R, K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2)
# Lojban: LOPT_CAPS_IN_WORD — a capital letter marks the stressed syllable (RAtatar -> rˈatatˌar).
LANGS["jbo"] = {"stress_rule": K.STRESSPOSN_2R, "caps_in_word": True, "extra_vowels": "y"}
# Burmese is tonal: collapse a syllable's inherent tone + explicit tone marker to the explicit
# one (ī gives i1, visarga း gives 2 -> i2, not i12).
LANGS["my"] = {"tone_collapse": True}

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


# per-language Indic stress_flags (tr_languages.c); default kn/ta/te/ml-style
# (S_FINAL_DIM_ONLY | S_FINAL_NO_2). The gu/mr/or/pa block uses 1RH + S_MID_DIM|S_FINAL_DIM.
_INDIC_STRESS = {
    "hi": K.S_MID_DIM | K.S_FINAL_DIM, "mr": K.S_MID_DIM | K.S_FINAL_DIM,
    "ne": K.S_MID_DIM | K.S_FINAL_DIM, "bn": K.S_MID_DIM | K.S_FINAL_DIM,
    "as": K.S_MID_DIM | K.S_FINAL_DIM,
    "gu": K.S_MID_DIM | K.S_FINAL_DIM, "or": K.S_MID_DIM | K.S_FINAL_DIM,
    "pa": K.S_MID_DIM | K.S_FINAL_DIM,
}
_INDIC_STRESS_RULE = {
    "hi": K.STRESSPOSN_1RH, "mr": K.STRESSPOSN_1RH,
    "gu": K.STRESSPOSN_1RH, "or": K.STRESSPOSN_1RH, "pa": K.STRESSPOSN_1RH,
    "ml": K.STRESSPOSN_1SL,  # 1st syllable unless 1st vowel short and 2nd long
}
for _l, _off in _INDIC_OFFSETS.items():
    LANGS[_l] = _indic_config(
        _off, stress_rule=_INDIC_STRESS_RULE.get(_l, K.STRESSPOSN_1L),
        stress_flags=_INDIC_STRESS.get(_l, K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2))


# Georgian (1L + S_FINAL_NO_2) and Amharic (1L + S_NO_AUTO_2|S_FINAL_DIM): non-Latin
# scripts whose stress operates on the phoneme vowels, so only the stress config is needed.
LANGS["ka"] = {"stress_rule": K.STRESSPOSN_1L, "stress_flags": K.S_FINAL_NO_2}
LANGS["am"] = {"stress_rule": K.STRESSPOSN_1L,
               "stress_flags": K.S_NO_AUTO_2 | K.S_FINAL_DIM}

# Sinhala has its own Unicode layout (not the ISCII-derived ranges SetIndicLetters assumes),
# so it overrides the generic Indic config built above: consonants 0x1a-0x46, vowels 0x05-0x16,
# vowel signs + virama 0x4a-0x73. The C range is what lets the virama's `C) ්` rule fire
# (suppress the inherent vowel) instead of speaking the virama's name "halkirima".
LANGS["si"] = {
    "stress_rule": K.STRESSPOSN_1L,
    "stress_flags": K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2,
    "letter_bits": {}, "letter_bits_offset": 0x0d80,
    "letter_bits_ranges": [
        (K.LETTERGP_A, 0x05, 0x16), (K.LETTERGP_A, 0x4a, 0x73),
        (K.LETTERGP_B, 0x4a, 0x73), (K.LETTERGP_C, 0x1a, 0x46),
    ],
}

# --- Arabic (tr_languages.c SetArabicLetters, SetLetterBitsUTF8 with offset 0x600) -----
def _ar_codes(s):
    return [ord(c) - 0x600 for c in s if not c.isspace()]


LANGS["ar"] = {
    # Arabic stress is antepenultimate with an auto-secondary on the final (ذلك ->
    # ðˈaːlikˌa, الذين -> ʔallˈaðiːnˌa): STRESSPOSN_3R matches the oracle. (espeak reaches
    # this via the weight logic inside its default 2R; 3R is the faithful approximation.)
    "stress_rule": K.STRESSPOSN_3R, "stress_flags": 0,
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
# Sindhi is written in the Arabic script (OFFSET_ARABIC); reuse the Arabic letter bits so
# vowels are detected, but Sindhi stress is penultimate (2R), not Arabic's antepenult (3R).
LANGS["sd"] = dict(LANGS["ar"], stress_rule=K.STRESSPOSN_2R)
# Urdu: the voice file (lang/.../ur) sets `stressRule 6` = STRESSPOSN_1RH (last heaviest syllable,
# excluding the final) — the Hindi/Urdu weight-based stress. Default 2R put the accent on the wrong
# syllable for words whose final syllable is heavy (انھوں UnHo:n -> ʊnhˈoːn, the long oː).
LANGS["ur"] = {"stress_rule": K.STRESSPOSN_1RH, "unstress_u_words": True}
# Hawaiian: a macron (long vowel) holding the lexical primary on a non-final syllable
# demotes to secondary, the clause nucleus moving to the final syllable (kākou -> kˌaːkoˈu).
LANGS["haw"] = {"macron_clause_final": True}
# Voice-file stressRule overrides that the tr_languages.c port lacked (lang/.../<code>):
# chr Cherokee stressRule 9 (mark all stressed), piqd Klingon & quc K'iche' stressRule 3 (final),
# py Pyash stressRule 0 (first). Default 2R was wrong for rules-based words.
LANGS.setdefault("chr", {})["stress_rule"] = K.STRESSPOSN_ALL
LANGS.setdefault("piqd", {})["stress_rule"] = K.STRESSPOSN_1R
LANGS.setdefault("quc", {})["stress_rule"] = K.STRESSPOSN_1R
LANGS.setdefault("py", {})["stress_rule"] = K.STRESSPOSN_1L

# --- Armenian (tr_languages.c case L('h','y'), OFFSET_ARMENIAN 0x530) -----------------
_HY_VOWELS = [0x31, 0x35, 0x37, 0x38, 0x3b, 0x48, 0x55]
_HY_CONSONANTS = [0x32, 0x33, 0x34, 0x36, 0x39, 0x3a, 0x3c, 0x3d, 0x3e, 0x3f, 0x40, 0x41,
                  0x42, 0x43, 0x44, 0x46, 0x47, 0x49, 0x4a, 0x4b, 0x4c, 0x4d, 0x4e, 0x4f,
                  0x50, 0x51, 0x52, 0x53, 0x54, 0x56]
LANGS["hy"] = {
    "stress_rule": K.STRESSPOSN_1R, "stress_flags": 0,  # final syllable
    "letter_bits": {}, "letter_bits_offset": 0x530,
    "letter_bits_codes": [
        (K.LETTERGP_A, _HY_VOWELS), (K.LETTERGP_VOWEL2, _HY_VOWELS),
        (K.LETTERGP_B, _HY_CONSONANTS), (K.LETTERGP_C, _HY_CONSONANTS + [0x45]),
    ],
}


# --- Korean (Hangul syllables decomposed to jamo; SetLetterBits at OFFSET_KOREAN) ------
LANGS["ko"] = {
    "stress_rule": K.STRESSPOSN_2LLH, "stress_flags": 0, "decompose_hangul": True,
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
