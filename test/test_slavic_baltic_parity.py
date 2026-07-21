"""Byte-exact force_compat parity for the Slavic/Baltic headword tail.

Each case pins a mechanism that used to diverge from espeak-ng 1.52.0 (oracle), keyed to
the phonetic behaviour it exercises so a regression names the culprit, not just a word:

- cs `byl`/`byly`: `y`/`r` are vowel LETTERS (SetLetterVowel), so the `K) l (K` not-vowel
  syllabic-l rule does NOT fire after a vowel (bˈil, not the syllabic bˈil̩).
- ru `радио` / lt `raj`: an epenthetic @- inserted before a word-initial `r` inherits the
  word-start marker, so its `IF nextPhW(r) THEN ipa NULL` fires and the schwa is deleted.
- ky `эмнеге` … ($u words): a $u clause nucleus keeps its trochaic leading secondary
  (ˌemneɡˈe) — espeak never drops it, and its S_INITIAL_2/S_2_SYL_2 stay off for $u words.
- lt `ir` ($u): espeak runs a $u word's phoneme programs on its NATURAL stress (tonic only
  at render), so `i`'s ChangeIfStressed(I) does not fire (ˈir, not ˈɪr).
- tt `ъ`/`ь`: S_NO_AUTO_2 — no auto-secondary is added over the dict entry's own marks.
- sr/hr/bs `sl`: `l` is NOT a vowel letter, so a vowel-less "sl" is unpronounceable and
  spelled letter-by-letter (sˈəlˌə), while `r`-nucleus "krv" stays whole.
"""
import unicodedata

import pytest

from espyak.api import G2P

CASES = [
    ("cs", "byl", "bˈil"),
    ("cs", "byly", "bˈili"),
    ("ru", "радио", "rˈɑdʲɪo"),
    ("lt", "raj", "rajˈɔnas"),
    ("lt", "ir", "ˈir"),
    ("ky", "эмнеге", "ˌemneɡˈe"),
    ("ky", "эмнеден", "ˌemned[ˈen"),
    ("ky", "тескерисинче", "t[ˌeskerˌisintSˈe"),
    ("tt", "ъ", "qɑɫɯnɫˌɯqbilɣesˈe"),
    ("tt", "ь", "neɕkælˌekbilɣesˈe"),
    ("sr", "sl", "sˈəlˌə"),
    ("hr", "sl", "sˈəlˌə"),
    ("bs", "sl", "sˈəlˌə"),
    # adversarial: the fixes must NOT over-spell words whose nucleus IS a vowel letter,
    # nor drop a genuinely pronounceable syllabic consonant.
    ("sr", "krv", "krv"),
    ("sr", "bicikl", "bˈitsɪkl̩"),
]


def _nfc(s):
    return unicodedata.normalize("NFC", s)


@pytest.mark.parametrize("lang,word,expected", CASES)
def test_slavic_baltic_parity(oracle, lang, word, expected):
    got = _nfc(G2P(lang, force_compat=True).phonemize(word))
    assert got == expected
    assert got == _nfc(oracle(word, lang, "ipa"))
