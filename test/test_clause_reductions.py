"""Clause-level cross-word post-processing: function-word reduction, en linking/intrusive r,
and nl homorganic-stop degemination.

espeak resolves these over its clause-level phoneme list, using state that a per-word render
otherwise loses (the previous word's final phoneme + spelling, the next word's onset, and each
word's clause position). Three effects are exercised here:

1. `$atend`-gated function words (en `has`, `a`, `the`, `to`, `of`) reduce mid-clause and only
   keep their strong `$atend` pronunciation when they carry the clause tonic (are clause-final).
2. en linking/intrusive r: a word ending in a schwa-family vowel or ɑː (intrusive), or spelled
   with a final 'r' after ɔː/ɜː (linking), restores a ɹ before a following vowel-initial word.
3. nl t/d/p/b assimilate to a null pause before a homorganic word-initial stop (ph_dutch `!`),
   unless a `$brk` word (`te`) mid-clause splits the two stops apart.

All expected values are from the espeak-ng 1.52.0 oracle and re-checked against the live binary
by ``test_matches_oracle`` when the vendored oracle is built.
"""
import pytest

from espyak.api import G2P

# (lang, text, expected_ipa) — all verified byte-for-byte against espeak-ng 1.52.0
CASES = [
    # --- 1. function-word reduction mid-clause ($atend gating) ---
    ("en", "has saved", "hɐz sˈeɪvd"),                    # `has` not tonic -> reduced %ha#z
    ("en", "it has been a day", "ɪt hˈazbiːn ɐ dˈeɪ"),    # `a` mid-clause -> ɐ (not ˈeɪ)
    ("en", "a=b", "ɐ ˈiːkwəlz bˈiː"),                     # `a` before the symbol word -> ɐ
    ("en", "he has a book", "hiː hɐz ɐ bˈʊk"),
    ("en", "she has been there", "ʃiː hˈazbiːn ðˈeə"),
    ("en", "the cat sat on a mat", "ðə kˈat sˈat ˌɒn ɐ mˈat"),
    ("en", "in a hurry", "ɪn ɐ hˈʌɹi"),
    ("en", "on a roll", "ˌɒn ɐ ɹˈəʊl"),
    # adversarial: a lone / clause-final $u word STAYS strong (it carries the clause tonic)
    ("en", "a", "ˈeɪ"),
    ("en", "has", "hˈaz"),
    ("en", "the", "ðˈə"),
    ("en", "been", "bˈiːn"),
    ("en", "has a", "hɐz ˈeɪ"),                           # final `a` tonic -> ˈeɪ; `has` reduced

    # --- 2. en linking / intrusive r ---
    ("en", "tilde ex", "tˈɪldəɹ ˈɛks"),                   # intrusive: ə + vowel
    ("en", "comma apple", "kˈɒməɹ ˈapəl"),
    ("en", "here it is", "hˈiəɹ ɪt ˈɪz"),                 # centring diphthong ends in ə
    ("en", "where it is", "wˌeəɹ ɪt ˈɪz"),
    ("en", "for it", "fɔːɹ ˈɪt"),                         # linking: spelled 'r', ɔː
    ("en", "her own", "hɜːɹ ˈəʊn"),                       # linking: spelled 'r', ɜː
    ("en", "four or five", "fˈɔːɹ ɔː fˈaɪv"),
    ("en", "more or less done", "mˈɔːɹ ɔː lˈɛs dˈʌn"),    # 're' spelling counts as final 'r'
    ("en", "sofa or chair", "sˈəʊfəɹ ɔː tʃˈeə"),
    # adversarial: NO r before a consonant, and NO intrusive r after ɔː without a spelled 'r'
    ("en", "tilde box", "tˈɪldə bˈɒks"),
    ("en", "comma box", "kˈɒmə bˈɒks"),
    ("en", "car box", "kˈɑː bˈɒks"),
    ("en", "here box", "hˈiə bˈɒks"),
    ("en", "saw box", "sˈɔː bˈɒks"),
    ("en", "draw a picture", "dɹˈɔː ɐ pˈɪktʃə"),          # `draw` (ɔː, no 'r') -> no r
    ("en", "law and order", "lˈɔː and ˈɔːdə"),            # `law` (ɔː, no 'r') -> no r

    # --- 3. nl homorganic-stop degemination ---
    ("nl", "kost twintig", "kˈɔs tʋˈɪntəx"),              # final t drops before initial t
    ("nl", "wat dat is", "ʋɑ tɑt ˈɪs"),                   # t drops, following d devoices to t
    ("nl", "dat toen kwam", "dɑ tˈun kʋˈɑm"),
    ("nl", "op poten", "ɔ pˈoːtən"),                      # labial p drops before p
    ("nl", "heb boter", "hɛ pˈoːtər"),                    # final b (devoiced p) drops before b
    ("nl", "wat te", "ʋɑ tˈə"),                           # $brk word `te`, but clause-final -> drops
    # adversarial: a $brk `te` MID-clause keeps the preceding stop; non-homorganic pairs untouched
    ("nl", "wat te doen", "ʋɑt tə dˈun"),
    ("nl", "niet te doen", "nˌit tə dˈun"),
    ("nl", "kook koek", "kˈoːk kˈuk"),                    # k+k is not degeminated
    ("nl", "dag geven", "dˈɑx ɣˈeːvən"),
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
