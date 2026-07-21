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
        "lopt_unpronouncable": 2,  # tr_languages.c L('e','n'): rules-based Unpronouncable2 (str ok)
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
    "es": {"spirantize": True,
        "stress_rule": K.STRESSPOSN_2R,
        "stress_flags": K.S_FINAL_SPANISH | K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2,
        "unstressed_wd1": 0,
        "unstressed_wd2": 2,
        "lopt_unpronouncable": 2,  # tr_languages.c L('e','s') else-branch (NOT ca/an/ia, which keep 's')
        "extra_vowels": "áéíóúü",
        "encoding": "iso-8859-1",
        "numbers": K.NUM_SINGLE_STRESS | K.NUM_AND_UNITS | K.NUM_OMIT_1_HUNDRED
        | K.NUM_OMIT_1_THOUSAND | K.NUM_DECIMAL_COMMA | K.NUM_DFRACTION_4,
    },
    # Aragonese shares the es (Spanish) Translator block (tr_languages.c case L('a','n')):
    # same stress_rule (2R) and stress_flags as es/ia — S_FINAL_SPANISH | S_FINAL_DIM_ONLY |
    # S_FINAL_NO_2 (no S_NO_AUTO_2, unlike ca). Without this an fell to DEFAULTS (flags=0,
    # unstressed_wd 1/3) which mis-placed the primary/secondary on 16 headwords.
    "an": {"spirantize": True,
        "stress_rule": K.STRESSPOSN_2R,
        "stress_flags": K.S_FINAL_SPANISH | K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2,
        "unstressed_wd1": 0,
        "unstressed_wd2": 2,
        "extra_vowels": "áéíóúü",
        "encoding": "iso-8859-1",
        # an reads the fraction digit-by-digit (no NUM_DFRACTION bit, tr_languages.c L('a','n')).
        "numbers": K.NUM_HUNDRED_AND | K.NUM_DECIMAL_COMMA,
    },
    # Catalan shares the es (Spanish) Translator block but the 'ca' voice adds S_NO_AUTO_2
    # (no automatic secondary stress — biocomsc -> biokˈɔmsk, no ˌi) and S_FIRST_PRIMARY
    # (reduce primaries after the first to secondary). tr_languages.c case L('c','a'),
    # name2==L('c','a').
    "ca": {"unstress_u_words": True, "spirantize": True, 
        "stress_rule": K.STRESSPOSN_2R,
        "stress_flags": (K.S_FINAL_SPANISH | K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2
                         | K.S_NO_AUTO_2 | K.S_FIRST_PRIMARY),
        "unstressed_wd1": 0,
        "unstressed_wd2": 2,
        # ca reads the fraction as a whole cardinal (NUM_DFRACTION_4, tr_languages.c shares es).
        "numbers": K.NUM_HUNDRED_AND | K.NUM_DECIMAL_COMMA | K.NUM_DFRACTION_4,
    },
    "de": {"trill_r_not_after_stop": True, "lopt_prefixes": True,
        "stress_rule": K.STRESSPOSN_1L,   # German: first syllable (set in tr_languages)
        "stress_flags": 0,
        "lopt_unpronouncable": 2,  # tr_languages.c L('d','e'): rules-based Unpronouncable2 (tsch ok)
        "extra_vowels": "äöü",
        "encoding": "iso-8859-1",
        "regression": 0x100,  # LOPT_REGRESSIVE_VOICING: devoice word-final obstruents (Auslautverhärtung)
        "numbers": K.NUM_SWAP_TENS | K.NUM_DECIMAL_COMMA,
    },
    "fr": {
        "stress_rule": K.STRESSPOSN_1R,   # French: final syllable
        "stress_flags": K.S_NO_AUTO_2 | K.S_FINAL_DIM,
        "it_lengthen": 1,  # LOPT_IT_LENGTHEN: drop length from unstressed syllables (y -> iɡʁɛk)
        "extra_vowels": "àâäéèêëîïôöùûü",
        "encoding": "iso-8859-1",
        "numbers": K.NUM_OMIT_1_HUNDRED | K.NUM_DECIMAL_COMMA | K.NUM_DFRACTION_4
        | K.NUM_VIGESIMAL,
    },
    # South Slavic (tr_languages.c case L('s','r'), shared by hr/bs): initial stress,
    # spelling stress on the first letter. ph_croatian laxes a/i/u via ChangeIfNotStressed,
    # so $u function words reduce despite carrying the clause accent (li->lˈɪ, ili->ˈɪlɪ).
    "sr": {"syllabic_consonants": "rl", "stress_rule": K.STRESSPOSN_1L, "stress_flags": K.S_FINAL_NO_2, "dictrules": [2, 4],
           "regression": 0x3,  # LOPT_REGRESSIVE_VOICING (tr_languages.c L('s','r'), shared hr/bs)
           "max_initial_consonants": 5,  # tr_languages.c L('s','r')
           "spelling_stress": True, "extra_consonants": "čćšžđ", "unstress_u_words": True},
    "hr": {"syllabic_consonants": "rl", "stress_rule": K.STRESSPOSN_1L, "stress_flags": K.S_FINAL_NO_2, "dictrules": [1],
           "regression": 0x3,  # LOPT_REGRESSIVE_VOICING (tr_languages.c L('s','r'), shared hr/bs)
           "max_initial_consonants": 5,  # tr_languages.c L('s','r')
           "spelling_stress": True, "extra_consonants": "čćšžđ", "unstress_u_words": True},
    "bs": {"syllabic_consonants": "rl", "stress_rule": K.STRESSPOSN_1L, "stress_flags": K.S_FINAL_NO_2, "dictrules": [3, 4],
           "regression": 0x3,  # LOPT_REGRESSIVE_VOICING (tr_languages.c L('s','r'), shared hr/bs)
           "max_initial_consonants": 5,  # tr_languages.c L('s','r')
           "spelling_stress": True, "extra_consonants": "čćšžđ", "unstress_u_words": True},
    "cs": {"syllabic_consonants": "rl", "stress_rule": K.STRESSPOSN_1L, "spelling_stress": True,
           "stress_flags": K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2,  # no spurious final secondary
           "regression": 0x3,  # LOPT_REGRESSIVE_VOICING (však -> fʃak)
           "max_initial_consonants": 5,  # tr_languages.c L('c','s') (shared sk)
           "extra_vowels": "áéíóúůýě", "extra_consonants": "čďňřšťž",
           # cs reads the fraction as a whole cardinal when it is <=2 digits (NUM_DFRACTION_2);
           # its decimal separator is ',' (tr_languages.c L('c','s') sets decimal_sep=',').
           "numbers": K.NUM_HUNDRED_AND | K.NUM_DECIMAL_COMMA | K.NUM_DFRACTION_2},
    # Finnish/Estonian: fixed initial stress (espeak's zero-init default 1L; my default is 2R)
    # fi/et: fixed initial stress, secondary on alternating NON-final syllables. espeak's
    # case sets no stress_flags (flags=0) yet never auto-secondaries the final vowel —
    # it relies on the uninitialised vowel_stress[] sentinel (UB we can't reproduce without
    # regressing langs that DO take a trochaic final-2, e.g. bn/ko/ro/ar). S_FINAL_NO_2 is a
    # behaviour-faithful implementation choice (NOT a default-vs-compat divergence: the OUTPUT
    # matches espeak; it just reaches espeak's result via a flag instead of its UB) for fi/et only
    # (pieneksi -> pˈieneksɪ not pˈieneksˌi; meie -> mˈeije not mˈeijˌe).
    # fi/et stress_flags come from the VOICE file (stressOpt): S_FINAL_DIM_ONLY | S_FINAL_NO_2 |
    # S_2_TO_HEAVY — the last keeps secondary stress off light syllables (et följetonist ->
    # fˈøʎjetonist, no ˌo before the heavy final).
    "fi": {"stress_rule": K.STRESSPOSN_1L, "extra_vowels": "äöy", "spelling_stress": True,
           "stress_flags": K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2 | K.S_2_TO_HEAVY,
           # fi reads the fraction as a whole cardinal when it is <=2 digits (NUM_DFRACTION_2).
           "numbers": K.NUM_HUNDRED_AND | K.NUM_DECIMAL_COMMA | K.NUM_DFRACTION_2},
    "et": {"stress_rule": K.STRESSPOSN_1L, "extra_vowels": "äöüõ", "spelling_stress": True,
           "stress_flags": K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2 | K.S_2_TO_HEAVY},
    # Latvian: fixed initial stress. _list headwords carry explicit stress so they scored
    # 100% under the wrong 2R default, but rules-based words (Glāžšķūņa -> ɡlˈaːʒʃcuːɲa)
    # need 1L.
    "lv": {"stress_rule": K.STRESSPOSN_1L, "spelling_stress": True,
           "stress_flags": K.S_NO_AUTO_2 | K.S_FINAL_DIM | K.S_FINAL_DIM_ONLY | K.S_EO_CLAUSE1},
    # Ido (constructed, penultimate stress like Esperanto): no final auto-secondary.
    # Without S_FINAL_NO_2 the final vowel got a spurious ˌ (Jun/junio -> dʒˈuniˌo not dʒˈunio).
    "io": {"stress_rule": K.STRESSPOSN_2R, "stress_flags": K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2},
    # Slovak: fixed initial stress (shares espeak's cs block). No config -> wrong 2R default
    # (alebo -> alˈebo instead of ˈalebo). Regressive voicing assimilation (však -> fʃak).
    "sk": {"syllabic_consonants": "rl", "stress_rule": K.STRESSPOSN_1L, "spelling_stress": True,
           "stress_flags": K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2, "regression": 0x03,
           "max_initial_consonants": 5,  # tr_languages.c L('c','s')/L('s','k')
           "extra_vowels": "áäéíóôúýyr", "extra_consonants": "čďľĺňŕšťž"},
    # fixed-initial-stress langs that had no config (-> wrong 2R default). espeak's per-lang
    # stress_rule (tr_languages.c); _list headwords are mostly dict-stressed so these were
    # already high, but rules-based words needed the right rule (af alebo-class, etc.).
    "af": {"stress_rule": K.STRESSPOSN_1L, "extra_vowels": "y", "lopt_prefixes": True, "accents_before": True},
    "be": {"stress_rule": K.STRESSPOSN_1L, "stress_flags": K.S_NO_AUTO_2 | K.S_NO_DIM},
    # da reads the fraction digit-by-digit; decimal separator is ',' (tr_languages.c L('d','a')).
    "da": {"stress_rule": K.STRESSPOSN_1L, "extra_vowels": "y", "lopt_prefixes": True,
           "numbers": K.NUM_HUNDRED_AND | K.NUM_DECIMAL_COMMA},
    # Luxembourgish has no tr_languages.c block, so it keeps the NewTranslator defaults
    # (2R stress). Its lb_list defines the accented letters as bare `$accent` entries but
    # ships NO accent-name spellings (`_grv`/`_acu`/… absent). LookupLetterAccent therefore
    # writes nothing and espeak emits an EMPTY word — it does NOT fall back to the rules.
    # accent_empty_no_fallback makes the $accent path exclusive so à/é/ö/… -> '' (not ˈaː).
    "lb": {"accent_empty_no_fallback": True},
    # xex (xextan test voice): in a letter+number token the clause nucleus is the FIRST word,
    # not the last (V4 -> vˈɛːvɛt kwa: the spelled letter keeps primary, the number is reduced).
    # Most langs (fo etc.) put the nucleus on the LAST part (clause_nucleus_last default True).
    "xex": {"clause_nucleus_last": False},
    "gd": {"stress_rule": K.STRESSPOSN_1L, "stress_flags": K.S_NO_AUTO_2},
    "is": {"stress_rule": K.STRESSPOSN_1L, "stress_flags": K.S_FINAL_NO_2, "extra_vowels": "y"},
    # sv reads the fraction digit-by-digit; decimal separator is ',' (tr_languages.c L('s','v')).
    "sv": {"stress_rule": K.STRESSPOSN_1L, "extra_vowels": "y",
           "numbers": K.NUM_HUNDRED_AND | K.NUM_DECIMAL_COMMA},
    "tr": {"stress_rule": K.STRESSPOSN_1RU, "stress_flags": K.S_NO_AUTO_2,
           "max_initial_consonants": 2,  # tr_languages.c L('t','r') (shared az)
           # tr reads the fraction as a whole cardinal when it is <=2 digits (NUM_DFRACTION_2).
           "numbers": K.NUM_HUNDRED_AND | K.NUM_DECIMAL_COMMA | K.NUM_DFRACTION_2},
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
           | 0x8000 | K.S_HYPEN_UNSTRESS, "extra_vowels": "áéíóöőúüű",
           # hu reads the fraction as a whole cardinal plus a "tenths"/"hundredths"/… suffix
           # (_0Z<n>, NUM_DFRACTION_5); its decimal separator is ',' (tr_languages.c L('h','u')).
           "numbers": K.NUM_HUNDRED_AND | K.NUM_DECIMAL_COMMA | K.NUM_DFRACTION_5
           | K.NUM_OMIT_1_HUNDRED | K.NUM_OMIT_1_THOUSAND},
    "ht": {"stress_rule": K.STRESSPOSN_1R,  # Haitian Creole: final-syllable stress
           "stress_flags": K.S_NO_AUTO_2 | K.S_FINAL_DIM, "extra_vowels": "àèéò"},
    "it": {"stress_rule": K.STRESSPOSN_2R, "extra_vowels": "àèéìíîòóùú",
           "stress_flags": K.S_NO_AUTO_2 | K.S_FINAL_DIM_ONLY | K.S_PRIORITY_STRESS,
           "it_lengthen": 2,  # remove length from unstressed/non-penultimate
           "lopt_alt": True,  # ApplySpecialAttribute2: $alt/$alt2 shift the post-stress e<->E o<->O
           "name_foreign_alphabet": True,  # TranslateLetter: name Cyrillic before the letter (cirillico)
           # a $u monosyllable as the clause nucleus runs its phoneme programs UNstressed (so
           # gli's final i laxes ʎi->ʎɪ via the ph_italian i->I program), the clause primary
           # overlaid after; il/in/non keep their lexical vowels unchanged
           "reduce_dict_vowels": True,  # LOPT_REDUCE&1: reduce vowels even in it_list entries
           "unstress_u_words": True,
           # it reads the fraction as a whole cardinal, adding a "hundredths"/… suffix (_0Z<n>)
           # only when the fraction has a leading zero (NUM_DFRACTION_1, tr_languages.c L('i','t')).
           "numbers": K.NUM_HUNDRED_AND | K.NUM_DECIMAL_COMMA | K.NUM_DFRACTION_1},
    "sl": {"syllabic_consonants": "rl", "stress_rule": K.STRESSPOSN_2R, "stress_flags": K.S_NO_AUTO_2,
           "it_lengthen": 1, "regression": 0x103, "extra_consonants": "čšž", "lopt_alt": True,
           "unstress_u_words": True, "drop_u_length": True},  # $u words: short, open vowels
    "la": {"stress_rule": K.STRESSPOSN_2R, "stress_flags": K.S_NO_AUTO_2},
    "ga": {"stress_rule": K.STRESSPOSN_1L,  # Irish: initial stress, no secondary
           "stress_flags": K.S_NO_AUTO_2},
    "lt": {"stress_rule": K.STRESSPOSN_2R, "stress_flags": K.S_NO_AUTO_2,
           "extra_vowels": "ąęėįųū", "extra_consonants": "čšž"},
    "az": {"param_suffix": 1, "stress_rule": K.STRESSPOSN_1RU, "stress_flags": K.S_NO_AUTO_2,
           "max_initial_consonants": 2,  # tr_languages.c L('a','z')
           "extra_vowels": "əıöü", "extra_consonants": "çğş"},
    "kk": {"param_suffix": 1, "stress_rule": K.STRESSPOSN_1RU, "stress_flags": K.S_NO_AUTO_2,
           "max_initial_consonants": 2},  # tr_languages.c L('k','k')
    "ku": {"stress_rule": K.STRESSPOSN_1RU, "extra_vowels": "êîû", "extra_consonants": "çş",
           "max_initial_consonants": 2},  # tr_languages.c L('k','u')
    # Farsi keeps the 2R default stress/flags, but tr_languages.c case L('f','a') swaps the
    # default chars_ignore table for chars_ignore_zwnj_hyphen (readclause.c IgnoreOrReplaceChar):
    # U+0640 TATWEEL is dropped, and — unlike every other language, which deletes it — U+200C
    # ZERO WIDTH NON-JOINER is rewritten to '-'. The hyphen then splits the run (translate.c:
    # "'-' between two letters is a hyphen, treat as a space"), so an abbreviation written with a
    # ZWNJ (ق‌ظ) is spelled letter-by-letter (qˈɑf zˈɑ) rather than matching the dictionary alias
    # — only the dot-spelled form (ق.ظ) hits the alias. `chars_ignore` maps codepoint -> "" (drop)
    # or replacement string, applied to the input text in phonemize().
    "fa": {"chars_ignore": {0x00AD: "", 0x0640: "", 0x200C: "-"}},
    # Welsh: $u function words reduce (clear y -> obscure: fy -> vˈø not vˈɨː); default 2R suits
    # the penultimate stress, so only the $u-reduction flag is needed.
    "cy": {"unstress_u_words": True, "set_letter_vowel": "wy",  # Welsh: SetLetterVowel(w/y)
                                                            # makes them vowels AND removes them from
                                                            # the consonant group C, so `e (CC` (e.g.
                                                            # pedwar's e+d+w) fails and `e (d`->e: wins
           "stress_rule": K.STRESSPOSN_2R,  # tr_languages.c L('c','y')
           "stress_flags": K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2,
           "unstressed_wd1": 0, "unstressed_wd2": 2,
           # Welsh counts in tens: 20 = "dau ddeg", 42 = "pedwar deg dau" (built from the _NX
           # tens fragments); OMIT_1_HUNDRED drops "un" before "cant" (100 -> "cant").
           "numbers": K.NUM_OMIT_1_HUNDRED},
    "smj": {"caps_are_letters": True, "stress_rule": K.STRESSPOSN_1L,  # Lule Saami: first syllable
            "stress_flags": K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2 | K.S_2_TO_HEAVY,
            "spelling_stress": True, "extra_vowels": "áä", "extra_consonants": "ŋđ",
            "unstress_u_words": True,  # $u function words reduce despite the clause accent
            "u_post_nuclear": True,  # a TRAILING $u word in a multi-word render stays post-nuclear
                                     # (A:ga -> ˈɑː kɑ): the spelled letter name took the accent
            "atend_clause_final": True},  # $atend letter name (O -> o:) only at clause end; a
                                          # non-final caps letter rule-translates (dO:t -> ...ˈoɔ...)
    "ro": {"stress_rule": K.STRESSPOSN_1R,
           "stress_flags": K.S_FINAL_VOWEL_UNSTRESSED | K.S_FINAL_DIM_ONLY,
           "extra_vowels": "ăâîșț",
           # ro reads the fraction as a whole cardinal when it is <=4 digits and has no leading
           # zero (NUM_DFRACTION_3, tr_languages.c L('r','o')).
           "numbers": K.NUM_HUNDRED_AND | K.NUM_DECIMAL_COMMA | K.NUM_DFRACTION_3},
    "mk": {"stress_rule": K.STRESSPOSN_3R, "extra_consonants": "ѓќџљњ",  # antepenultimate
           "unstress_u_words": True},  # $u function words reduce despite the clause accent
    # Malay (tr_languages.c case L('m','s')): 2R like the default, but the VOICE block sets
    # S_FINAL_DIM_ONLY | S_FINAL_NO_2. Without S_FINAL_NO_2 espyak fell to DEFAULTS (flags=0)
    # and auto-secondaried the word-final syllable (bertegang -> bˈərtəɡˌaŋ, radio -> rˈediˌo),
    # which espeak suppresses (bˈərtəɡaŋ, rˈedio). accents=2 ("capital" after letter name).
    "ms": {"stress_rule": K.STRESSPOSN_2R,
           "stress_flags": K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2,
           "numbers": K.NUM_DECIMAL_COMMA | K.NUM_ALLOW_SPACE | K.NUM_ROMAN},
    "eu": {"spirantize": True, "param_suffix": 1, "stress_rule": K.STRESSPOSN_EU,  # Basque: primary 2nd syllable, secondary last
           "stress_flags": K.S_FINAL_VOWEL_UNSTRESSED | K.S_MID_DIM, "extra_consonants": "ñ",
           # espeak runs SetWordStress over the whole word (stem+suffix already concatenated,
           # translateword.c:578), so a removed suffix's vowels stay in the auto-secondary pass
           # (abako -> ˈaβakˌo, secondary on the suffix -o); don't exclude them as the ro stem-only
           # path does. And a 3+-syllable $u word taking the clause accent moves it to the last
           # syllable, its 2nd-syllable accent dropping to secondary (etarako -> etˌaɾakˈo).
           "suffix_keeps_stress": True, "u_clause_final": True},
    "vi": {"stress_rule": K.STRESSPOSN_1L, "unstressed_wd1": 2, "unstressed_wd2": 2,
           "tonic_stress": 4, "clause_final_tone": "7", "u_tonic": 3, "tone_language": 1,  # vi: a content word takes
           # PRIMARY stress (ba ba -> bˈaː1 bˈaː7); the clause-final ngang syllable is tone 7 (its
           # end-of-clause variant, ph_vietnam phoneme 7), other ngang syllables the default tone 1
           # all tone-marked vowels are vowels (espeak vowels_vi[]) so glide rules fire
           # (o before a vowel -> w: hoặc -> hwˌa6c)
           "vowels_override": "aàáảãạăằắẳẵặâầấẩẫậeèéẻẽẹêềếểễệiìíỉĩịoòóỏõọôồốổỗộơờớởỡợuùúủũụưừứửữựyỳýỷỹỵ"},
    "pt": {"unstress_u_words": True, "stress_rule": K.STRESSPOSN_1R,  # final syllable (tr_languages.c L('p','t'))
           "stress_flags": K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2 | K.S_INITIAL_2 | K.S_PRIORITY_STRESS,
           "lopt_alt": True, "extra_vowels": "àáâãçéêíóôõú", "encoding": "iso-8859-1",
           "set_letter_vowel": "y",  # SetLetterVowel(tr,'y') (tr_languages.c L('p','t'))
           "priority_stress_demote": True,
           # pt reads the fraction as a whole cardinal when it is <=2 digits (NUM_DFRACTION_2);
           # NUM_AND_UNITS inserts the "e" (i) connective between tens and units — "vinte e um"
           # vˈiŋtɨiˈum (tr_languages.c L('p','t')).
           "numbers": K.NUM_HUNDRED_AND | K.NUM_DECIMAL_COMMA | K.NUM_DFRACTION_2
                      | K.NUM_AND_UNITS},
    "nl": {"stress_rule": K.STRESSPOSN_1L, "extra_vowels": "äëïöüáéíóú",
           # espeak's nl stress_flags = S_FIRST_PRIMARY (tr_languages.c L('n','l')): keep the first
           # primary, drop later ones to secondary. Applied only to the number phrase here
           # (`num_stress_flags`) — a whole-language S_FIRST_PRIMARY would also demote the second
           # primary of a $1-stressed compound (mskraam -> ˈɛmskrˌaːm), which espeak's compound
           # SetWordStress protects but espyak's does not; numbers carry no such $-forced stress.
           "num_stress_flags": K.S_FIRST_PRIMARY,
           "regression": 0x100, "lopt_prefixes": True, "lopt_dieres": True,  # LOPT_REGRESSIVE_VOICING: devoice at end of word (heb->hɛp); LOPT_DIERESES (tr_languages.c L('n','l'))
           # nl reads the fraction digit-by-digit; decimal separator is ',' (tr_languages.c L('n','l')).
           "numbers": K.NUM_HUNDRED_AND | K.NUM_DECIMAL_COMMA},
    "pl": {"stress_rule": K.STRESSPOSN_2R, "extra_vowels": "ąćęłńóśźż",
           "stress_flags": K.S_FINAL_DIM_ONLY,  # mark unstressed final syllables diminished (tr_languages.c L('p','l'))
           # SetLetterVowel(tr,'y') (tr_languages.c): Polish puts 'y' in vowel group A too
           # (default A = "aeiou", except y), so `A) ł (_` fires after y: był -> bˈɨw, not bˈɨ.
           "set_letter_bits": [(K.LETTERGP_A, "y"), (K.LETTERGP_VOWEL2, "y")],
           "max_initial_consonants": 7,  # tr_languages.c L('p','l'): "wchrzczony" (brzmi stays whole)
           "regression": 0x9,  # LOPT_REGRESSIVE_VOICING (usb -> uɛzbɛ)
           # pl reads the fraction as a whole cardinal when it is <=2 digits (NUM_DFRACTION_2).
           "numbers": K.NUM_HUNDRED_AND | K.NUM_DECIMAL_COMMA | K.NUM_DFRACTION_2},
    # Norwegian Bokmål (tr_languages.c case L('n','b')): first-syllable stress, 'y' a vowel.
    # No config -> wrong 2R default for rules-based words.
    "nb": {"stress_rule": K.STRESSPOSN_1L, "extra_vowels": "y"},  # SetLetterVowel(tr,'y')
    # Indonesian (tr_languages.c case L('i','d'), shares the ms/Malay block): 2R +
    # S_FINAL_DIM_ONLY | S_FINAL_NO_2 (suppress final auto-secondary). Without it -> DEFAULTS.
    "id": {"stress_rule": K.STRESSPOSN_2R,
           "stress_flags": K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2,
           "numbers": K.NUM_DECIMAL_COMMA | K.NUM_ALLOW_SPACE | K.NUM_ROMAN},
    # Interlingua (tr_languages.c case L('i','a'), shares the es/Spanish block): 2R +
    # S_FINAL_SPANISH | S_FINAL_DIM_ONLY | S_FINAL_NO_2, unstressed_wd 0/2 (like an).
    "ia": {"stress_rule": K.STRESSPOSN_2R,
           "stress_flags": K.S_FINAL_SPANISH | K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2,
           "unstressed_wd1": 0, "unstressed_wd2": 2},
    # Oromo (tr_languages.c case L('o','m')): 2R + S_FINAL_DIM_ONLY | S_FINAL_NO_2 | S_FINAL_LONG.
    "om": {"stress_rule": K.STRESSPOSN_2R,
           "stress_flags": K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2 | K.S_FINAL_LONG},
    # Greenlandic (tr_languages.c case L('k','l')): the GREENLANDIC stress rule (primary on the
    # last long vowel, else penult/antepenult by syllable count) + S_NO_AUTO_2 (no auto-secondary).
    "kl": {"stress_rule": K.STRESSPOSN_GREENLANDIC, "stress_flags": K.S_NO_AUTO_2},
    # Swahili / Setswana (tr_languages.c case L('s','w'), shared by tn): 2R +
    # S_FINAL_DIM_ONLY | S_FINAL_NO_2. Stress already 2R-default; the flags suppress final auto-2.
    "sw": {"stress_rule": K.STRESSPOSN_2R,
           "stress_flags": K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2, "max_initial_consonants": 4},
    "tn": {"stress_rule": K.STRESSPOSN_2R,
           "stress_flags": K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2, "max_initial_consonants": 4},
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
# ru reads the fraction digit-by-digit between "_dpt" ("и") and a "_dpt2" tail ("десятых"),
# and uses ',' as the decimal separator (Translator_Russian: NUM_DECIMAL_COMMA | NUM_OMIT_1_HUNDRED).
LANGS["ru"]["numbers"] = K.NUM_HUNDRED_AND | K.NUM_DECIMAL_COMMA
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
# el reads the fraction digit-by-digit; decimal separator is ',' (tr_languages.c L('e','l')).
LANGS["el"]["numbers"] = K.NUM_HUNDRED_AND | K.NUM_DECIMAL_COMMA
LANGS["grc"] = _greek_config(K.STRESSPOSN_2R, K.S_FINAL_DIM_ONLY | K.S_FINAL_NO_2)
# Lojban: LOPT_CAPS_IN_WORD — a capital letter marks the stressed syllable (RAtatar -> rˈatatˌar).
LANGS["jbo"] = {"stress_rule": K.STRESSPOSN_2R, "caps_in_word": True, "extra_vowels": "y"}
# Burmese is tonal: collapse a syllable's inherent tone + explicit tone marker to the explicit
# one (ī gives i1, visarga း gives 2 -> i2, not i12).
LANGS["my"] = {"tone_collapse": True}
LANGS["cmn"] = {"palatal_u_to_y": True, "neutral_tone_unstress": True,  # pinyin ü; neutral tone (5) is unstressed
                "tone_numbers": 1,  # a number after letters is a tone number (pinyin); tr_languages.c:1628
                "switch_segment_tone5": True,  # cmn tone post-pass runs over an (en)…(cmn) word switch
                "listx": True}  # langopts.listx=1: compile _listx AFTER _list, so _listx wins ties
