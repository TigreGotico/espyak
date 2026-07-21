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


SYMBOL_SPLIT = [
    ("£5", "pˈaʊnd fˈaɪv"),
    ("€10", "jˈʊəɹəʊz tˈɛn"),
    ("20°", "twˈɛnti dɪɡɹˈiːz"),
    ("5+3", "fˈaɪv plˈʌs θɹˈiː"),
    ("$5", "dˈɒlə fˈaɪv"),
    ("5$", "fˈaɪv dˈɒlə"),
    ("5=5", "fˈaɪv ˈiːkwəlz fˈaɪv"),
    ("99%", "nˈaɪnti nˈaɪn pəsˈɛnt"),
    ("5<6", "fˈaɪv sˈɪks"),
    ("7>2", "sˈɛvən tˈuː"),
    ("it costs £5 and 20°", "ɪt kˈɒsts pˈaʊnd fˈaɪv and twˈɛnti dɪɡɹˈiːz"),
    ("©2020", "kˈɒpɪɹˌaɪt tˈuː θˈaʊzənd ən twˈɛnti"),
]


@pytest.mark.parametrize("text,ipa", SYMBOL_SPLIT)
def test_symbols_split_from_adjacent_words(text, ipa):
    assert G2P("en", force_compat=True).phonemize(text) == ipa


SYMBOL_RUNS = [
    ("€€", "jˈʊəɹəʊzjˈʊəɹəʊz"),
    ("€€£", "jˈʊəɹəʊzjˈʊəɹəʊzpˈaʊnd"),
    ("+-", "plˈʌs"),
]


@pytest.mark.parametrize("text,ipa", SYMBOL_RUNS)
def test_adjacent_symbol_runs_glue(text, ipa):
    assert G2P("en", force_compat=True).phonemize(text) == ipa
