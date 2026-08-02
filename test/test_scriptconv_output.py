"""Multi-notation output via scriptconv, and the shared Kirshenbaum table."""
import pytest
from espyak import G2P


@pytest.fixture(scope="module")
def en():
    return G2P("en")


def test_default_and_ipa_flag_unchanged(en):
    # Back-compat: the alphabet parameter defaults to IPA / the ipa flag.
    ref_ipa = en.phonemize("hello world")
    assert en.phonemize("hello world", alphabet="ipa") == ref_ipa
    ref_kirsh = en.phonemize("hello world", ipa=False)
    assert en.phonemize("hello world", alphabet="kirshenbaum") == ref_kirsh


def test_xsampa_output(en):
    # IPA həlˈəʊ wˈɜːld → X-SAMPA: @ = ə, " = ˈ, 3: = ɜː
    out = en.phonemize("hello world", alphabet="x-sampa")
    assert out == 'h@l"@U w"3:ld'


def test_lexique_schwa(en):
    # Lexique renders ə as ° (its schwa symbol).
    out = en.phonemize("hello world", alphabet="lexique")
    assert "°" in out
    assert "ə" not in out


def test_arpa_output_is_token_separated(en):
    out = en.phonemize("hello world", alphabet="arpa")
    # ARPABET is space-separated uppercase tokens.
    assert out.upper() == out
    assert " " in out


def test_unknown_alphabet_raises(en):
    with pytest.raises(ValueError):
        en.phonemize("hello", alphabet="bogus")


def test_kirshenbaum_table_matches_scriptconv():
    # The rebuilt _IPA1 must equal espeak-ng's verbatim dictionary.c ipa1[96].
    from espyak.render import _IPA1
    expected = [
        0x20, 0x21, 0x22, 0x2b0, 0x24, 0x25, 0x0e6, 0x2c8, 0x28, 0x29, 0x27e, 0x2b, 0x2cc, 0x2d, 0x2e, 0x2f,
        0x252, 0x31, 0x32, 0x25c, 0x34, 0x35, 0x36, 0x37, 0x275, 0x39, 0x2d0, 0x2b2, 0x3c, 0x3d, 0x3e, 0x294,
        0x259, 0x251, 0x3b2, 0xe7, 0xf0, 0x25b, 0x46, 0x262, 0x127, 0x26a, 0x25f, 0x4b, 0x26b, 0x271, 0x14b, 0x254,
        0x3a6, 0x263, 0x280, 0x283, 0x3b8, 0x28a, 0x28c, 0x153, 0x3c7, 0xf8, 0x292, 0x32a, 0x5c, 0x5d, 0x5e, 0x5f,
        0x60, 0x61, 0x62, 0x63, 0x64, 0x65, 0x66, 0x261, 0x68, 0x69, 0x6a, 0x6b, 0x6c, 0x6d, 0x6e, 0x6f,
        0x70, 0x71, 0x72, 0x73, 0x74, 0x75, 0x76, 0x77, 0x78, 0x79, 0x7a, 0x7b, 0x7c, 0x7d, 0x303, 0x7f,
    ]
    assert _IPA1 == expected
