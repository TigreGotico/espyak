"""Digit-adjacent time / range / sign punctuation across languages.

espeak-ng isolates a ':' or '-' that sits next to digits as its own clause token, so
the digit-context letter-to-sound rules fire across the word boundary: a time colon is
omitted (``D_) : (_DD_``) — or spoken as the language's connector (de "Uhr") — a hyphen
between two numbers is a "dash"/"Strich"/dropped, and a leading hyphen before a number is
a "minus". Each language supplies its own phonemes; nothing here is hard-coded per case.

Expected values are from the espeak-ng 1.52.0 oracle and re-checked against the live
binary by ``test_matches_oracle`` when the vendored oracle is built.
"""
import pytest

from espyak.api import G2P

# (lang, text, expected_ipa) — all verified against espeak-ng 1.52.0
CASES = [
    # --- times: colon omitted (en/nl/es/fr) or spoken as a connector (de "Uhr") ---
    ("en", "2:30", "tˈuː θˈɜːti"),
    ("en", "12:30", "twˈɛlv θˈɜːti"),
    ("en", "09:05", "nˈaɪn zˈiəɹəʊ fˈaɪv"),          # 1st group drops leading 0, later group speaks it
    ("en", "23:59", "twˈɛnti θɹˈiː fˈɪfti nˈaɪn"),
    ("en", "12:30:45", "twˈɛlv θˈɜːti fˈɔːti fˈaɪv"),
    ("de", "12:30", "tsvˈœlf uːɾ dɾˈaɪsɪç"),
    ("de", "2:30", "tsvˈaɪ uːɾ dɾˈaɪsɪç"),
    ("de", "09:05", "nˈɔøn uːɾ nˈʊl fˈʏnf"),
    ("nl", "12:30", "tʋˈaːlf dˈɛrtəx"),
    ("es", "12:30", "dˈoθe tɾˈeɪnta"),
    ("es", "09:05", "nwˈeβe θˈeɾo θˈinko"),
    ("fr", "12:30", "dˈuz ˈœʁ tʁˈɑ̃t"),
    ("fr", "12:30:45", "dˈuz ˈœʁ tʁˈɑ̃t kaʁɑ̃tsˈɛ̃k"),
    # --- ranges: hyphen between two numbers is "dash" (dropped in es) ---
    ("en", "3-4", "θɹˈiː dˈaʃ fˈɔː"),
    ("en", "10-20", "tˈɛn dˈaʃ twˈɛnti"),
    ("en", "1-2-3", "wˈɒn dˈaʃ tˈuː dˈaʃ θɹˈiː"),
    ("de", "3-4", "dɾˈaɪ ʃtɾˈɪç fˈiːɾ"),
    ("de", "1-2-3", "ˈaɪns ʃtɾˈɪç tsvˈaɪ ʃtɾˈɪç dɾˈaɪ"),
    ("nl", "3-4", "drˈi vˈir"),
    ("nl", "1-2-3", "ˈeːn tʋˈeː drˈi"),
    ("es", "3-4", "tɾˈes kwˈatɾo"),
    ("es", "1-2-3", "ˈuno ðˈos tɾˈes"),
    ("fr", "3-4", "tʁwˈa kˈatʁ"),
    ("fr", "1-2-3", "ˈœ̃ dˈø tʁwˈa"),
    # --- leading hyphen before a number is "minus" ---
    ("en", "-5", "mˈaɪnəs fˈaɪv"),
    ("en", "-12", "mˈaɪnəs twˈɛlv"),
    ("de", "-5", "mˈiːnʊs fˈʏnf"),
    ("nl", "-5", "mˈɪn vˈɛɪf"),
    ("nl", "-12", "mˈɪn tʋˈaːlf"),
    # --- adversarial neighbours ---
    ("en", "12:", "twˈɛlv"),        # trailing colon dropped (no following group)
    ("de", "12:", "tsvˈœlf"),
    ("en", ":30", "kˈəʊlən θˈɜːti"),   # leading colon: no digit before -> spoken "colon"
    ("nl", ":30", "dˈɛrtəx"),
    ("en", "3-", "θɹˈiː"),          # trailing hyphen dropped
    ("en", "-x", "ˈɛks"),           # hyphen before a letter is not a minus
    ("en", "3--4", "θɹˈiː fˈɔː"),   # double hyphen is a pause, not a minus
    ("de", "3--4", "dɾˈaɪ fˈiːɾ"),
    ("en", "30:a", "θˈɜːti kˈəʊlən ˈeɪ"),   # colon before a letter is spoken
    ("nl", "30:a", "dˈɛrtəx ˈaː"),
    ("de", "a:30", "ˈɑː dɾˈaɪsɪç"),
    ("en", "12:30pm", "twˈɛlv θˈɜːti pˌiːˈɛm"),
    ("fr", "12:30pm", "dˈuz ˈœʁ tʁˈɑ̃t pˌeˈɛm"),
]


@pytest.fixture(scope="module")
def g2p_cache():
    cache = {}

    def get(lang):
        if lang not in cache:
            cache[lang] = G2P(lang)
        return cache[lang]

    return get


@pytest.mark.parametrize("lang,text,ipa", CASES)
def test_ipa(g2p_cache, lang, text, ipa):
    assert g2p_cache(lang).phonemize(text) == ipa


@pytest.mark.parametrize("lang,text,ipa", CASES)
def test_matches_oracle(oracle, g2p_cache, lang, text, ipa):
    assert g2p_cache(lang).phonemize(text) == oracle(text, lang, "ipa")