# yue/hak (and zh): a number after letters indicates a tone number (jyutping). tr_languages.c:867/1628.
LANGS["yue"] = {"tone_numbers": 1, "listx": True}
LANGS["hak"] = {"tone_numbers": 1}
# Shan (shn): a tone language — every syllable carries a tone (default 1 if unmarked). espyak applies
# the tone marks ႇ/ႈ/း/ႉ/ႊ (tones 2-6) per shn_rules: the linguistically correct G2P. espeak's binary
# DISCARDS them and emits tone 1 for every syllable — an espeak bug (its own rules produce the tones).
# Default = correct (deviates, see docs/divergences.md shn-tone-marks); force_compat mirrors the bug.
LANGS["shn"] = {"tone_language": 1, "compat_separators": "ႇႈႉႊ", "compat_long_vowel_tone": True,
                # force_compat: a Myanmar codepoint the shn rules cannot translate (a medial ွ
                # U+103D / ှ U+103E, or the visarga း U+1038 orphaned by the asat split) is spelled
                # IN PLACE by espeak's TranslateLetter (in-band phonSWITCH) as its codepoint name:
                # (en)<Myanmar>(shn)<"letter"><hex-digit-names>, with shn's tone-copy reaching the
                # switched English phonemes. compat_spell_codepoint is the Unicode block it applies
                # to (Myanmar 0x1000-0x109F); see _spell_codepoint_inband.
                "compat_spell_orphan_visarga": True,
                "compat_spell_codepoint": (0x1000, 0x109F)}

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
        "indic_schwa": True,  # final inherent schwa deletes, so a $u nucleus can't sit on it
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
# as: the Bengali letter র (U+09B0, RA) has no rule in as_rules, so a word containing it can't be
# translated and espeak spells the WHOLE word letter by letter (FLAG_SPELLWORD): each letter by its
# NAME, and র — having no name in as — switches to its alphabet's language bn (আমার -> ˈa mˈɔ ˈakaɾ
# (bn)ɾˈɔ(as)). See _spell_letters / _spell_foreign_letter.
LANGS["as"]["spell_word_foreign_letter"] = True
# Indic $u function words reduce their schwa despite carrying the clause accent (pa ਤੱਕ -> tˈək,
# hi तक -> tˈək): the phoneme programs must see the un-tonic stress so the inherent vowel V laxes to ə.
for _l in ("pa", "ne", "hi"):
    LANGS[_l]["unstress_u_words"] = True
