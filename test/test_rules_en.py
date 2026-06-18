"""End-to-end English letter-to-sound + stress tests via the rule engine.

These words are chosen to exercise the *rules* path (not the `_list` dictionary,
which is not yet wired). Expected values are from the espeak-ng 1.52.0 oracle and
re-verified against the live binary when available.

Known remaining gaps (tracked in the repo plan) that this suite deliberately avoids:
  - within-group rule sort tie-ordering (e.g. ng->ŋ, er->ɜː)
  - syllabic-l rendering (əl) which needs the phoneme-program pass
  - the `_list` dictionary lookup (most real words)
"""
import pytest

from espyak.api import G2P

# (word, expected_ipa) — verified vs espeak-ng 1.52.0
CASES = [
    ("splosh", "splˈɒʃ"),
    ("frenge", "fɹˈɛndʒ"),
    ("quint", "kwˈɪnt"),
    ("glomp", "ɡlˈɒmp"),
    ("trisk", "tɹˈɪsk"),
    ("skemp", "skˈɛmp"),
    ("crelt", "kɹˈɛlt"),
]


@pytest.fixture(scope="module")
def g2p():
    return G2P("en")


@pytest.mark.parametrize("word,ipa", CASES)
def test_rules_ipa(g2p, word, ipa):
    assert g2p.phonemize(word) == ipa


@pytest.mark.parametrize("word,ipa", CASES)
def test_rules_match_oracle(oracle, g2p, word, ipa):
    assert g2p.phonemize(word) == oracle(word, "en", "ipa")
