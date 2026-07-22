"""Clause intonation-nucleus placement (espeak CalcPitches / count_pitch_vowels).

espeak places the clause tonic on the LAST syllable at the highest stress level of the clause;
trailing unstressed ($u) function words after a stronger word are POST-NUCLEAR and keep their
reduced form. A $strend/$strend2 word (SFLAG_PROMOTE_STRESS, "full stress if at clause end") is a
nucleus candidate even when its own render is reduced, so a clause-final promotable word still
takes the tonic. A single word is its own nucleus.

The same $pause (FLAG_PREPAUSE) mechanism inserts a short pause before `and`/`or`/`but`/`nor`
when they are neither the first two nor the last word of the clause (translate.c:469); that pause
blocks the en linking/intrusive ɹ from the preceding word.

All expected values are from the espeak-ng 1.52.0 oracle and re-checked against the live binary
by ``test_matches_oracle`` when the vendored oracle is built.
"""
import pytest

from espyak.api import G2P

# (lang, text, expected_ipa) — verified byte-for-byte against espeak-ng 1.52.0
CASES = [
    # --- trailing $u function word is post-nuclear: nucleus stays on the content word ---
    ("en", "more or", "mˈɔːɹ ɔː"),          # `or` ($u $pause) post-nuclear, reduces
    ("en", "law and", "lˈɔː and"),
    ("en", "saw it", "sˈɔː ɪt"),
    ("en", "law is", "lˈɔː ɪz"),
    ("en", "this or that", "ðɪs ɔː ðˈat"),   # medial $u `or` reduces; nucleus on final `that`
    ("en", "up and down", "ˌʌp and dˈaʊn"),  # `up` pre-nuclear secondary; nucleus on `down`
    ("en", "out of it", "ˈaʊtəv ɪt"),        # trailing `it` reduced; nucleus stays on `out of`
    ("en", "one of us", "wˈɒn ɒv ˌʌs"),      # `us` ends SECONDARY (post-nuclear), not primary
    ("en", "all of us", "ˈɔːl ɒv ˌʌs"),
    ("en", "none of them", "nˈɒn ɒv ðˌɛm"),
    ("en", "part of it", "pˈɑːt ɒv ɪt"),
    ("nl", "kat de", "kˈɑ tə"),              # trailing `de` reduces; `kat` keeps the nucleus

    # --- $strend/$strend2 promotable word: clause-final, takes the tonic even when reduced base ---
    ("en", "she has been there", "ʃiː hˈazbiːn ðˈeə"),  # `there` $strend2 -> promoted final nucleus
    ("en", "where is the", "wˈeəɹ ɪz ðə"),   # `where` $strend2 -> nucleus; `is`,`the` reduce

    # --- single word is its own nucleus (isolated renders unchanged) ---
    ("en", "the", "ðˈə"),
    ("en", "or", "ˈɔː"),
    ("en", "and", "ˈand"),
    ("en", "us", "ˈʌs"),
    ("en", "it", "ˈɪt"),

    # --- $pause word blocks incoming linking/intrusive ɹ, position-gated ---
    ("en", "sofa or chair", "sˈəʊfəɹ ɔː tʃˈeə"),         # `or` is word 2 -> no pause -> ɹ links
    ("en", "four or five", "fˈɔːɹ ɔː fˈaɪv"),
    ("en", "more or less done", "mˈɔːɹ ɔː lˈɛs dˈʌn"),
    ("en", "the sofa and the chair", "ðə sˈəʊfə and ðə tʃˈeə"),  # `and` word 3 -> pause -> no ɹ
    ("en", "the spa or the sea", "ðə spˈɑː ɔː ðə sˈiː"),
    ("en", "a comma or a colon", "ɐ kˈɒmə ɔːɹ ɐ kˈəʊlən"),  # blocks comma->or, keeps or->a
    ("en", "tilde ex", "tˈɪldəɹ ˈɛks"),      # no $pause word -> ɹ links normally

    # --- tone language (vi): a $u nucleus stays SECONDARY, content nucleus takes the tone ---
    ("vi", "cho ba", "tʃˌɔ1 bˈaː7"),         # `ba` nucleus; `cho` ($u) post-nuclear secondary
    ("vi", "ba cho", "bˈaː7 tʃˌɔ1"),         # nucleus stays on `ba` (content), `cho` reduces
    ("vi", "cho", "tʃˌɔ1"),                  # lone $u word: secondary nucleus (u_tonic)

    # --- la $u word: a nonsyllabic onset schwa @- (translate-default stress 1) outranks the
    # real vowel reduced to DIMINISHED (unstressed_wd1=0) and takes the clause tonic, rendering
    # as a bare ˈ before the cluster (count_pitch_vowels PRIMARY_LAST on the @- pitch syllable).
    ("la", "pro", "pˈrɔ"),                   # $u, p @- * O: tonic on @- not O
    ("la", "prae", "pˈraɪ"),
    ("la", "trans", "tˈrans"),               # $u, t @- * a n s: @- outranks the diminished a
    # non-$u cluster words are unaffected: the real vowel keeps the primary
    ("la", "pla", "plˈa"),                   # not $u -> normal penult/only-vowel stress
    ("la", "credo", "krˈɛdɔ"),               # not $u, two syllables
    ("la", "spro", "sprˈɔ"),                 # not $u, cluster + full vowel
]


@pytest.fixture
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


# A $unstressend spelled abbreviation (hu kb/KFT) shows a primary in its natural render, but as
# the clause nucleus the primary MOVES to the last letter (FLAG_UNSTRESS_END) — the nucleus
# re-render must fire even though the natural render already carries a primary.
HU_UNSTRESSEND_ABBREV = [
    ("kb", "kˌaːbˈeː"),
    ("KFT", "kˌaːˌɛfftˈeː"),
    ("tts", "tˌeːtˌeːˈɛʃ"),
]


@pytest.mark.parametrize("word,ipa", HU_UNSTRESSEND_ABBREV)
def test_hu_unstressend_abbrev_tonic_moves(oracle, word, ipa):
    import unicodedata
    g = G2P("hu", force_compat=True)
    assert unicodedata.normalize("NFC", g.phonemize(word)) == ipa
    assert unicodedata.normalize("NFC", oracle(word + "\n", "hu", "ipa")) == ipa
