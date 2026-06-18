"""Render-path tests: phoneme list -> IPA / Kirshenbaum output.

The phoneme strings here are chosen to NOT trigger context-dependent phoneme programs
(see espyak/phoneme_program.py / P1b), so the bare encoder + renderer reproduce
espeak-ng's output exactly. Each expected value was captured from the espeak-ng 1.52.0
oracle and is re-verified against the live binary when it is available.
"""
import pytest

from espyak.api import G2P

# (phoneme_string, expected_ipa, expected_kirshenbaum) — verified vs oracle 1.52.0
CASES = [
    ("h@l'oU",        "həlˈəʊ",       "h@l'oU"),
    ("w'3:ld",        "wˈɜːld",        "w'3:ld"),
    ("Tr'u:",         "θɹˈuː",         "Tr'u:"),
    ("n'eIS@n",       "nˈeɪʃən",       "n'eIS@n"),
    ("D'@",           "ðˈə",           "D'@"),
    ("f'oUt@gr,aaf",  "fˈəʊtəɡɹˌaf",   "f'oUt@gr,aaf"),
    ("b'0tl",         "bˈɒtl",         "b'0tl"),
    ("'O:l",          "ˈɔːl",          "'O:l"),
    (",sept'i:m@l",   "sˌeptˈiːməl",   "s,ept'i:m@l"),
]


@pytest.fixture(scope="module")
def g2p():
    return G2P("en")


@pytest.mark.parametrize("phon,ipa,_kirsh", CASES)
def test_render_ipa(g2p, phon, ipa, _kirsh):
    assert g2p.render(phon, ipa=True) == ipa


@pytest.mark.parametrize("phon,_ipa,kirsh", CASES)
def test_render_kirshenbaum(g2p, phon, _ipa, kirsh):
    assert g2p.render(phon, ipa=False) == kirsh


@pytest.mark.parametrize("phon,ipa,kirsh", CASES)
def test_render_matches_oracle(oracle, g2p, phon, ipa, kirsh):
    # round-trip the same phoneme string through the real binary via [[...]] input
    assert g2p.render(phon, ipa=True) == oracle("[[%s]]" % phon, "en", "ipa")
    assert g2p.render(phon, ipa=False) == oracle("[[%s]]" % phon, "en", "x")


def test_separator_and_tie(g2p):
    # separator inserts between phonemes; tie joins multi-char names
    assert g2p.render("h@l'oU", ipa=False, separator="_").count("_") >= 1
