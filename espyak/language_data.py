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
    },
    "de": {
        "stress_rule": K.STRESSPOSN_1L,   # German: first syllable (set in tr_languages)
        "stress_flags": 0,
        "extra_vowels": "äöü",
        "encoding": "iso-8859-1",
    },
    "fr": {
        "stress_rule": K.STRESSPOSN_1R,   # French: final syllable
        "stress_flags": K.S_NO_AUTO_2 | K.S_FINAL_DIM,
        "extra_vowels": "àâäéèêëîïôöùûü",
        "encoding": "iso-8859-1",
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
           "extra_vowels": "áéíóöőúüű"},
    "ht": {"stress_rule": K.STRESSPOSN_1R,  # Haitian Creole: final-syllable stress
           "stress_flags": K.S_NO_AUTO_2 | K.S_FINAL_DIM, "extra_vowels": "àèéò"},
    "it": {"stress_rule": K.STRESSPOSN_2R, "extra_vowels": "àèéìíîòóùú"},
    "pt": {"stress_rule": K.STRESSPOSN_2R, "stress_flags": K.S_FINAL_SPANISH,
           "extra_vowels": "àáâãçéêíóôõú", "encoding": "iso-8859-1"},
    "nl": {"stress_rule": K.STRESSPOSN_1L, "extra_vowels": "äëïöüáéíóú"},
    "pl": {"stress_rule": K.STRESSPOSN_2R, "extra_vowels": "ąćęłńóśźż"},
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
