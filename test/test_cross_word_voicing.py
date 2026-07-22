"""Clause-level regressive voicing assimilation, and the LOPT_REDUCE&2 stress condition.

espeak-ng runs ``SetRegressiveVoicing`` ONCE over the whole clause phoneme list
(``phonemelist.c:214-216``), after the words of the clause have been concatenated. A
word-final obstruent therefore sees the FOLLOWING word's initial consonant and assimilates
to its voicing: Polish ``plik zapisany`` -> ``plˈiɡ zˌapisˈanɨ``. A per-word pass cannot see
that context.

Whether the assimilation crosses the boundary is decided entirely by the language's
``LOPT_REGRESSIVE_VOICING`` bits, not by a list of languages:

* bit ``0x04`` resets the voicing accumulator at a word start, so Bulgarian (``0x107``)
  keeps each word's citation form;
* a value with an empty low nibble (German/Dutch/Maltese ``0x100``) performs no
  assimilation at all — only word-final devoicing;
* a consonant only switches if it HAS a ``voicingswitch`` partner, and
  ``ImportPhoneme`` (``compiledata.c:1726-1727``) clears that field for an imported
  consonant, which is why Russian ``кот дом`` stays ``kˈot dˈom`` (``t`` imports ``pl/t``)
  while ``наш дом`` voices to ``nˈaʒ dˈom`` (``S`` is defined locally).

The second mechanism here is ``langopts.param[LOPT_REDUCE] = 2`` (bg, is, ru): in
``StressCondition`` (``synthdata.c:434-437``) a syllable at the word's own maximum stress
level counts as PRIMARY, so ``ChangeIfNotStressed``/``ChangeIfUnstressed`` reductions never
fire on it. Icelandic ``var`` therefore keeps its long vowel even when the clause gives it
no stress mark at all.

Every expectation was captured from the espeak-ng 1.52.0 oracle and is re-verified against
the live binary by the oracle-gated tests.
"""
import pytest

from espyak.api import G2P


_G2P = {}


def g2p(lang):
    if lang not in _G2P:
        _G2P[lang] = G2P(lang, force_compat=True)
    return _G2P[lang]


# (lang, text, expected_ipa)
CROSS_WORD = [
    # --- assimilation crosses the boundary (no 0x04 bit, non-empty low nibble) ---
    ("pl", "plik zapisany", "plˈiɡ zˌapisˈanɨ"),   # k -> ɡ before z
    ("pl", "kot duży",      "kˈɔd dˈuʒɨ"),          # t -> d before d
    ("cs", "byt dobry",     "bˈid dˈobri"),
    ("sk", "byt dobry",     "bˈid dˈobri"),
    ("sr", "rat bio",       "rˈad bˌɪo"),
    ("hr", "rat bio",       "ɾˈad bˌɪo"),
    ("bs", "rat bio",       "ɾˈad bˌɪo"),
    ("sl", "rak bo",        "rˈaːɡ bˈoː"),
    ("uk", "кіт добрий",    "kˈiːd̪ dˈobrɪj"),
    ("ru", "наш дом",       "nˈɑʒ dˈom"),           # S has a local voicingswitch
    # --- adversarial: a VOICELESS onset must leave the previous word alone ---
    ("pl", "plik tekstowy", "plˈik tɛkstˈɔvɨ"),
    ("pl", "dom biały",     "dˈɔm bjˈawɨ"),         # nasal coda: nothing to assimilate
    ("cs", "byt tichy",     "bˈit cˈixi"),
    ("sk", "byt tichy",     "bˈit tʲˈixi"),
    ("sr", "rat pao",       "rˈat pˈao"),
    ("hr", "rat pao",       "ɾˈat pˈao"),
    ("bs", "rat pao",       "ɾˈat pˈao"),
    ("sl", "rak po",        "rˈaːk pˈoː"),
    ("uk", "кіт тихий",     "kˈiːt̪ t̪ˈɪxɪj"),
    # --- adversarial: languages where the C explicitly does NOT carry voicing across ---
    ("bg", "код там",       "kˈot tˈam"),           # 0x107: bit 0x04 resets at a word start
    ("bg", "сад дома",      "sˈat dˈomɐ"),          # ...even before a voiced onset
    ("be", "код там",       "kˈɔt tˈam"),
    ("ru", "кот дом",       "kˈot dˈom"),           # imported t: no voicingswitch
    ("ru", "раз два",       "rˈɑs dvˈɑ"),           # ru s is redefined without a switch
    ("ru", "так делать",    "tˈɑk dʲˈeɭʌtʲ"),       # imported k: no voicingswitch
    ("de", "tag baum",      "tˈɑːk bˈaʊm"),         # 0x100: devoicing only, no assimilation
    ("nl", "kat boom",      "kˈɑt bˈoːm"),
]


