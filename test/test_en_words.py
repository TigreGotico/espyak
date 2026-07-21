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


# espeak's clause reader breaks a word at a letter<->punctuation boundary (translate.c:1182) and
# spells the isolated punctuation by its character name — like symbols, but for category-P chars
# such as '#' (hash) and ':' (colon). A ':' directly against a digit stays in the token for the
# number path (time/range), so only a letter-adjacent one peels off.
LETTER_PUNCT_SPLIT = [
    ("c#", "sˈiː hˈaʃ"),
    ("a#b", "ɐ hˈaʃ bˈiː"),
    ("5#", "fˈaɪv hˈaʃ"),
    ("c:d", "sˈiː kˈəʊlən dˈiː"),
    ("a:b", "ɐ kˈəʊlən bˈiː"),
    ("12:30", "twˈɛlv θˈɜːti"),  # digit-adjacent ':' NOT peeled — stays for the time rules
]


@pytest.mark.parametrize("text,ipa", LETTER_PUNCT_SPLIT)
def test_letter_punctuation_splits_and_spells(text, ipa):
    assert G2P("en", force_compat=True).phonemize(text) == ipa


# Same letter<->punctuation break across languages: the ':' genitive/abbreviation marker peels off
# (sv usa:s -> the ':' is dropped, 's' spelled ˈɛs; hu splits ÁFAa:fA at the ':'), a subscript digit
# is read as its number name (ca co₂ -> 'co' + ₂ -> "dos"), and ca's in-word middle dot is kept.
MULTILANG_PUNCT_SPLIT = [
    ("sv", "usa:s", "ˌʉɛsˈɑː ˈɛs"),
    ("hu", "ÁFAa:fA", "ˈaːfɑɑ ˈɛff ˈɑː"),
    ("ca", "co₂", "kˈɔ ðˈos"),
    ("ca", "col·legi", "kullˈɛʒi"),
]


@pytest.mark.parametrize("lang,text,ipa", MULTILANG_PUNCT_SPLIT)
def test_letter_punctuation_splits_multilang(lang, text, ipa):
    import unicodedata
    got = unicodedata.normalize("NFC", G2P(lang, force_compat=True).phonemize(text))
    assert got == ipa
