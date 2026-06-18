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


LANGS["ru"] = _cyrillic_config(K.STRESSPOSN_SYLCOUNT)
LANGS["uk"] = _cyrillic_config(K.STRESSPOSN_SYLCOUNT)
LANGS["bg"] = _cyrillic_config(K.STRESSPOSN_2R)
LANGS["tt"] = _cyrillic_config(K.STRESSPOSN_1R)


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