@pytest.mark.parametrize("lang,text,ipa", CROSS_WORD)
def test_cross_word_voicing(lang, text, ipa):
    assert g2p(lang).phonemize(text) == ipa


@pytest.mark.parametrize("lang,text,ipa", CROSS_WORD)
def test_cross_word_voicing_matches_oracle(oracle, lang, text, ipa):
    assert g2p(lang).phonemize(text) == oracle(text, lang, "ipa")


def test_word_internal_voicing_unchanged_by_the_clause_pass():
    # The clause pass rewrites a phoneme only where the neighbouring word makes a difference,
    # so a word's internal assimilation must be identical alone and inside a clause.
    pl = g2p("pl")
    assert pl.phonemize("wgrał") in pl.phonemize("stlą wgrał")
    cs = g2p("cs")
    assert cs.phonemize("však") == "fʃˈak"         # word-internal v-devoicing, untouched
    assert cs.phonemize("však ano").startswith("fʃ")


REDUCE_MAX_STRESS = [
    # is: a: -> a (ChangeIfNotStressed) must NOT fire on the word's own peak syllable, so an
    # unstressed `var` keeps its long vowel inside a clause.
    ("is", "var",                "ʋˈaːr"),
    ("is", "skráin var vistuð",  "sɡərˈaʊːɪn ʋaːr ʋˈɪsdyð"),
    ("is", "var vistuð",         "ʋaːr ʋˈɪsdyð"),
    ("is", "bar var",            "bˈaːr ʋaːr"),
    ("is", "var og",             "ʋaːr ˈɔːx"),
    # adversarial: length that the RULES never produced must not appear — a vowel before a
    # consonant cluster is short whether the word is stressed or not.
    ("is", "barn",               "bˈardn#"),
    ("is", "varr",               "ʋˈarɾr"),
    ("is", "fara heim",          "fˈaːɾra hˈeɪːm"),
]


@pytest.mark.parametrize("lang,text,ipa", REDUCE_MAX_STRESS)
def test_reduce_max_stress(lang, text, ipa):
    assert g2p(lang).phonemize(text) == ipa


@pytest.mark.parametrize("lang,text,ipa", REDUCE_MAX_STRESS)
def test_reduce_max_stress_matches_oracle(oracle, lang, text, ipa):
    assert g2p(lang).phonemize(text) == oracle(text, lang, "ipa")


def test_imported_consonant_loses_its_voicing_switch():
    # compiledata.c:1726-1727 — ImportPhoneme clears end_type (the voicingswitch slot) for a
    # consonant, so ru's imported t/k/s have no voicing partner while its own S does.
    tab = g2p("ru").phoneme_table
    assert tab.get("t").voicing_switch is None     # import_phoneme pl/t
    assert tab.get("k").voicing_switch is None     # import_phoneme consonants/k-
    assert tab.get("s").voicing_switch is None     # redefined locally, no voicingswitch line
    assert tab.get("S").voicing_switch == "Z"      # defined locally WITH a voicingswitch
    assert g2p("pl").phoneme_table.get("t").voicing_switch == "d"