# bn/mr/hi র is the tap ɾ prevocalically and word-finally, but the alveolar trill r in a syllable
# coda before a NON-STOP consonant (ধর্ম -> dʰɔrmɔ, mr चार्वाक -> tʃaːrvaːk, hi नौकरशाह -> ...arʃ...);
# before a stop it stays the tap (bn দরকার -> dɔːɾkɑɾ).
for _l in ("bn", "mr", "hi"):
    LANGS[_l]["coda_trill_r"] = True
# bn: a lengthened retroflex stop renders doubled, not with ː (দশটা -> dɔʃʈʈˈa, not ʈː) —
# the retroflex ʈ/ɖ carries an explicit single-char ipa that espeak's IPA writer repeats.
LANGS["bn"]["double_rfx_stop"] = True
# fo/mt: a geminate rr is the trill r + approximant ɹ (rɹ), not ɹɹ — the first r of the cluster
# trills (fo fyrri -> fɪrɹˈɪ, verri -> ʋɛrɹˈɪ; mt irrespettivament -> ˌirɹespˌetivˈament, arra ->
# ˈarɹaː). Both voices use the same r phoneme whose geminate first segment trills.
LANGS.setdefault("fo", {})["geminate_r_trill"] = True
LANGS.setdefault("mt", {})["geminate_r_trill"] = True
# fo: a word-final `r` after a vowel is the trill `r` only clause-finally; when another word
# follows it weakens to the approximant `ɹ` (ognar -> ɔɡnˈar, but `ognar og` -> ɔɡnˈaɹ ɔˈœː).
# Only surfaces in a multi-word ('_'-joined compound) render, where a non-final word's `r`
# precedes a space.
LANGS["fo"]["word_final_r_approximant"] = True
# fo: a single letter's NAME is case-sensitive — the lowercase l/m/n have no gemination
# (l -> ɛl) but the uppercase L/M/N forms do (L -> ɛll). espeak buckets the two cases
# separately; espyak keys the dict lowercase, so without this the geminated uppercase
# variant wins the lowercase letter lookup.
LANGS["fo"]["case_sensitive_letters"] = True
# fo: the full numbers flag set (tr_languages.c:847). Without an explicit value fo would
# fall back to NUM_HUNDRED_AND, missing NUM_SWAP_TENS — Faroese says the units before the
# tens joined by "og" (36 -> "seks og tríati" -> sɛɡsuotɹeːdɪʋˈʊ, not "tríati seks").
LANGS["fo"]["numbers"] = (
    K.NUM_DECIMAL_COMMA | K.NUM_SWAP_TENS | K.NUM_HUNDRED_AND | K.NUM_OMIT_1_HUNDRED
    | K.NUM_ORDINAL_DOT | K.NUM_1900 | K.NUM_ROMAN | K.NUM_ROMAN_CAPITALS
    | K.NUM_ROMAN_ORDINAL)


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
# Urdu uses the Hindi phoneme table, so a lengthened retroflex stop renders doubled like bn
# (ٹٹو -> ʈʈ, پٹھو -> ʈʰʈʰ), not with ː — the retroflex ʈ/ɖ ipa is repeated by the IPA writer.
LANGS["ur"] = {"stress_rule": K.STRESSPOSN_1RH, "unstress_u_words": True,
               "double_rfx_stop": True,
               # lexical lowercase `r` (ر) is the tap ɾ prevocalically/word-finally, but espeak's
               # `CALL base1/r` does `IF nextPh(isNotVowel) THEN ChangePhoneme(r/)` — before ANY
               # consonant the coda r becomes the trill r/ (ipa r): فرسٹ -> fˈarsʈ, مگرمچھ ->
               # maɡˈarmacʰ. (Uppercase R in the dict is already the trill, ipa r.)
               "coda_trill_r": True}
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

