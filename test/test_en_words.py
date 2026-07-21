"""Common-word end-to-end tests (dictionary + 2-letter groups + stress).

Expected values from espeak-ng 1.52.0; re-verified against the live binary.
"""
import pytest

from espyak.api import G2P

# (word, expected_ipa) — common English words, verified vs oracle
CASES = [
    ('time', 'tˈaɪm'),
    ('people', 'pˈiːpəl'),
    ('way', 'wˈeɪ'),
    ('day', 'dˈeɪ'),
    ('thing', 'θˈɪŋ'),
    ('world', 'wˈɜːld'),
    ('school', 'skˈuːl'),
    ('student', 'stjˈuːdənt'),
    ('group', 'ɡɹˈuːp'),
    ('country', 'kˈʌntɹi'),
    ('problem', 'pɹˈɒbləm'),
    ('part', 'pˈɑːt'),
    ('company', 'kˈʌmpəni'),
    ('system', 'sˈɪstəm'),
    ('program', 'pɹˈəʊɡɹam'),
    ('work', 'wˈɜːk'),
    ('number', 'nˈʌmbə'),
    ('night', 'nˈaɪt'),
    ('water', 'wˈɔːtə'),
    ('room', 'ɹˈuːm'),
    ('mother', 'mˈʌðə'),
    ('story', 'stˈɔːɹi'),
    ('month', 'mˈʌnθ'),
    ('book', 'bˈʊk'),
    ('word', 'wˈɜːd'),
    ('house', 'hˈaʊs'),
    ('friend', 'fɹˈɛnd'),
    ('father', 'fˈɑːðə'),
    ('power', 'pˈaʊə'),
    ('member', 'mˈɛmbə'),
    ('car', 'kˈɑː'),
    ('team', 'tˈiːm'),
]


@pytest.fixture(scope="module")
def g2p():
    return G2P("en")


@pytest.mark.parametrize("word,ipa", CASES)
def test_common_word_ipa(g2p, word, ipa):
    assert g2p.phonemize(word) == ipa


@pytest.mark.parametrize("word,ipa", CASES)
def test_common_word_matches_oracle(oracle, g2p, word, ipa):
    assert g2p.phonemize(word) == oracle(word, "en", "ipa")


SYMBOL_NAMES = [
    ("£", "pˈaʊnd"),
    ("°", "dɪɡɹˈiːz"),
    ("+", "plˈʌs"),
    ("€", "jˈʊəɹəʊz"),
    ("¥", "jˈɛn"),
    ("§", "sˈɛkʃən"),
]


@pytest.mark.parametrize("sym,ipa", SYMBOL_NAMES)
def test_symbol_names_from_emoji_dict(sym, ipa):
    assert G2P("en", force_compat=True).phonemize(sym) == ipa
