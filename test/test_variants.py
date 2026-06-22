"""Sub-dialect VARIANT system end-to-end tests.

A variant (pt-br, en-us, es-419, ca-va, ...) is a voice/lang file that layers a phoneme
table, dictrules and `replace`s over a SHARED base language (pt, en, es, ca). These cases
pin the discriminating words that distinguish each dialect from its base, verified against
espeak-ng 1.52.0 (`espeak-ng -q --ipa -v <variant>`).
"""
import pytest

from espyak.api import G2P

# (variant, base_lang, [(word, expected_ipa), ...])
VARIANT_CASES = [
    # en-us: en-us phoneme table (rhotic ɚ, flapped ɾ) + dictrules 3,6 + `replace 03 I i`
    # (word-final unstressed ɪ -> i). en-gb is the canonical base (identical to plain en).
    ("en-us", "en", [
        ("tomato", "təmˈeɪɾoʊ"),
        ("water", "wˈɔːɾɚ"),
        ("schedule", "skˈɛdʒuːl"),
        ("early", "ˈɜːli"),       # replace 03 I i: final ɪ -> i
        ("amply", "ˈæmpli"),
    ]),
    ("en-gb", "en", [
        ("tomato", "təmˈɑːtəʊ"),
        ("water", "wˈɔːtə"),
        ("schedule", "ʃˈɛdjuːl"),
    ]),
    # pt-br: base pt + dictrules 2 -> d/t -> dʒ/tʃ before [i], final unstressed -> y/æ.
    ("pt-br", "pt", [
        ("dia", "dʒˈiæ"),
        ("tia", "tʃˈiæ"),
        ("verdade", "vˌeɾədˈadʒy"),
    ]),
    # es-419: base es + phonemes es-la (seseo: θ -> s) + dictrules 2.
    ("es-419", "es", [
        ("cielo", "sjˈelo"),
        ("zapato", "sapˈato"),
    ]),
    # Catalan dialects: base ca + ca-va/ca-ba/ca-nw phoneme tables + dictrules.
    ("ca-va", "ca", [("vuit", "vwˈit"), ("casa", "kˈaza")]),
    ("ca-ba", "ca", [("casa", "kˈazə")]),
    ("ca-nw", "ca", [("casa", "kˈazɛ")]),
    # French dialects: all share the base fr translator/table; differ only in synthesis
    # (tunes/dictrules), so the IPA G2P matches base fr.
    ("fr-be", "fr", [("roi", "ʁwˈa")]),
    ("fr-ch", "fr", [("roi", "ʁwˈa")]),
    ("fr-fr", "fr", [("roi", "ʁwˈa")]),
]


@pytest.mark.parametrize("variant,base,cases", VARIANT_CASES,
                         ids=[c[0] for c in VARIANT_CASES])
def test_variant_words(variant, base, cases):
    g = G2P(variant)
    assert g._base_lang == base, "%s should load base language %s" % (variant, base)
    for word, ipa in cases:
        assert g.phonemize(word) == ipa, "%s %r" % (variant, word)


def test_variant_loads_base_rules_not_variant_file():
    """A variant has no <code>_rules dict; it must load the BASE language's rules/dict."""
    g = G2P("pt-br")
    assert g._base_lang == "pt"
    # the variant code is preserved for output language tagging
    assert g.lang == "pt-br"


def test_base_language_unaffected_by_variant_path():
    """Requesting a base language directly resolves base_lang == itself (no variant)."""
    for code in ("en", "es", "pt", "ca", "fr", "ru"):
        g = G2P(code)
        assert g._base_lang == code
        assert not g._voice_cfg.is_variant