# Quechua: a word-boundary apostrophe is NOT part of the word. espeak's clause reader
# turns a word-final/initial ' into a space before the word reaches dictionary lookup
# (translate.c:1361 — qu sets neither LOPT_APOSTROPHE nor char_plus_apostrophe), so an
# isolated glottalised letter like k' is looked up as bare `k` and spelled (kˈaː), NOT
# matched against the dead `k' k`?a:` _list entry (which would add a spurious glottal stop
# k`ʔ). A word-INTERNAL apostrophe between letters is kept (hayk'a -> hˈajk`ʔa), so the
# ejective cluster still renders where the glyph is genuinely an ejective.
LANGS.setdefault("qu", {})["strip_boundary_apostrophe"] = True

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


# alphabets[] (tr_languages.c:65): maps a Unicode block to its alphabet *_list name key, the
# language to switch to when a character of that block can't be translated by the current
# language, and the espeak AL_* flags. A block with AL_WORDS triggers a WORD-LEVEL phonSWITCH
# to `language` (dictionary.c:2257); range_min/range_max/name/lang/flags mirror the C entries.
AL_DONT_NAME = 0x01
AL_NOT_LETTERS = 0x04
AL_WORDS = 0x10
AL_NOT_CODE = 0x20
AL_NO_SYMBOL = 0x40

