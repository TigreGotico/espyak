"""Pilot-language end-to-end tests (eo, es) — validates multilingual config.

Expected values from espeak-ng 1.52.0; re-verified vs the live binary.
"""
import pytest

from espyak.api import G2P

EO_CASES = [
    ('anst', 'anstˈataʊ'),
    ('apud', 'ˈapud'),
    ('post', 'pˈost'),
    ('plej', 'plˈeɪ'),
    ('ilia', 'ilˈia'),
    ('miaj', 'mˈiaɪ'),
    ('ciaj', 'tsˈiaɪ'),
    ('liaj', 'lˈiaɪ'),
    ('niaj', 'nˈiaɪ'),
    ('viaj', 'vˈiaɪ'),
    ('iliaj', 'ilˈiaɪ'),
    ('siaj', 'sˈiaɪ'),
    ('esti', 'ˈesti'),
    ('estas', 'ˈestas'),
    ('estis', 'ˈestis'),
    ('estos', 'ˈestos'),
    ('estus', 'ˈestus'),
    ('povas', 'pˈovas'),
]

ES_CASES = [
    ('nuestro', 'nwˈestɾo'),
    ('nuestros', 'nwˈestɾos'),
    ('nuestra', 'nwˈestɾa'),
    ('nuestras', 'nwˈestɾas'),
    ('vuestro', 'bwˈestɾo'),
    ('vuestros', 'bwˈestɾos'),
    ('vuestra', 'bwˈestɾa'),
    ('vuestras', 'bwˈestɾas'),
    ('tras', 'tɾˈas'),
    ('ante', 'ˈante'),
    ('para', 'pˈaɾa'),
    ('entre', 'ˈɛntɾe'),
    ('sobre', 'sˈoβɾe'),
    ('bajo', 'bˈaxo'),
    ('desde', 'dˈesðe'),
    ('hasta', 'ˈasta'),
    ('hacia', 'ˈaθja'),
    ('aunque', 'ˈaʊnke'),
]

@pytest.mark.parametrize("lang,cases", [("eo", EO_CASES), ("es", ES_CASES)])
def test_pilot_language(oracle, lang, cases):
    g = G2P(lang)
    for word, ipa in cases:
        assert g.phonemize(word) == ipa
        assert g.phonemize(word) == oracle(word, lang, "ipa")