# (range_min, range_max, name_key, switch_lang or None, flags)
ALPHABETS = (
    (0x380, 0x3ff, "_el", "el", AL_DONT_NAME | AL_NOT_LETTERS | AL_WORDS),
    (0x400, 0x52f, "_cyr", None, 0),
    (0x530, 0x58f, "_hy", "hy", AL_WORDS),
    (0x590, 0x5ff, "_he", None, 0),
    (0x600, 0x6ff, "_ar", None, 0),
    (0x700, 0x74f, "_syc", None, 0),
    (0x900, 0x97f, "_hi", "hi", AL_WORDS),
    (0x980, 0x9ff, "_bn", "bn", AL_WORDS),
    (0xa00, 0xa7f, "_gur", "pa", AL_WORDS),
    (0xa80, 0xaff, "_gu", "gu", AL_WORDS),
    (0xb00, 0xb7f, "_or", None, 0),
    (0xb80, 0xbff, "_ta", "ta", AL_WORDS),
    (0xc00, 0xc7f, "_te", "te", 0),
    (0xc80, 0xcff, "_kn", "kn", AL_WORDS),
    (0xd00, 0xd7f, "_ml", "ml", AL_WORDS),
    (0xd80, 0xdff, "_si", "si", AL_WORDS),
    (0xe00, 0xe7f, "_th", None, 0),
    (0xe80, 0xeff, "_lo", None, 0),
    (0xf00, 0xfff, "_ti", None, 0),
    (0x1000, 0x109f, "_my", None, 0),
    (0x10a0, 0x10ff, "_ka", "ka", AL_WORDS),
    (0x1100, 0x11ff, "_ko", "ko", AL_WORDS),
    (0x1200, 0x139f, "_eth", None, 0),
    (0x2800, 0x28ff, "_braille", None, AL_NO_SYMBOL),
    (0x3040, 0x30ff, "_ja", None, AL_NOT_CODE),
    (0x3100, 0x9fff, "_zh", None, AL_NOT_CODE),
    (0xa700, 0xd7ff, "_ko", "ko", AL_NOT_CODE | AL_WORDS),
    (0x10450, 0x1047f, "_shaw", "en", 0),
)


def alphabet_from_char(cp):
    """Port of AlphabetFromChar (tr_languages.c:97): the alphabets[] entry whose range
    contains `cp`, or None. Ranges are in ascending order; the first whose range_max >= cp
    either contains cp (range_min <= cp) or falls in an unmapped gap (None)."""
    for lo, hi, name, lang, flags in ALPHABETS:
        if cp <= hi:
            if cp >= lo:
                return (lo, hi, name, lang, flags)
            return None
    return None


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
