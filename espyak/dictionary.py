"""Letter-to-sound matcher: port of the core of espeak-ng's dictionary.c.

  - MatchRule       (the rule scoring state machine)
  - TranslateRules  (the per-word driver: group selection, endings, retranslation)
  - AppendPhonemes  (vowel/stress counting used by @ and & rules)
  - IsLetter / IsLetterGroup / IsDigit helpers

The matcher walks each compiled rule's instruction stream (produced by rule_compiler)
exactly as espeak walks the compiled byte stream, so the point arithmetic and the
last-best-wins tie-break are reproduced. Phonemes are accumulated as mnemonic strings.

Reference: espeak-ng 1.52.0 dictionary.c (MatchRule:1484, TranslateRules:2080).
"""
import re
import unicodedata
from espyak import constants as K
from espyak.phoneme_tab import phVOWEL, phSTRESS, phLIQUID, phSTOP, phNASAL, phINVALID, phPAUSE, Phoneme

# A no-tie barrier ('|' in phoneme strings): keep it as a passthrough token through
# set_word_stress so the downstream phoneme parser doesn't greedily merge the phonemes it
# separates (pt acronym 's|;' must stay s + ; = sʲ, not the single phoneme 's;' = ʂ). It is
# type phINVALID, so it is never counted as a vowel or treated as a stress mark.
_BARRIER = Phoneme("|")

# A literal digit in a dict/rule phoneme string that maps to no phoneme (fa _list 'ARoq1' for the
# uvular ق/غ) is kept as an inert phINVALID token whose ipa is the digit, so it survives stressing and
# renders literally (espeak: ɑroq1). Tonal tables that define real digit phonemes (vi/cmn 1-7) match
# those first, so this only triggers where the digit is genuinely unmapped.
_LITERAL_DIGITS = {}
for _d in "0123456789":
    _dp = Phoneme(_d)
    _dp.ipa = _d
    _LITERAL_DIGITS[_d] = _dp


def _nfc(s):
    return unicodedata.normalize("NFC", s)


def _nfc_compose(s):
    """NFC form of `s`, but ONLY when NFC genuinely composes (does not lengthen).

    espeak hashes raw dict bytes, so the dict lookup falls back to an NFC form only to
    bridge an NFD source list matched by an NFC word (ko conjoining jamo -> syllable) — a
    composition that shortens or keeps length. A Devanagari nukta letter (U+095C etc.) is a
    Unicode full-composition-exclusion: NFC(U+095C) DEcomposes to ड+़ (LONGER). Bridging that
    would let a `.replace`-composed word (U+095C) re-match a decomposed dict key that espeak
    itself misses (falling through to the rules). So an exclusion-driven decomposition never
    bridges: return the string unchanged there, so the fallback get() is a harmless repeat."""
    n = unicodedata.normalize("NFC", s)
    return n if len(n) <= len(s) else s

REPLACED_E = ord("E")

# Myanmar format/break marks that espeak's tokenizer treats as separators (the dot-below ့,
# virama ္, and asat ်): when isolated they render to NOTHING — espeak never reaches its
# codepoint-spelling TranslateLetter for them — so they are excluded from compat_spell_codepoint.
_SPELL_CODEPOINT_SKIP = frozenset((0x1037, 0x1039, 0x103A))

# diereses_list (dictionary.c:61): vowels-with-dieresis that mark the START of a separate
# syllable. With LOPT_DIERESES (nl/af/la/ky/lt), an unmatched one is replaced by its base
# letter IN PLACE and matching continues from that point (keeping the phonemes produced so
# far), rather than restarting the whole word — so a digraph the dieresis breaks does NOT
# re-form (nl ingrediënt: i + ënt -> di'Ent, not the ie-digraph dient -> d'int).
_DIERESES_LIST = frozenset((0xE4, 0xEB, 0xEF, 0xF6, 0xFC, 0xFF))  # ä ë ï ö ü ÿ

# remove_accent[] (dictionary.c:66), indexed by codepoint-0xC0: the 7-bit base letter an
# accented char reduces to. espeak, on finding no rule for a letter, substitutes this base
# and re-translates the word (dictionary.c:2228). Covers 0xC0..0x25D.
_REMOVE_ACCENT = bytes.fromhex(
    "61616161616161636565656569696969646e6f6f6f6f6f006f7575757579747361616161616161636565656569696969646e6f6f6f6f6f006f757575757974796161616161616363636363636363646464646565656565656565656567676767676767676868686869"
    "69696969696969696969696a6a6b6b6b6c6c6c6c6c6c6c6c6c6c6e6e6e6e6e6e6e6e6e6f6f6f6f6f6f6f6f727272727272737373737373737374747474747475757575757575757575757577777979797a7a7a7a7a7a736262626200006f6363646464646465656566"
    "6667676869696b6b6c6c6d6e6e6f6f6f6f6f70707900007373747474747575757679797a7a7a7a7a7a7a000000777474746b6464646c6c6c6e6e6e616169696f6f7575757575757575757565616161616161676767676b6b6f6f6f6f7a7a6a646464676777776e6e61"
    "6161616f6f6161616165656565696969696f6f6f6f727272727575757573737474797968686e646f6f7a7a616165656f6f6f6f6f6f6f6f79796c6e746a64716163636c74737a000062757665656a6a717172727979616161626f636464656565656565"
)

# default English letter classification (tr_languages.c NewTranslator lines 277-284)
_DEFAULT_LETTER_BITS = {
    K.LETTERGP_A: "aeiou",
    K.LETTERGP_B: "bcdfgjklmnpqstvxz",
    K.LETTERGP_C: "bcdfghjklmnpqrstvwxz",
    K.LETTERGP_H: "hlmnr",
    K.LETTERGP_F: "cfhkpqstx",
    K.LETTERGP_G: "bdgjlmnrvwyz",
    K.LETTERGP_Y: "eiy",
    K.LETTERGP_VOWEL2: "aeiouy",
}


def _utf8_in(buf, i):
    """Decode one UTF-8 char forward at byte index i. Returns (codepoint, nbytes)."""
    if i >= len(buf):
        return 0, 1
    c = buf[i]
    if c < 0x80:
        return c, 1
    if c & 0xe0 == 0xc0:
        n = 2
    elif c & 0xf0 == 0xe0:
        n = 3
    elif c & 0xf8 == 0xf0:
        n = 4
    else:
        return c, 1
    try:
        return ord(buf[i:i + n].decode("utf-8")), n
    except (UnicodeDecodeError, ValueError):
        return c, 1


def _utf8_back(buf, i):
    """Decode the UTF-8 char ending at index i (i points at its last byte going back).

    Returns (codepoint, nbytes) where the char starts at i-(nbytes-1).
    """
    if i < 0:
        return 0, 1
    start = i
    while start > 0 and (buf[start] & 0xc0) == 0x80:
        start -= 1
    n = i - start + 1
    try:
        return ord(buf[start:start + n].decode("utf-8")), n
    except (UnicodeDecodeError, ValueError):
        return buf[i], 1


class Translator:
    """Translator state for the rules engine, configured per language."""

    def __init__(self, phsource=None, config=None):
        self.letter_bits = [0] * 256
        self.letter_groups = [None] * 8     # wchar overrides per group (None = use bits)
        self.letter_bits_offset = 0
        self.dict_condition = 0
        self.expect_verb = 0
        self.word_vowel_count = 0
        self.word_stressed_count = 0
        self._dict_ref = None
        self.phsource = phsource
        if config is None:
            config = {
                "stress_rule": K.STRESSPOSN_2R, "stress_flags": 0,
                "unstressed_wd1": 1, "unstressed_wd2": 3, "translator_name": 0,
                "letter_bits": dict(_DEFAULT_LETTER_BITS),
                "extra_vowels": "", "extra_consonants": "",
            }
        self.config = config
        self.stress_rule = config.get("stress_rule", K.STRESSPOSN_2R)
        self.stress_flags = config.get("stress_flags", 0)
        self.unstressed_wd1 = config.get("unstressed_wd1", 1)
        self.unstressed_wd2 = config.get("unstressed_wd2", 3)
        self.u_clause_final = config.get("u_clause_final", False)
        self.it_lengthen = config.get("it_lengthen", 0)  # LOPT_IT_LENGTHEN
        self.translator_name = config.get("translator_name", 0)
        # GetVowelStress priority-stress demotion (dictionary.c:889). Universal in espeak,
        # but enabled per-language here: a faithful port interacts with the `=` phonSTRESS_PREV
        # handling in ways still being reconciled for languages whose dict entries combine `''`
        # and `=` markers (da seminarium), so it is gated to the languages it is verified on.
        self.priority_stress_demote = config.get("priority_stress_demote", False)
        # voice `dictrules N M ...` permanently set those numbered conditions, so `?N`-gated
        # dict entries match (sr `?2 w -> duplo` for the W letter name needs condition 2).
        for _n in config.get("dictrules", ()):
            self.dict_condition |= (1 << _n)
        self._setup_letters(config)

    @property
    def dict(self):
        return self._dict_ref

    @dict.setter
    def dict(self, dictlist):
        # Stamp the translator's dict_condition onto the DictList so lookups that build their
        # own LookupContext without the translator in hand (number translation, numbers.py)
        # still select the voice's `?N`-gated entries (pt dictrules 1 -> ?1_14 "catorze").
        self._dict_ref = dictlist
        if dictlist is not None:
            dictlist.dict_condition = self.dict_condition

    def _setup_letters(self, config):
        for group, letters in config.get("letter_bits", _DEFAULT_LETTER_BITS).items():
            bits = 1 << group
            for ch in letters:
                if ord(ch) < 256:
                    self.letter_bits[ord(ch)] |= bits
        # SetLetterVowel: extra vowels go into groups A and VOWEL2
        for ch in config.get("extra_vowels", ""):
            if ord(ch) < 256:
                self.letter_bits[ord(ch)] |= (1 << K.LETTERGP_A) | (1 << K.LETTERGP_VOWEL2)
        for ch in config.get("extra_consonants", ""):
            if ord(ch) < 256:
                self.letter_bits[ord(ch)] |= (1 << K.LETTERGP_C)
        # SetLetterVowel(tr, c) (tr_languages.c:116): `letter_bits[c] = (bits & 0x40) | 0x81`
        # — make c a VOWEL (groups A + VOWEL2), keep its LETTERGP_Y bit, and REMOVE it from the
        # consonant groups B/C/G. pt `SetLetterVowel(tr,'y')`: y stops counting as a not-vowel
        # `K`, so `an (K+ -> &~N` no longer fires over `a (n -> &~`; tiffany -> tˈifɐ̃ni, not …ŋi.
        for ch in config.get("set_letter_vowel", ""):
            if ord(ch) < 256:
                self.letter_bits[ord(ch)] = (self.letter_bits[ord(ch)] & 0x40) | 0x81
        # ResetLetterBits(tr, mask) (tr_languages.c:126): clear the masked group bits from EVERY
        # letter before the language re-populates them (is clears groups 3,4 with 0x18, then sets
        # its own F=kpst / H=jvr). Runs after the defaults, before the per-language SetLetterBits.
        reset_mask = config.get("reset_letter_bits", 0)
        if reset_mask:
            inv = ~reset_mask & 0xFF
            for code in range(256):
                self.letter_bits[code] &= inv
        # SetLetterBits(group, letters): OR letters into a specific group
        for group, letters in config.get("set_letter_bits", []):
            for ch in letters:
                if ord(ch) < 256:
                    self.letter_bits[ord(ch)] |= (1 << group)
        # non-Latin scripts: letter_bits indexed by (char - offset) code values
        self.letter_bits_offset = config.get("letter_bits_offset", 0)
        for group, codes in config.get("letter_bits_codes", []):
            for code in codes:
                if 0 <= code < 256:
                    self.letter_bits[code] |= (1 << group)
        # SetLetterBitsRange(group, first, last): OR a contiguous code range (Indic)
        for group, first, last in config.get("letter_bits_ranges", []):
            for code in range(first, last + 1):
                if 0 <= code < 256:
                    self.letter_bits[code] |= (1 << group)
        # wchar vowel override (SetLetterVowel over a list of >255 codepoints, e.g. the 72
        # Vietnamese tone-marked vowels): a letter_groups[] entry takes precedence over the
        # 256-wide letter_bits in is_letter, so vowel groups can hold non-Latin-1 chars.
        vov = config.get("vowels_override")
        if vov:
            vset = frozenset(vov)
            self.letter_groups[K.LETTERGP_A] = vset
            self.letter_groups[K.LETTERGP_VOWEL2] = vset
        # wchar group override (tr_languages.c `tr->letter_groups[N] = ...`): a fixed membership
        # for a built-in group A)/B)/C)/H)/F)/G), consulted by IsLetter BEFORE letter_bits. is sets
        # group B (LETTERGP_B) to the voiceless consonants so `B) n -> hn#` fires only after a
        # voiceless letter (afn -> …hn#) and NOT after voiced g (vegna -> ʋˈɛɡna, no leak).
        for group, chars in config.get("letter_groups_override", {}).items():
            self.letter_groups[group] = frozenset(chars)

    def is_letter(self, letter, group):
        # port of IsLetter (dictionary.c:770)
        if group < 8 and self.letter_groups[group] is not None:
            return 1 if chr(letter) in self.letter_groups[group] else 0
        if group > 7:
            return 0
        if self.letter_bits_offset > 0:
            l2 = letter - self.letter_bits_offset
            if 0 < l2 < 0x100:
                letter = l2
            else:
                return 0
        elif 0xc0 <= letter < 0xc0 + len(_REMOVE_ACCENT):
            # accented Latin letter inherits its base letter's groups (dictionary.c:788):
            # ò counts as a vowel because o does -> gd `A) p (_` fires (ròp -> …b), ga IsVowel.
            base = _REMOVE_ACCENT[letter - 0xc0]
            return 1 if (self.letter_bits[base] & (1 << group)) else 0
        if 0 <= letter < 0x100:
            return 1 if (self.letter_bits[letter] & (1 << group)) else 0
        return 0

    def is_vowel(self, letter):
        return self.is_letter(letter, K.LETTERGP_VOWEL2)


# mnem_flags table (compiledict.c) — keyword -> flag code value
_MNEM_FLAGS = {
    "$1": 0x41, "$2": 0x42, "$3": 0x43, "$4": 0x44, "$5": 0x45, "$6": 0x46, "$7": 0x47,
    "$u": 0x48, "$u1": 0x49, "$u2": 0x4a, "$u3": 0x4b,
    "$u+": 0x4c, "$u1+": 0x4d, "$u2+": 0x4e, "$u3+": 0x4f,
    "$pause": 8, "$strend": 9, "$strend2": 10, "$unstressend": 11,
    "$accent_before": 12, "$abbrev": 13, "$double": 14,
    "$alt": 15, "$alt1": 15, "$alt2": 16, "$alt3": 17, "$alt4": 18, "$alt5": 19,
    "$alt6": 20, "$alt7": 21, "$combine": 23, "$dot": 24, "$hasdot": 25,
    "$max3": 27, "$brk": 28, "$text": 29,
    "$verbf": 0x20, "$verbsf": 0x21, "$nounf": 0x22, "$pastf": 0x23,
    "$verb": 0x24, "$noun": 0x25, "$past": 0x26, "$verbextend": 0x28,
    "$capital": 0x29, "$allcaps": 0x2a, "$accent": 0x2b, "$sentence": 0x2d,
    "$only": 0x2e, "$onlys": 0x2f, "$stem": 0x30, "$atend": 0x31, "$atstart": 0x32,
    "$native": 0x33, "$textmode": 200, "$phonememode": 201,
}


class DictEntry:
    __slots__ = ("phonemes", "flag_codes", "multiword", "rest", "key_upper")

    def __init__(self, phonemes, flag_codes, multiword=False, rest="", key_upper=False):
        self.phonemes = phonemes
        self.flag_codes = flag_codes
        self.multiword = multiword
        self.rest = rest
        # True if the SOURCE key for this entry had a leading uppercase letter. espeak buckets
        # `l` and `L` separately, so a lowercase single-letter NAME lookup must not borrow the
        # uppercase variant (fo L -> %El: geminates, l -> El does not).
        self.key_upper = key_upper


class DictList:
    """Parsed <lang>_list (+_extra): word -> entries, with espeak's selection logic."""

    def __init__(self):
        self.words = {}     # lowercase word -> list[DictEntry] in file order
        self._raw_keys = set()  # raw (non-NFC) lowercase keys, for cross-form collision guard
        self.cased_keys = set()  # original-case keys (espeak's letter lookup is case-sensitive)
        self.text_mode = False
        # fo: single-letter NAME lookups respect the source key's case (see DictEntry.key_upper).
        self.case_sensitive_letters = False
        # the owning Translator stamps its dict_condition here (Translator.dict setter) so
        # context-less lookups (number translation) still select `?N`-gated entries.
        self.dict_condition = 0

    def has_exact(self, key):
        """True if `key` existed verbatim (case-sensitive). espeak's LookupLetter is
        case-sensitive: a lowercase letter must not match an uppercase `_X` name entry
        (smj `_O o:` is the name of UPPERCASE O; lowercase o spells via the rules -> oɔ)."""
        return _nfc(key) in self.cased_keys

    @classmethod
    def load(cls, *paths):
        dl = cls()
        for path in paths:
            if path:
                dl._parse_file(path)
        return dl

    def _parse_file(self, path):
        try:
            fh = open(path, encoding="utf-8", errors="replace")
        except OSError:
            return
        with fh:
            for raw in fh:
                self._parse_line(raw)

    def _parse_line(self, raw):
        ix = raw.find("//")
        if ix >= 0:
            raw = raw[:ix]
        line = raw.strip()
        if not line:
            return
        flag_codes = []
        rest_words = ""
        # a condition can precede the word: "?N" or "?!N" (N up to two digits). compile_line
        # (compiledict.c:435) consumes ONLY `?`, an optional `!`, and up to two digits, then the
        # word follows — so the condition need NOT be whitespace-separated from the word. Both
        # "?!3 _0and  @n" (spaced) and "?1_14" (glued, pt teens/tens) are the same shape: the
        # word is whatever remains after the fixed-width condition token. Reading the whole
        # whitespace token as the condition (and scraping its digits) mis-parsed "?1_14" as
        # condition 114 and dropped `_14`, so the pt cardinals 13/14/16-19/2X/4X/6X/7X/9X and
        # the en `?3_.p` abbreviation never loaded.
        leading_cond = []
        while line and line[0] == "?":
            p = 1
            neg = p < len(line) and line[p] == "!"
            if neg:
                p += 1
            ndig = 0
            num = 0
            while ndig < 2 and p < len(line) and line[p].isdigit():
                num = num * 10 + int(line[p])
                p += 1
                ndig += 1
            if ndig == 0:
                break  # a bare leading `?` is not a condition (leave it for the word/phonemes)
            leading_cond.append(num + (132 if neg else 100))
            line = line[p:].lstrip()
        if not line:
            return
        flag_codes.extend(leading_cond)
        # multi-word entry "(w1 w2 ...)"
        if line[0] == "(":
            close = line.find(")")
            if close < 0:
                return
            # compiledict.c LINE_PARSER_END_OF_WORD: inside a "(...)" multi-word entry a hyphen
            # is a word separator (it sets BITNUM_FLAG_HYPHENATED and rewrites '-' to ' '), so
            # `(has-been)`/`(lean-to)` compile to key "has"/"lean" + follow "been"/"to", exactly
            # like the space-separated `(has been)`. A hyphen after a DIGIT is kept (numeric-hyphen,
            # hu `(1-e)` $text): those stay a single-token key, matching the C special case.
            inside = re.sub(r"(?<!\d)-", " ", line[1:close]).split()
            word = inside[0] if inside else ""
            rest_words = " ".join(inside[1:])
            tokens = line[close + 1:].split()
            multiword = True
        else:
            toks = line.split()
            word = toks[0]
            tokens = toks[1:]
            multiword = False
        # a standalone `$textmode` / `$phonememode` line is a SECTION directive (ro abbreviations:
        # etc -> etcetera, udmr -> udemere are replacement text, not phonemes), not a word entry.
        if word in ("$textmode", "$phonememode") and not tokens:
            self.text_mode = (word == "$textmode")
            return
        phon_tokens = []
        for tok in tokens:
            # a condition marker is "?N" or "?!N" (? + digit); a token like "?ila:h" is
            # phonemes beginning with the glottal-stop phoneme `?` (Arabic hamza), NOT a
            # condition — misreading it dropped the pronunciation of hamza-initial words.
            if tok.startswith("?") and len(tok) > 1 and (
                    tok[1].isdigit() or (tok[1] == "!" and tok[2:3].isdigit())):
                neg = tok[1] == "!"
                num = "".join(ch for ch in tok if ch.isdigit())
                if num:
                    flag_codes.append(int(num) + (132 if neg else 100))
            elif tok.startswith("$"):
                val = _MNEM_FLAGS.get(tok)
                if val == 200:
                    self.text_mode = True
                elif val == 201:
                    self.text_mode = False
                elif val is not None:
                    flag_codes.append(val)
            else:
                phon_tokens.append(tok)
        # espeak's _list value is a SINGLE phoneme string (word breaks use ||, not spaces); a second
        # whitespace-separated token is a separate field that EncodePhonemes does not consume (mt
        # `lil hinn<TAB>lil:in:` -> lil maps to `hinn`, the trailing `lil:in:` dropped, not hinnlilin).
        # EXCEPTION: a $textmode value is replacement TEXT that espeak puts back in the source buffer
        # and re-tokenises, so a multi-word value keeps ALL its words (xex j -> "íki flu", spoken as
        # two words ˈiːki flˈuː).
        if self.text_mode and len(phon_tokens) > 1:
            phonemes = " ".join(phon_tokens)
        else:
            phonemes = phon_tokens[0] if phon_tokens else ""
        if "_^_" in phonemes:
            # compiledict.c:582-583: an entry whose phonemes contain a language switch (phonSWITCH,
            # written `_^_LANG`) implicitly gets FLAG_ONLY_S — "don't match on suffixes (except 's')
            # when switching languages". So de `word _^_EN` matches `word`/`words` but NOT the stem
            # of `worden` (the `en` suffix removed), which falls through to the rules (vˈɔɾdən).
            flag_codes.append(_MNEM_FLAGS["$onlys"])
        if self.text_mode:
            flag_codes.append(_MNEM_FLAGS["$text"])  # within a $textmode section -> FLAG_TEXTMODE
        # compile_line (compiledict.c:601-617): every key is lowercased; a key whose letters are
        # ALL uppercase (en LBS, ca/Greek T, fo L) gets an implicit $allcaps, so it only matches
        # an all-caps source word. A first-capital key (pt Braille, ?2 Gmail) carries NO case
        # flag — it is simply the lowercase entry.
        if (word and word[0] != "_" and word.isalpha() and word.isupper()
                and _MNEM_FLAGS["$allcaps"] not in flag_codes):
            flag_codes = flag_codes + [_MNEM_FLAGS["$allcaps"]]
        entry = DictEntry(phonemes, flag_codes, multiword, rest_words,
                          key_upper=word[:1].isupper())
        # NFC-normalize keys so NFD source lists (e.g. ko_list conjoining jamo) match an
        # NFC-normalized lookup; idempotent for the usual NFC/ASCII entries. EXCEPTION: keys that
        # NFC would merge with a distinct espeak entry (polytonic Greek, CJK compatibility
        # ideographs) stay matchable under their raw key — see the raw-key indexing below.
        _lw = word.lower()
        _is_greek = bool(_lw) and 0x1F00 <= ord(_lw[0]) <= 0x1FFF
        _nfckey = _lw if _is_greek else _nfc(_lw)
        # Index under the RAW source key, plus the NFC key when it differs. espeak hashes
        # the raw dict bytes, so a decomposed source key (Devanagari base+nukta, e.g. kok
        # ड़ = ड+़ -> r.) must stay matchable by a decomposed lookup rather than being
        # collapsed onto — and shadowed in the same bucket by — a distinct precomposed
        # entry (U+095C -> r-). The NFC key is still indexed so an NFD source list (ko
        # conjoining jamo) keeps matching an NFC-normalised lookup. CRITICAL: nukta
        # precomposed letters (U+095C etc.) are Unicode full-composition-exclusions, so
        # NFC(U+095C) DEcomposes to ड+़ — indexing that entry under its NFC key would drop
        # its r- pronunciation into the decomposed r. bucket and shadow it (reversed()
        # picks the last-added). A composition-exclusion is exactly the case where the NFC
        # form is LONGER than the raw key (1 precomposed char -> base+mark); a genuine
        # composition (ko conjoining jamo -> syllable) is not longer. So the NFC key is only
        # added when it is not longer than the raw key AND does not already name another
        # entry's raw key — i.e. it introduces no cross-form collision.
        self.words.setdefault(_lw, []).append(entry)
        if _nfckey != _lw and len(_nfckey) <= len(_lw) and _nfckey not in self._raw_keys:
            self.words.setdefault(_nfckey, []).append(entry)
        self._raw_keys.add(_lw)
        self.cased_keys.add(word)
        if not _is_greek:
            self.cased_keys.add(_nfc(word))

    def lookup(self, word, ctx):
        """Return (phonemes_or_None, flags1) or (None, None) if not found.

        Port of LookupDict2 selection: iterate entries last-in-file first, apply
        condition/flag checks against the context (an LookupContext). A returned
        phonemes of "" with flags1!=None means flags-only (use rules).
        """
        self._last_accent = False
        entries = self.words.get(word.lower()) or self.words.get(_nfc_compose(word.lower()))
        if not entries and len(word) == 2 and word[1] == ":":
            # smj writes long-vowel letter names with a redundant length colon (A: is the long-A
            # letter name ɑː); the dict keys it under the bare letter (A -> A:). A CamelCase split
            # yields the bare "A:" token, which otherwise misses the dict and reads as a short vowel.
            entries = self.words.get(word[0].lower()) or self.words.get(_nfc_compose(word[0].lower()))
        if not entries:
            return None, None
        for entry in reversed(entries):
            ok, flags1, flags2, stress = self._eval(entry, ctx)
            if not ok:
                continue
            flags1 = (flags1 & ~0xf) | stress if stress is not None else flags1
            # $accent on a phoneme-less entry (en á `$accent $atend`): LookupDict2 spells the
            # letter via LookupAccentedLetter (base-letter name + accent name) instead of the
            # rules. FLAG_ACCENT lives in flags2, which we don't return, so signal it here.
            if (flags2 & K.FLAG_ACCENT) and not entry.phonemes:
                self._last_accent = True
            return entry.phonemes, flags1
        return None, None

    def multiword_skip(self, word, following, dict_condition=0,
                       first_upper=False, all_upper=False):
        """Return how many FOLLOWING words a matching multi-word entry for `word` consumes.

        Mirrors LookupDict2's selection (last-in-file entry wins) but reports only the skipword
        count: 0 when the winning entry is an ordinary single word (or nothing matches), N when a
        `(w1 w2 ... wN+1)` entry fires. The caller uses this to advance past the consumed words and
        to place the clause tonic on the whole multi-word unit. The case flags MUST match those the
        actual render-time lookup uses, or the two disagree — e.g. all-caps `HAS BEEN` selects the
        $allcaps single-word `has` entry, not `(has-been)`, so no words may be skipped."""
        if not following:
            return 0
        entries = self.words.get(word.lower()) or self.words.get(_nfc_compose(word.lower()))
        if not entries:
            return 0
        ctx = LookupContext(dict_condition=dict_condition, following=following, clause_ctx=True,
                            first_upper=first_upper, all_upper=all_upper)
        for entry in reversed(entries):
            ok, _f1, _f2, _s = self._eval(entry, ctx)
            if ok:
                return len(entry.rest.split()) if entry.multiword else 0
        return 0

    def lookup_flags(self, word, dict_condition=0, first_upper=False, all_upper=False):
        """Flags-only lookup (port of LookupFlags): return flags1 for `word`, with FLAG_FOUND set
        if any entry matched (0 if absent). No phoneme translation, so the matcher's DollarRule can
        call it without recursing back into translation. `first_upper`/`all_upper` gate $capital/
        $allcaps entries (hu KFT $unstressend is all-caps-only)."""
        entries = self.words.get(word.lower()) or self.words.get(_nfc_compose(word.lower()))
        if not entries:
            return 0
        ctx = LookupContext(dict_condition=dict_condition, first_upper=first_upper,
                            all_upper=all_upper)
        for entry in reversed(entries):
            ok, flags1, flags2, stress = self._eval(entry, ctx)
            if ok:
                flags1 = (flags1 & ~0xf) | stress if stress is not None else flags1
                return flags1 | K.FLAG_FOUND
        return 0

    def _eval(self, entry, ctx):
        flags1 = 0
        flags2 = 0
        stress = None
        for flag in entry.flag_codes:
            if flag >= 100:
                if flag >= 132:
                    if (ctx.dict_condition & (1 << (flag - 132))) != 0:
                        return False, 0, 0, None
                else:
                    if (ctx.dict_condition & (1 << (flag - 100))) == 0:
                        return False, 0, 0, None
            elif flag > 80:
                return False, 0, 0, None  # multi-word skipwords: no match for isolated word
            elif flag > 64:
                stress = flag & 0xf
                if (flag & 0xc) == 0xc:
                    flags1 |= K.FLAG_STRESS_END
            elif flag >= 32:
                flags2 |= (1 << (flag - 32))
            else:
                flags1 |= (1 << flag)
        if entry.multiword:
            # LookupDict2 flag>80 (skipwords) path: the entry only matches if the words that FOLLOW
            # in the source match the stored follow-string. C does `strncmp(word2, "<rest> ", n)`
            # against the raw source after the first word; here the follow words are pre-tokenised in
            # ctx.following (lowercased), so a whole-word prefix compare is exact. With no following
            # context (isolated-word lookup / lookup_flags) ctx.following is empty and a multi-word
            # entry can never fire — preserving the historical isolated-word behaviour.
            rest = entry.rest.split()
            foll = ctx.following
            if len(foll) < len(rest) or any(foll[k] != rest[k] for k in range(len(rest))):
                return False, 0, 0, None
        # condition checks (LookupDict2 tail)
        if (flags2 & K.FLAG_STEM) and not ctx.suffix_removed:
            return False, 0, 0, None
        # $only / $onlys suffix gating (LookupDict2:2573-2581). $only never matches once a prefix
        # OR suffix was removed; $onlys (implicit on language-switch entries) matches only when no
        # suffix was removed or the removed suffix was 's'. de `word _^_EN` ($onlys via _^_) thus
        # matches `word`/`words` but not the `en`-stripped stem of `worden`.
        if (flags2 & K.FLAG_ONLY) and (ctx.suffix_removed or ctx.prefix_removed):
            return False, 0, 0, None
        if (flags2 & K.FLAG_ONLY_S) and (
                ctx.prefix_removed or (ctx.suffix_removed and not ctx.suffix_is_s)):
            # LookupDict2:2571 rejects BOTH $only and $onlys once a prefix was removed, not
            # just $only. en `put ,pUt $onlys` must not match the `out`-prefix-stripped stem of
            # `output` (-> ˈaʊtpʊt, the whole out+put stressed once, not ˈaʊtpˌʊt).
            return False, 0, 0, None
        if (flags2 & K.FLAG_CAPITAL) and not ctx.first_upper:
            return False, 0, 0, None
        if (flags2 & K.FLAG_ALLCAPS) and not ctx.all_upper:
            return False, 0, 0, None
        if (flags1 & K.FLAG_NEEDS_DOT) and not ctx.has_dot:
            return False, 0, 0, None
        if flags2 & K.FLAG_ATEND:
            if ctx.clause_ctx:
                # $atend = "use this pronunciation at end of clause" (LookupDict2: word_end <
                # clause_end). A multi-word entry's span ends after its follow-words, so it is at
                # clause end only when it consumes ALL remaining words; a single-word entry only
                # when nothing follows. This stops `(it has) $atend` from firing mid-clause.
                rest_n = len(entry.rest.split()) if entry.multiword else 0
                if len(ctx.following) != rest_n:
                    return False, 0, 0, None
            elif not ctx.at_end:
                return False, 0, 0, None
        if (flags2 & K.FLAG_ATSTART) and not ctx.first_word:
            return False, 0, 0, None
        if (flags2 & K.FLAG_SENTENCE) and not ctx.sentence:
            return False, 0, 0, None
        if (flags2 & K.FLAG_VERB) and not ctx.expect_verb:
            return False, 0, 0, None
        if (flags2 & K.FLAG_PAST) and not ctx.expect_past:
            return False, 0, 0, None
        if (flags2 & K.FLAG_NOUN) and not ctx.expect_noun:
            return False, 0, 0, None
        return True, flags1, flags2, stress


class LookupContext:
    """Per-word context for dictionary selection (isolated-word defaults)."""

    def __init__(self, first_upper=False, all_upper=False, has_dot=False,
                 first_word=True, at_end=True, sentence=True, dict_condition=0,
                 expect_verb=0, expect_noun=0, expect_past=0, suffix_removed=False,
                 prefix_removed=False, suffix_is_s=False, following=(), clause_ctx=False):
        self.first_upper = first_upper
        self.all_upper = all_upper
        self.has_dot = has_dot
        self.first_word = first_word
        self.at_end = at_end
        self.sentence = sentence
        self.dict_condition = dict_condition
        self.expect_verb = expect_verb
        self.expect_noun = expect_noun
        self.expect_past = expect_past
        self.suffix_removed = suffix_removed   # a suffix was removed (FLAG_SUFX)
        self.prefix_removed = prefix_removed   # a prefix was removed (SUFX_P)
        self.suffix_is_s = suffix_is_s         # the removed suffix was 's' (FLAG_SUFX_S)
        # the words that FOLLOW this word in the clause (lowercased tokens), used to match a
        # multi-word `(w1 w2 ...)` dict entry against the source (LookupDict2 skipwords path).
        self.following = list(following)
        # True when `following` reflects the real clause tail, so a $atend gate is evaluated by
        # actual position (does the matched span reach the clause end?) instead of the historical
        # isolated-word at_end=True assumption. Only set for multi-word probing/rendering.
        self.clause_ctx = clause_ctx


def is_digit(c):
    return ord("0") <= c <= ord("9")


def is_alpha(wc):
    return chr(wc).isalpha() if wc else False


def count_vowels(tr, ph, mnem_index):
    """Port of AppendPhonemes' vowel/stress counting over a mnemonic phoneme string.

    Updates tr.word_vowel_count and tr.word_stressed_count. `mnem_index` maps a phoneme
    mnemonic -> Phoneme; multi-char mnemonics are matched greedily.
    """
    unstress_mark = False
    i = 0
    n = len(ph)
    maxlen = mnem_index.maxlen
    while i < n:
        if ph[i] in (" ", "\t", "|"):
            i += 1
            continue
        m = None
        for L in range(min(maxlen, n - i), 0, -1):
            cand = ph[i:i + L]
            if cand in mnem_index.table:
                m = cand
                break
        if m is None:
            i += 1
            continue
        p = mnem_index.table[m]
        i += len(m)
        if p.type == phSTRESS:
            if p.stress_type < 4:
                unstress_mark = True
        elif p.type == phVOWEL:
            if ("unstressed" not in p.flags) and (not unstress_mark):
                tr.word_stressed_count += 1
            unstress_mark = False
            tr.word_vowel_count += 1


class MnemIndex:
    """Greedy mnemonic lookup over a phoneme table (for vowel counting / stress)."""

    def __init__(self, phoneme_table):
        self.table = phoneme_table.phonemes
        self.maxlen = max((len(m) for m in self.table), default=1)

    def tokenize(self, ph):
        """Greedy split of a mnemonic phoneme string into [(mnemonic, Phoneme), ...]."""
        toks = []
        i, n = 0, len(ph)
        while i < n:
            if ph[i] == "|":
                toks.append(("|", _BARRIER))  # no-tie barrier: preserve through stressing
                i += 1
                continue
            if ph[i] in (" ", "\t"):
                i += 1
                continue
            m = None
            for L in range(min(self.maxlen, n - i), 0, -1):
                cand = ph[i:i + L]
                if cand in self.table:
                    m = cand
                    break
            if m is None:
                if ph[i] in _LITERAL_DIGITS:
                    toks.append((ph[i], _LITERAL_DIGITS[ph[i]]))
                i += 1
                continue
            toks.append((m, self.table[m]))
            i += len(m)
        return toks


# stress level -> stress mnemonic to insert (stress_phonemes[] indexed by v_stress).
# 1 (unstressed) is never inserted. Renderer maps these back via stress_type.
_STRESS_MNEM = {0: "%%", 2: ",", 3: ",,", 4: "'", 5: "''", 6: "'!"}

# synthesize.h stress levels
STRESS_IS_DIMINISHED = 0
STRESS_IS_UNSTRESSED = 1
STRESS_IS_NOT_STRESSED = 2
STRESS_IS_SECONDARY = 3
STRESS_IS_PRIMARY = 4
STRESS_IS_PRIORITY = 5

# stress_rule values
STRESSPOSN_2R = K.STRESSPOSN_2R


def _ph_is_vowel(p):
    return p.type == phVOWEL and "nonsyllabic" not in p.flags


def _nonsyllabic_before_vowel(p):
    """True for a vowel-typed phoneme whose program turns it into the consonant N when the
    next phoneme is a vowel (`IF nextPh(isVowel) THEN ChangePhoneme(N)`). This is the yue/zh
    `ng` initial: syllabic `ŋ̩` on its own (五 -> ˈnɡ5), but a plain onset consonant `ŋ` before
    a vowel (我=ngo5 -> ŋˈo5), so it must NOT be counted as a syllable nucleus there. The
    program signature scopes this to that phoneme — other langs' ChangePhoneme(N) is on a
    consonant-typed `n` (velar assimilation), which _ph_is_vowel already rejects."""
    if p.type != phVOWEL:
        return False
    prog = getattr(p, "program", None)
    if not prog:
        return False
    txt = " ".join(prog)
    return "nextPh(isVowel)" in txt and "ChangePhoneme(N)" in txt


def _is_syllabic_marker(mnem, ph):
    """The phonSYLLABIC virtual phoneme `-` (phsource `phoneme -`): marks the PRECEDING
    consonant as a syllabic nucleus. GetVowelStress (dictionary.c:878) counts it as a
    syllable slot even though it carries no sound of its own, and the output loop
    (dictionary.c:1391, `*p == phonSYLLABIC`) emits that syllable's stress before the
    consonant it follows. A bare `-` after a vowel (ar/fa letter names `...e-,ta`,
    `maqs[-'u:Rah`) still adds the slot, shifting the following real vowels' stress one
    place — which is exactly how espeak places the secondary."""
    return ph.type == K.phVIRTUAL and mnem == "-"


def get_vowel_stress(toks, stressed_syllable=0):
    """Port of GetVowelStress. Returns (vowel_stress list, phonetic toks, count, primary).

    `phonetic` is the token stream with stress markers removed (as ph_out in C).
    vowel_stress is indexed 1..count-1 (index 0 unused/sentinel).
    """
    vowel_stress = [STRESS_IS_UNSTRESSED]  # index 0
    phonetic = []
    count = 1
    max_stress = -1
    stress = -1
    primary_posn = 0
    for idx, (mnem, ph) in enumerate(toks):
        if ph.type == phSTRESS and not mnem.isdigit():
            # digit-named phStress phonemes are tone marks (Vietnamese 1-7), not stress
            # markers — keep them in the phonetic stream rather than consuming them.
            if mnem == "=":
                # phonSTRESS_PREV: place primary stress on the PRECEDING stressable vowel — but it must
                # not override a lexical accent (PRIORITY stress). pt símbolo (s''imbol=U): the accented
                # í is priority, so = is suppressed (else it stresses the unstressed 'o' -> sˈimbˌolʊ,
                # blocking o->u; correct is sˈimbulʊ). But = DOES move an ordinary PRIMARY to the suffix,
                # demoting the earlier one to secondary: da defektrice (def'?Egtri=s@-) -> defˌεɡtʁˈisə.
                j = count - 1
                while (j > 0) and (stressed_syllable == 0) and (max_stress < STRESS_IS_PRIORITY) \
                        and (vowel_stress[j] < STRESS_IS_PRIMARY):
                    if vowel_stress[j] not in (STRESS_IS_DIMINISHED, STRESS_IS_UNSTRESSED):
                        vowel_stress[j] = STRESS_IS_PRIMARY
                        if max_stress < STRESS_IS_PRIMARY:
                            max_stress = STRESS_IS_PRIMARY
                            primary_posn = j
                        for ix in range(1, j):
                            if vowel_stress[ix] == STRESS_IS_PRIMARY:
                                vowel_stress[ix] = STRESS_IS_SECONDARY
                        break
                    j -= 1
                continue
            # stress marker for the following vowel
            if (ph.stress_type < 4) or (stressed_syllable == 0):
                stress = ph.stress_type
                if stress > max_stress:
                    max_stress = stress
            continue
        if _nonsyllabic_before_vowel(ph) and idx + 1 < len(toks) \
                and _ph_is_vowel(toks[idx + 1][1]):
            # yue/zh `ng` onset before a vowel: the phoneme interpreter changes it to the
            # consonant N, so (like espeak's GetVowelStress) it is not a syllable nucleus here
            # and the stress falls on the following vowel (我=ngo5 -> ŋˈo5, not ŋo5).
            phonetic.append((mnem, ph))
            continue
        if _ph_is_vowel(ph):
            # @- is the "very short schwa": in most languages it is the nonsyllabic
            # linking/epenthetic schwa (eo Cr clusters septemb@-*o) — excluded from the
            # vowel count by its phNONSYLLABIC flag (_ph_is_vowel returns False). But fr/vi
            # redefine @- as a full syllabic vowel (ph_french/ph_vietnam, no `nsy`), so it
            # IS a nucleus there (fr je=Z@- -> ʒˈə-); rely on the per-language flag, not the
            # mnemonic, to keep both cases right.
            vowel_stress.append(stress)
            if stress >= STRESS_IS_PRIMARY and stress >= max_stress:
                primary_posn = count
                max_stress = stress
            if stress < 0 and "unstressed" in ph.flags:
                vowel_stress[count] = STRESS_IS_UNSTRESSED
            count += 1
            stress = -1
        elif _is_syllabic_marker(mnem, ph):
            # phonSYLLABIC marker (dictionary.c:876-879): the previous consonant is a syllable
            # nucleus. Add a vowel_stress slot (unstressed if no stress precedes) WITHOUT
            # resetting `stress` or moving primary_posn (control&1 is always set on this call).
            vowel_stress.append(stress if stress >= 0 else STRESS_IS_UNSTRESSED)
            count += 1
        phonetic.append((mnem, ph))
    vowel_stress.append(STRESS_IS_UNSTRESSED)
    return vowel_stress, phonetic, count, primary_posn, max_stress


def set_word_stress(tr, phoneme_str, mnem_index, dict_flags=0, tonic=-1, control=0,
                    suffix_vowels=0):
    """Port of SetWordStress (dictionary.c:919) for stress_rule=STRESSPOSN_2R and the
    common path. Returns the phoneme string with stress mnemonics inserted.

    `suffix_vowels` is the number of trailing vowels that belong to a removed suffix:
    espeak runs GetVowelStress on the stem only and appends the suffix unstressed, so
    those vowels are excluded from the auto-secondary loop (ro unele -> ˈunele not ˈunelˌe).
    """
    toks = mnem_index.tokenize(phoneme_str)
    if not toks:
        return phoneme_str
    stressflags = tr.stress_flags

    unstressed_word = False
    stressed_syllable = dict_flags & 0x7
    if dict_flags & 0x8:
        stressed_syllable = dict_flags & 0x3
        unstressed_word = True

    vowel_stress, phonetic, vowel_count, primary_posn, max_stress = get_vowel_stress(
        toks, stressed_syllable)

    if max_stress == STRESS_IS_PRIORITY and tr.priority_stress_demote:
        # GetVowelStress (dictionary.c:889): a priority marker ('') replaces every other
        # primary marker in the word, then the priority itself becomes the primary. With
        # S_PRIORITY_STRESS the demoted primaries go UNSTRESSED, else SECONDARY. In C this
        # runs inside GetVowelStress, so its result is the max_stress captured below.
        # pt aníbal (&n''ib'Al): the priority í wins, so the rule-emitted primary on the
        # final -al is dropped (force_compat -> ɐnˈibɑl, not ɐnˈibˌɑl).
        for ix in range(1, vowel_count):
            if vowel_stress[ix] == STRESS_IS_PRIMARY:
                if tr.stress_flags & K.S_PRIORITY_STRESS:
                    vowel_stress[ix] = STRESS_IS_UNSTRESSED
                else:
                    vowel_stress[ix] = STRESS_IS_SECONDARY
            if vowel_stress[ix] == STRESS_IS_PRIORITY:
                vowel_stress[ix] = STRESS_IS_PRIMARY
                primary_posn = ix
        max_stress = STRESS_IS_PRIMARY

    max_stress_input = max_stress
    # espeak keeps unstressed_word TRUE for the whole of SetWordStress; the reset just below is an
    # espyak-only device to gate the el u_clause_final block. Capture the C-faithful value so the
    # S_INITIAL_2 / S_2_SYL_2 auto-secondary block (which C skips for every $u word) still keys off it.
    unstressed_word_input = unstressed_word
    if (unstressed_word and tonic >= STRESS_IS_PRIMARY and max_stress >= STRESS_IS_PRIMARY
            and primary_posn >= vowel_count - 2):
        # a $u function word that IS the clause nucleus keeps its own lexical stress only when that
        # accent is on the penult or last syllable (el θαείμαι -> θaˈime). With the accent further
        # back (είμαστε, accent on the antepenult) the clause tonic instead moves to the final
        # syllable (-> ˌimastˈe), left to the u_clause_final block below.
        unstressed_word = False
    if stressed_syllable > 0:
        if stressed_syllable >= vowel_count:
            stressed_syllable = vowel_count - 1
        vowel_stress[stressed_syllable] = STRESS_IS_PRIMARY
        max_stress = STRESS_IS_PRIMARY
        primary_posn = stressed_syllable
    if max_stress < 0 and dict_flags is not None:
        max_stress = STRESS_IS_DIMINISHED

    # GetVowelStress sets *stressed_syllable = primary_posn: an explicit primary stress
    # marker (or $N flag) fixes the stressed syllable, so the stress_rule below is
    # skipped (its guard is `stressed_syllable == 0`). Without this, words with explicit
    # stress get a second primary from the penultimate rule (méxico -> mˈɛxˈiko).
    stressed_syllable = primary_posn

    # syllable weights (heavy/light)
    consonant_types_set = (phVOWEL,)  # placeholder; weight calc below uses types
    vowel_length = [0] * (vowel_count + 2)
    syllable_weight = [0] * (vowel_count + 2)
    _compute_weights(phonetic, vowel_length, syllable_weight)

    max_stress_input = max_stress  # max explicit stress before the stress rule fires

    # stress rule
    if tr.stress_rule == STRESSPOSN_2R:
        if stressed_syllable == 0:
            max_stress = STRESS_IS_PRIMARY
            if vowel_count > 2:
                stressed_syllable = vowel_count - 2
                # S_FINAL_SPANISH (dictionary.c:1055): a word ending in a consonant other than -s/-n
                # takes final stress (ca/es animal -> animˈal, papel -> papˈel); a -Vs/-Vn ending
                # (plurals, verb forms) keeps the penult, but -Cs/-Cn (consonant before) goes final.
                # espeak branches on the translator: an/ca (the s+n form), ia (s only), and the
                # generic else-arm with its -ns (s after a nasal) penult special-case.
                if (stressflags & K.S_FINAL_SPANISH) and phonetic and phonetic[-1][1].type != phVOWEL:
                    final_ph = phonetic[-1][1]
                    last_mnem = phonetic[-1][0]
                    final_ph2 = phonetic[-2][1] if len(phonetic) >= 2 else final_ph
                    pre_vowel = final_ph2.type == phVOWEL
                    if tr.translator_name in (K.L("a", "n"), K.L("c", "a")):
                        if (last_mnem not in ("s", "n")) or not pre_vowel:
                            stressed_syllable = vowel_count - 1
                    elif tr.translator_name == K.L("i", "a"):
                        if (last_mnem != "s") or not pre_vowel:
                            stressed_syllable = vowel_count - 1
                    else:
                        if (last_mnem == "s") and (final_ph2.type == phNASAL):
                            pass  # -ns: stress stays on the penultimate syllable
                        elif ((final_ph.type != phNASAL) and (last_mnem != "s")) or not pre_vowel:
                            stressed_syllable = vowel_count - 1
                # S_FINAL_LONG (dictionary.c:1075, LANG=om): stress the last syllable when it
                # has a long vowel but the penult is short (vowel_length[n-1] > vowel_length[n-2]).
                if stressflags & K.S_FINAL_LONG:
                    if vowel_length[vowel_count - 1] > vowel_length[vowel_count - 2]:
                        stressed_syllable = vowel_count - 1
                if vowel_stress[stressed_syllable] in (STRESS_IS_DIMINISHED, STRESS_IS_UNSTRESSED):
                    stressed_syllable = stressed_syllable - 1 if stressed_syllable > 1 else stressed_syllable + 1
            else:
                stressed_syllable = 1
            if vowel_stress[stressed_syllable] < 0:
                if (vowel_stress[stressed_syllable - 1] < STRESS_IS_PRIMARY) or (vowel_stress[stressed_syllable + 1] < STRESS_IS_PRIMARY):
                    vowel_stress[stressed_syllable] = max_stress
    # STRESSPOSN_1L (first syllable) has no case in espeak's switch: the secondary-stress
    # loop below places the primary on the first eligible vowel (trochaic), so we do
    # nothing here.
    elif tr.stress_rule == K.STRESSPOSN_1SL:  # Malayalam: 1st syllable, unless the 1st vowel
        # is short and the 2nd is long (then the 2nd): കഠോര -> kɐʈʰˈoːɾɐ (1st a short, 2nd o: long).
        if stressed_syllable == 0:
            stressed_syllable = 1
            if vowel_length[1] == 0 and vowel_count > 2 and vowel_length[2] > 0:
                stressed_syllable = 2
            vowel_stress[stressed_syllable] = STRESS_IS_PRIMARY
            max_stress = STRESS_IS_PRIMARY
    elif tr.stress_rule == K.STRESSPOSN_1R:
        if stressed_syllable == 0:
            stressed_syllable = vowel_count - 1
            while stressed_syllable > 0:
                if vowel_stress[stressed_syllable] < STRESS_IS_DIMINISHED:
                    vowel_stress[stressed_syllable] = STRESS_IS_PRIMARY
                    break
                stressed_syllable -= 1
            max_stress = STRESS_IS_PRIMARY
    elif tr.stress_rule == K.STRESSPOSN_3R:  # antepenultimate (e.g. Macedonian)
        if stressed_syllable == 0:
            stressed_syllable = vowel_count - 3
            if stressed_syllable < 1:
                stressed_syllable = 1
            vowel_stress[stressed_syllable] = STRESS_IS_PRIMARY
            max_stress = STRESS_IS_PRIMARY
    elif tr.stress_rule == K.STRESSPOSN_EU:  # Basque: primary on 2nd syllable, secondary on last
        if stressed_syllable == 0 and vowel_count > 2:
            for ix in range(1, vowel_count):
                vowel_stress[ix] = STRESS_IS_DIMINISHED
            stressed_syllable = 2
            if max_stress <= STRESS_IS_DIMINISHED:
                vowel_stress[2] = STRESS_IS_PRIMARY
            max_stress = STRESS_IS_PRIMARY
            if vowel_count > 3:
                vowel_stress[vowel_count - 1] = STRESS_IS_SECONDARY
    elif tr.stress_rule == K.STRESSPOSN_SYLCOUNT:  # Russian: guess stress from syllable count
        # port of dictionary.c case STRESSPOSN_SYLCOUNT — for words without an explicit
        # (dictionary) stress, guess from the syllable count and the final phoneme type.
        if stressed_syllable == 0:
            guess_ru = (0, 0, 1, 1, 2, 3, 3, 4, 5, 6, 7, 7, 8, 9, 10, 11)
            guess_ru_v = (0, 0, 1, 1, 2, 2, 3, 3, 4, 5, 6, 7, 7, 8, 9, 10)  # final = vowel
            guess_ru_t = (0, 0, 1, 2, 3, 3, 3, 4, 5, 6, 7, 7, 7, 8, 9, 10)  # final = unvoiced stop
            stressed_syllable = vowel_count - 3
            if vowel_count < 16:
                final_type = phonetic[-1][1].type if phonetic else None
                if final_type == phVOWEL:
                    stressed_syllable = guess_ru_v[vowel_count]
                elif final_type == phSTOP:
                    stressed_syllable = guess_ru_t[vowel_count]
                else:
                    stressed_syllable = guess_ru[vowel_count]
            if stressed_syllable < 1:
                stressed_syllable = 1
            vowel_stress[stressed_syllable] = STRESS_IS_PRIMARY
            max_stress = STRESS_IS_PRIMARY
    elif tr.stress_rule in (K.STRESSPOSN_2LLH, K.STRESSPOSN_2L):  # Korean (2LLH) / 2L
        # port of dictionary.c case STRESSPOSN_2LLH -> STRESSPOSN_2L: 2LLH keeps stress on the
        # first syllable when it is heavy or the second is light; otherwise (light-then-heavy) it
        # falls through to the plain 2L arm, which stresses the second syllable. Plain 2L always
        # falls through. The marked-stress guard (only force PRIMARY when nothing else is marked)
        # mirrors the C `max_stress == STRESS_IS_DIMINISHED` check.
        fall_through = tr.stress_rule == K.STRESSPOSN_2L
        if tr.stress_rule == K.STRESSPOSN_2LLH:
            fall_through = not (syllable_weight[1] > 0 or syllable_weight[2] == 0)
        if fall_through and stressed_syllable == 0 and vowel_count > 2:
            stressed_syllable = 2
            if max_stress == STRESS_IS_DIMINISHED:
                vowel_stress[2] = STRESS_IS_PRIMARY
            max_stress = STRESS_IS_PRIMARY
    elif tr.stress_rule == K.STRESSPOSN_1RH:  # last heaviest syllable, excl. final (hi/mr)
        if stressed_syllable == 0:
            max_weight = -1
            for ix in range(1, vowel_count - 1):
                if vowel_stress[ix] < STRESS_IS_DIMINISHED:
                    wt = syllable_weight[ix]
                    if wt >= max_weight:
                        max_weight = wt
                        stressed_syllable = ix
            if syllable_weight[vowel_count - 1] == 2 and max_weight < 2:
                stressed_syllable = vowel_count - 1
            elif max_weight <= 0:
                stressed_syllable = 1
            vowel_stress[stressed_syllable] = STRESS_IS_PRIMARY
            max_stress = STRESS_IS_PRIMARY
    elif tr.stress_rule == K.STRESSPOSN_1RU:  # last syllable, or before an explicit
        if stressed_syllable == 0:             # unstressed vowel (Turkish/Azerbaijani)
            stressed_syllable = vowel_count - 1
            for ix in range(1, vowel_count):
                if vowel_stress[ix] == STRESS_IS_UNSTRESSED:
                    stressed_syllable = ix - 1
                    break
            vowel_stress[stressed_syllable] = STRESS_IS_PRIMARY
            max_stress = STRESS_IS_PRIMARY
    elif tr.stress_rule == K.STRESSPOSN_GREENLANDIC:  # kl (Greenlandic)
        # port of dictionary.c case STRESSPOSN_GREENLANDIC: demote any marked (consonant-cluster)
        # primary to secondary and give every long vowel secondary stress, then place the primary
        # on the last long vowel; with none, the penult (or, for >4 syllables, the antepenult).
        long_vowel = 0
        for ix in range(1, vowel_count):
            if vowel_stress[ix] == STRESS_IS_PRIMARY:
                vowel_stress[ix] = STRESS_IS_SECONDARY
            if vowel_length[ix] > 0:
                long_vowel = ix
                vowel_stress[ix] = STRESS_IS_SECONDARY
        if stressed_syllable == 0:
            if long_vowel > 0:
                stressed_syllable = long_vowel
            elif vowel_count > 5:
                stressed_syllable = vowel_count - 3
            else:
                stressed_syllable = vowel_count - 1
        vowel_stress[stressed_syllable] = STRESS_IS_PRIMARY
        max_stress = STRESS_IS_PRIMARY

    # S_FINAL_VOWEL_UNSTRESSED: don't allow stress on a word-final vowel (eu/ro)
    if ((stressflags & K.S_FINAL_VOWEL_UNSTRESSED) and (control & 2) == 0
            and vowel_count > 2 and max_stress_input < STRESS_IS_SECONDARY
            and vowel_stress[vowel_count - 1] == STRESS_IS_PRIMARY):
        if phonetic and _ph_is_vowel(phonetic[-1][1]):
            vowel_stress[vowel_count - 1] = STRESS_IS_UNSTRESSED
            vowel_stress[vowel_count - 2] = STRESS_IS_PRIMARY

    if not unstressed_word_input:
        if (stressflags & K.S_2_SYL_2) and vowel_count == 3:
            # two-syllable word: if one syllable has primary stress, give the other secondary
            if vowel_stress[1] == STRESS_IS_PRIMARY:
                vowel_stress[2] = STRESS_IS_SECONDARY
            if vowel_stress[2] == STRESS_IS_PRIMARY:
                vowel_stress[1] = STRESS_IS_SECONDARY
        if (stressflags & K.S_INITIAL_2) and vowel_stress[1] < STRESS_IS_DIMINISHED:
            # only one syllable before the primary -> give it secondary (pt aquele -> ˌɐkˈelɨ)
            if vowel_count > 3 and vowel_stress[2] >= STRESS_IS_PRIMARY:
                vowel_stress[1] = STRESS_IS_SECONDARY

    # guess complete stress pattern (secondary stresses)
    stress = STRESS_IS_PRIMARY if max_stress < STRESS_IS_PRIMARY else STRESS_IS_SECONDARY
    done = False
    first_primary = 0
    # exclude a removed suffix's trailing vowels from the auto-secondary pass (espeak runs
    # this on the stem only); never go below 1 so a stem vowel is still considered.
    sec_count = max(1, vowel_count - suffix_vowels) if suffix_vowels else vowel_count
    for v in range(1, sec_count):
        if vowel_stress[v] < STRESS_IS_DIMINISHED:
            if (stressflags & 0x10) and (stress < STRESS_IS_PRIMARY) and (v == vowel_count - 1):
                pass  # S_FINAL_NO_2
            elif (stressflags & 0x8000) and not done:
                vowel_stress[v] = stress
                done = True
                stress = STRESS_IS_SECONDARY
            elif (vowel_stress[v - 1] <= STRESS_IS_UNSTRESSED) and (
                (vowel_stress[v + 1] <= STRESS_IS_UNSTRESSED)
                or (stress == STRESS_IS_PRIMARY and vowel_stress[v + 1] <= STRESS_IS_NOT_STRESSED)
            ):
                if stress == STRESS_IS_SECONDARY and (stressflags & K.S_NO_AUTO_2):
                    continue
                # S_2_TO_HEAVY (et/fi): don't put secondary on a light syllable if a heavy one
                # follows (within the word, excluding the last syllable), nor on a light syllable
                # directly followed by a heavy one (följetonist: light 'o' before heavy 'nist'
                # -> no ˌo, so fˈøʎjetonist not fˈøʎjetˌonist).
                if v > 1 and (stressflags & K.S_2_TO_HEAVY) and syllable_weight[v] == 0:
                    if any(syllable_weight[i] > 0 for i in range(v, vowel_count - 1)):
                        continue
                    if syllable_weight[v + 1] > 0:
                        continue
                vowel_stress[v] = stress
                done = True
                stress = STRESS_IS_SECONDARY
        if vowel_stress[v] >= STRESS_IS_PRIMARY:
            if first_primary == 0:
                first_primary = v
            elif stressflags & K.S_FIRST_PRIMARY:
                vowel_stress[v] = STRESS_IS_SECONDARY

    if unstressed_word and tonic < 0:
        tonic = tr.unstressed_wd1 if vowel_count <= 2 else tr.unstressed_wd2

    if (unstressed_word and max_stress_input < STRESS_IS_PRIMARY
            and tr.stress_rule in (K.STRESSPOSN_1L, K.STRESSPOSN_1RH) and vowel_count > 3
            and not (dict_flags & K.FLAG_STRESS_END)):
        # a $u word with no lexical accent of its own (smj derived nouns allelattjaj, bn pronouns)
        # carries no primary: reduce the position-rule (1L/1RH) primary to secondary so the clause tonic
        # lands on its natural main syllable (the last/heaviest, via max_stress_posn's last-wins scan
        # below) instead of the first. $u+ entries (FLAG_STRESS_END, smj avtagattjaj) keep first stress.
        for _v in range(1, vowel_count):
            if vowel_stress[_v] == STRESS_IS_PRIMARY:
                vowel_stress[_v] = STRESS_IS_SECONDARY

    max_stress = STRESS_IS_DIMINISHED
    max_stress_posn = 0
    for v in range(1, vowel_count):
        if vowel_stress[v] >= max_stress:
            max_stress = vowel_stress[v]
            max_stress_posn = v
    # Clause tonic on a $u word whose nonsyllabic onset schwa @- outranks every real vowel.
    # espeak runs SetWordStress(tonic=-1) first: a $u word reduces its real vowels to
    # unstressed_wd1 (monosyllable) / unstressed_wd2 (polysyllable), but the nonsyllabic onset
    # @- (from a "C) r"-type rule) is untouched by SetWordStress and keeps its translate-time
    # default stress 1 (translate.c next_stress). The separate intonation pass
    # (count_pitch_vowels) then counts EVERY phVOWEL — @- included (SFLAG_SYLLABLE, translate.c
    # phVOWEL test ignores phNONSYLLABIC) — as a pitch syllable and places the clause tonic
    # (PRIMARY_LAST) on the LAST max-stress one. When unstressed_wd reduces the real vowels
    # BELOW @-'s level 1 (wd==0, e.g. la/lt), the @- is the unique maximum and takes the tonic,
    # rendering as a bare ˈ before the following cluster (la pro -> pˈrɔ, trans -> tˈrans). The
    # real vowels keep their reduced level, so no visible mark lands on them.
    nonsyl_tonic_pi = -1
    if (tonic >= STRESS_IS_PRIMARY and unstressed_word
            and max_stress_input < STRESS_IS_PRIMARY):
        _reduced = tr.unstressed_wd1 if vowel_count <= 2 else tr.unstressed_wd2
        if _reduced < STRESS_IS_UNSTRESSED:  # real vowels reduce below @-'s pitch level 1
            for _pi in range(len(phonetic) - 1, -1, -1):
                _p = phonetic[_pi][1]
                if _p.type == phVOWEL and "nonsyllabic" in _p.flags:
                    nonsyl_tonic_pi = _pi
                    break
            if nonsyl_tonic_pi >= 0:
                # reduce the real vowels naturally; the @- carries PRIMARY_LAST (marked below)
                tonic = _reduced
    if tonic >= 0:
        # A first-syllable-stress (1L) CONTENT word with no inherent stress (every vowel
        # diminished/unstressed, e.g. ga arsa -> @rs@) takes the clause tonic on syllable 1,
        # following the language's stress direction — not the last syllable max_stress_posn
        # (last-wins ties) selects. A $u function word (nl onze) keeps the last, so exclude it.
        if (max_stress <= STRESS_IS_UNSTRESSED and vowel_count > 1
                and tr.stress_rule == K.STRESSPOSN_1L and not unstressed_word):
            max_stress_posn = 1
        elif (tr.config.get("indic_schwa") and unstressed_word and vowel_count > 1
                and tr.stress_rule == K.STRESSPOSN_1L
                and max_stress_posn == vowel_count - 1
                and phoneme_str.rstrip("'\",%/ ")[-1:] == "V"):
            # A $u function word normally keeps the last syllable (nl onze -> ɔnzˈə), but when a 1L
            # Indic word ends in the inherent schwa V (DELETED word-finally), the clause tonic landing
            # there is lost (bn আমার = amarV -> the V drops, leaving only ˌamaɾ); use syllable 1 (ˈamaɾ).
            max_stress_posn = 1
        if (tonic > max_stress) or (max_stress <= STRESS_IS_PRIMARY):
            vowel_stress[max_stress_posn] = tonic
        max_stress = tonic
        # el: a multi-syllable $u (function) word carrying the clause accent takes it on the
        # LAST syllable, its lexical accent dropping to secondary (είμαστε -> ˌimastˈe). Short
        # $u words (<=2 vowels) keep the accent on the accented syllable (είμαι -> ˈime).
        if (getattr(tr, "u_clause_final", False) and unstressed_word
                and tonic >= STRESS_IS_PRIMARY and vowel_count >= 4
                and max_stress_posn != vowel_count - 1):
            vowel_stress[max_stress_posn] = STRESS_IS_SECONDARY
            vowel_stress[vowel_count - 1] = tonic
            max_stress_posn = vowel_count - 1
        # haw (Hawaiian): a long (macron) vowel carrying the lexical primary on a NON-final
        # syllable drops to secondary and the clause nucleus moves to the final syllable
        # (kākou: k'a:kou -> kˌaːkoˈu, the long ā demoted, primary on the final u).
        if (tr.config.get("macron_clause_final") and tonic >= STRESS_IS_PRIMARY
                and max_stress_posn != vowel_count - 1
                and 1 <= max_stress_posn < len(vowel_length)
                and vowel_length[max_stress_posn] > 0):
            # only a long MONOPHTHONG (macron, kākou a:) demotes; a DIPHTHONG carrying the
            # primary (maila ai, also vowel_length>0) keeps its accent (mˈaila, not mˌailˈa).
            _vi = 0
            _msp_ph = None
            for _m, _p in phonetic:
                if _ph_is_vowel(_p):  # @- excluded by its phNONSYLLABIC flag (syllabic in fr/vi)
                    _vi += 1
                    if _vi == max_stress_posn:
                        _msp_ph = _p
                        break
            if _msp_ph is not None and _msp_ph.starttype == _msp_ph.endtype:
                vowel_stress[max_stress_posn] = STRESS_IS_SECONDARY
                vowel_stress[vowel_count - 1] = tonic
                max_stress_posn = vowel_count - 1

    # A clause-tonic word with NO syllabic vowel (vowel_count == 1: its only vowel is a
    # nonsyllabic schwa @-, excluded from the count) gets no stress mark from the loops above
    # (max_stress_posn stays 0). espeak's intonation, however, treats @- as a syllable
    # (MakePhonemeList counts it: translate.c phVOWEL test ignores phNONSYLLABIC) and, finding
    # no primary, promotes the highest-stress (here only) syllable to the clause nucleus
    # (count_pitch_vowels PRIMARY_LAST) — so an isolated `ən` renders ˈən. Mark the LAST
    # nonsyllabic vowel for the output loop to stress. (The $u onset-@- case above may already
    # have set nonsyl_tonic_pi; don't clobber it — tonic was lowered to the reduced level there.)
    if (nonsyl_tonic_pi < 0 and tonic >= STRESS_IS_PRIMARY and vowel_count == 1
            and not unstressed_word):
        for _pi in range(len(phonetic) - 1, -1, -1):
            _p = phonetic[_pi][1]
            if _p.type == phVOWEL and "nonsyllabic" in _p.flags:
                nonsyl_tonic_pi = _pi
                break
    # produce output: walk phonetic, insert stress mnemonic before each vowel
    opt_length = getattr(tr, "it_lengthen", 0)  # LOPT_IT_LENGTHEN
    out = []
    v = 1
    prev_v = 0
    prev_v_stress = 0
    for _pi, (mnem, ph) in enumerate(phonetic):
        if _nonsyllabic_before_vowel(ph) and _pi + 1 < len(phonetic) \
                and _ph_is_vowel(phonetic[_pi + 1][1]):
            # yue/zh `ng` onset before a vowel is not a syllable nucleus (see get_vowel_stress):
            # emit it as a plain consonant so `v` stays aligned with the real vowels and the
            # stress mark lands on the following vowel, not the onset.
            out.append(mnem)
            continue
        if _pi == nonsyl_tonic_pi:
            # clause nucleus on a word with no syllabic vowel: stress its (only) nonsyllabic
            # vowel (ən -> ˈən). espeak's intonation places PRIMARY_LAST here.
            out.append(_STRESS_MNEM.get(STRESS_IS_PRIMARY, ""))
            out.append(mnem)
            continue
        if (opt_length & 1) and mnem == ":":
            # remove a lengthen indicator from a non-stressed (or non-max-stress) syllable
            if opt_length & 0x10:
                shorten = prev_v != max_stress_posn
            else:
                shorten = prev_v_stress < STRESS_IS_PRIMARY
            if shorten:
                continue
        _syl_cons = (not _ph_is_vowel(ph) and ph.type not in (phINVALID, phPAUSE)
                     and _pi + 1 < len(phonetic)
                     and _is_syllabic_marker(phonetic[_pi + 1][0], phonetic[_pi + 1][1]))
        if _ph_is_vowel(ph) or _syl_cons:
            # @- excluded from the vowel count in get_vowel_stress when nonsyllabic (its
            # phNONSYLLABIC flag, _ph_is_vowel False) — must also be skipped here or `v`
            # desyncs and the stress mark lands on it (eo pra -> pˈra instead of prˈa). In
            # fr/vi @- is syllabic (a real nucleus), so it is counted and stressed here.
            # A consonant directly before the phonSYLLABIC `-` is also a syllable nucleus here
            # (dictionary.c:1391 `*p == phonSYLLABIC`), matching the extra slot get_vowel_stress
            # counted — so `v` stays aligned with vowel_stress.
            v_stress = vowel_stress[v]
            if v_stress <= STRESS_IS_UNSTRESSED:
                if (v > 1) and (max_stress >= 2) and (stressflags & K.S_FINAL_DIM) and (v == vowel_count - 1):
                    v_stress = STRESS_IS_DIMINISHED
                elif (stressflags & K.S_NO_DIM) or (v == 1) or (v == vowel_count - 1):
                    v_stress = STRESS_IS_UNSTRESSED
                elif (v == vowel_count - 2) and (vowel_stress[vowel_count - 1] <= STRESS_IS_UNSTRESSED):
                    v_stress = STRESS_IS_UNSTRESSED
                else:
                    if (vowel_stress[v - 1] < STRESS_IS_DIMINISHED) or ((stressflags & K.S_MID_DIM) == 0):
                        v_stress = STRESS_IS_DIMINISHED
                        vowel_stress[v] = v_stress
            # Emit the diminished "%%" marker too: espeak carries the DIMINISHED level into
            # the phoneme list so ChangeIfDiminished programs fire (uk unstressed e -> ɪ via
            # ChangeIfDiminished(I2) on mid-word vowels). The renderer still shows no mark for
            # it (GetTranslatedPhonemeString only marks stress > 1), so visible output only
            # changes for phonemes that actually carry a ChangeIfDiminished program.
            if v_stress > STRESS_IS_UNSTRESSED or v_stress == STRESS_IS_DIMINISHED:
                out.append(_STRESS_MNEM.get(v_stress, ""))
            prev_v = v
            prev_v_stress = v_stress
            v += 1
        out.append(mnem)
    return "".join(out)


def change_word_stress(tr, phoneme_str, mnem_index, new_stress, pick_last=False):
    """Port of ChangeWordStress (translateword.c:705). Re-stresses an ALREADY-rendered
    phoneme string (one that carries its stress mnemonics). espeak calls this on the last
    word of a clause when the word's dict entry has FLAG_STRESS_END/FLAG_STRESS_END2
    (`$u+`/`$u1+`/`$u2+`/`$u3+`): the word was rendered with its lexical/unstressed marks,
    then this PROMOTES the FIRST syllable already at max_stress to the clause primary (4).

    Unlike set_word_stress(tonic=4) — which puts the tonic at the LAST max-stress vowel
    (max_stress_posn, last-wins) — ChangeWordStress promotes the FIRST one. That distinction
    is exactly the ro pronoun divergence (dumneata: dˈumneatˌa not dˌumneatˈa).

    `pick_last=True` instead promotes the LAST max-stress syllable: this models the
    intonation nucleus (intonation.c count_pitch_vowels, tone_posn = last max-stress) for a
    clause-final $u word WITHOUT FLAG_STRESS_END, whose dict stressed_syllable ($u1/$u2/$u3)
    only positions secondaries — the clause accent lands on the last (cărora -> kˌəɾoɾˈa)."""
    toks = mnem_index.tokenize(phoneme_str)
    if not toks:
        return phoneme_str
    vowel_stress, phonetic, vowel_count, _primary_posn, max_stress = get_vowel_stress(toks)
    if new_stress >= STRESS_IS_PRIMARY:
        # promote the FIRST (or, pick_last, LAST) vowel already at max_stress to new_stress
        rng = range(vowel_count - 1, 0, -1) if pick_last else range(1, vowel_count)
        for ix in rng:
            if vowel_stress[ix] >= max_stress:
                vowel_stress[ix] = new_stress
                break
    else:
        # demote: cap every vowel stronger than new_stress down to it
        for ix in range(1, vowel_count):
            if vowel_stress[ix] > new_stress:
                vowel_stress[ix] = new_stress
    # re-emit: a stress mnemonic before each vowel that is DIMINISHED or > UNSTRESSED
    out = []
    v = 1
    for _pi, (mnem, ph) in enumerate(phonetic):
        if _nonsyllabic_before_vowel(ph) and _pi + 1 < len(phonetic) \
                and _ph_is_vowel(phonetic[_pi + 1][1]):
            out.append(mnem)
            continue
        _syl_cons = (not _ph_is_vowel(ph) and ph.type not in (phINVALID, phPAUSE)
                     and _pi + 1 < len(phonetic)
                     and _is_syllabic_marker(phonetic[_pi + 1][0], phonetic[_pi + 1][1]))
        if _ph_is_vowel(ph) or _syl_cons:
            vs = vowel_stress[v]
            if vs == STRESS_IS_DIMINISHED or vs > STRESS_IS_UNSTRESSED:
                out.append(_STRESS_MNEM.get(vs, ""))
            v += 1
        out.append(mnem)
    return "".join(out)


def _compute_weights(phonetic, vowel_length, syllable_weight):
    # port of the heavy/light syllable loop (dictionary.c:1002-1026).
    # espeak's consonant_types[16] = {0,0,0,1,1,1,1,1,1,1,0,...} indexed by phoneme type
    # (phVOWEL=2 -> 0): a *consonant* is phLIQUID..phVIRTUAL. phVOWEL is NOT a consonant, so a
    # following vowel does NOT close the syllable (hiatus). Including phVOWEL here wrongly made
    # V.V syllables heavy (ko su-+u- -> 2LLH stressed the wrong syllable; 키스의 -> khˈisɯˌɯj).
    consonant_types = {phLIQUID, K.phSTOP, K.phVSTOP,
                       K.phFRICATIVE, K.phVFRICATIVE, K.phNASAL, K.phVIRTUAL}
    ix = 1
    n = len(phonetic)
    i = 0
    while i < n:
        mnem, ph = phonetic[i]
        if _ph_is_vowel(ph):
            weight = 0
            nxt = phonetic[i + 1][1] if i + 1 < n else None
            lengthened = nxt is not None and nxt.mnemonic == ":"
            if lengthened or ("long" in ph.flags):
                weight += 1
            vowel_length[ix] = weight
            j = i + 1
            if lengthened:
                j += 1
            c1 = phonetic[j][1] if j < n else None
            c2 = phonetic[j + 1][1] if j + 1 < n else None
            if c1 is not None and c1.type in consonant_types and (
                (c2 is None or c2.type != phVOWEL) or ("long" in c1.flags)
            ):
                weight += 1
            syllable_weight[ix] = weight
            ix += 1
        i += 1


def phLIQUID_T():
    return 4  # phLIQUID


class MatchRecord:
    __slots__ = ("points", "phonemes", "end_type", "del_fwd")

    def __init__(self):
        self.points = 0
        self.phonemes = ""
        self.end_type = 0
        self.del_fwd = None


def _letter_group_no(b):
    g = b - ord("A")
    if g < 0:
        g += 256
    return g


def match_rule(tr, buf, ix_word, group_length, rules, word_flags, dict_flags):
    """Port of MatchRule (dictionary.c:1484).

    buf: word bytes, framed as b"\\x00 <word> \\x00". ix_word: index of current group.
    rules: list[CompiledRule]. Returns (MatchRecord best, new_ix_word).
    """
    best = MatchRecord()
    total_consumed = 0
    common_phonemes = None  # unused (each rule carries its phonemes)

    for cr in rules:
        prog = cr.prog
        klen = len(prog)
        k = 0
        check_atstart = False
        consumed = 0
        distance_left = -2
        distance_right = -6
        failed = 0
        unpron_ignore = word_flags & K.FLAG_UNPRON_TEST
        match_type = 0
        letter_w = 0
        last_letter_w = 0
        points = 1
        end_type = 0
        del_fwd = None

        pre_ptr = ix_word
        post_ptr = ix_word + group_length

        while not failed:
            if k >= klen:
                failed = 2  # reached end of instruction stream => matched
                break
            rb = prog[k]; k += 1
            add_points = 0

            if rb <= K.RULE_LINENUM:
                if rb == K.RULE_PRE_ATSTART:
                    check_atstart = True
                    unpron_ignore = 0
                    match_type = K.RULE_PRE
                elif rb == K.RULE_PRE:
                    match_type = K.RULE_PRE
                    if word_flags & K.FLAG_UNPRON_TEST:
                        failed = 1
                elif rb == K.RULE_POST:
                    match_type = K.RULE_POST
                elif rb == K.RULE_CONDITION:
                    condition_num = prog[k]; k += 1
                    if condition_num >= 32:
                        if (tr.dict_condition & (1 << (condition_num - 32))) != 0:
                            failed = 1
                    else:
                        if (tr.dict_condition & (1 << condition_num)) == 0:
                            failed = 1
                    if not failed:
                        points += 1
                # RULE_PHONEMES / RULE_PH_COMMON / RULE_LINENUM not present in prog
                continue

            if match_type == 0:
                # consume this letter
                letter = buf[post_ptr] if post_ptr < len(buf) else 0
                post_ptr += 1
                if (letter == rb) or (letter == REPLACED_E and rb == ord("e")):
                    if (letter & 0xc0) != 0x80:
                        add_points = 21
                    consumed += 1
                else:
                    failed = 1
            elif match_type == K.RULE_POST:
                distance_right += 6
                if distance_right > 18:
                    distance_right = 19
                last_letter_w = letter_w
                if post_ptr - 1 >= 0 and buf[post_ptr - 1] == 0:
                    failed = 1
                else:
                    letter_w, nb = _utf8_in(buf, post_ptr)
                    letter_xbytes = nb - 1
                    letter = buf[post_ptr] if post_ptr < len(buf) else 0
                    post_ptr += 1
                    failed, add_points, post_ptr, k, rule_end, rule_del_fwd = _match_post(
                        tr, rb, prog, k, buf, letter, letter_w, letter_xbytes,
                        last_letter_w, distance_right, post_ptr, word_flags, dict_flags,
                        ix_word + group_length + consumed, ix_word + group_length)
                    if rule_end:
                        end_type = rule_end
                    if rule_del_fwd is not None:
                        del_fwd = rule_del_fwd
            elif match_type == K.RULE_PRE:
                distance_left += 2
                if distance_left > 18:
                    distance_left = 19
                if pre_ptr < 0 or buf[pre_ptr] == 0:
                    failed = 1
                else:
                    last_letter_w, _ = _utf8_in(buf, pre_ptr)
                    pre_ptr -= 1
                    letter_w, nb = _utf8_back(buf, pre_ptr)
                    letter_xbytes = nb - 1
                    letter = buf[pre_ptr] if pre_ptr >= 0 else 0
                    failed, add_points, pre_ptr, k = _match_pre(
                        tr, rb, prog, k, buf, letter, letter_w, letter_xbytes,
                        last_letter_w, distance_left, distance_right, pre_ptr, word_flags, dict_flags,
                        ix_word + group_length + consumed)

            if failed == 0:
                points += add_points

        if failed == 2 and unpron_ignore == 0:
            if (not check_atstart) or (pre_ptr - 1 >= 0 and buf[pre_ptr - 1] == ord(" ")):
                if check_atstart:
                    points += 4
                if points >= best.points:
                    best.points = points
                    best.phonemes = cr.phonemes
                    best.end_type = end_type
                    best.del_fwd = del_fwd
                    total_consumed = consumed

    total_consumed += group_length
    if total_consumed == 0:
        total_consumed = 1
    new_ix = ix_word + total_consumed
    if best.points == 0:
        best.phonemes = ""
    return best, new_ix


def _match_post(tr, rb, prog, k, buf, letter, letter_w, letter_xbytes,
                last_letter_w, distance_right, post_ptr, word_flags, dict_flags,
                match_end_ptr=None, group_end=None):
    failed = 0
    add_points = 0
    end_type = 0
    del_fwd = None
    if rb == K.RULE_LETTERGP:
        letter_group = _letter_group_no(prog[k]); k += 1
        if tr.is_letter(letter_w, letter_group):
            lg_pts = 20
            if letter_group == 2:
                lg_pts = 19
            add_points = lg_pts - distance_right
            post_ptr += letter_xbytes
        else:
            failed = 1
    elif rb == K.RULE_LETTERGP2:
        letter_group = _letter_group_no(prog[k]); k += 1
        n_bytes = _is_letter_group(tr, buf, post_ptr - 1, letter_group, 0)
        if n_bytes >= 0:
            add_points = 20 - distance_right
            post_ptr += (n_bytes - 1)
        else:
            failed = 1
    elif rb == K.RULE_NOTVOWEL:
        if tr.is_letter(letter_w, 0) or (letter_w == ord(" ") and (word_flags & K.FLAG_SUFFIX_VOWEL)):
            failed = 1
        else:
            add_points = 20 - distance_right
            post_ptr += letter_xbytes
    elif rb == K.RULE_DIGIT:
        if is_digit(letter_w):
            add_points = 20 - distance_right
            post_ptr += letter_xbytes
        elif tr.config.get("tone_numbers"):
            # tone languages: a 'D' post-rule also matches when no digit is present
            # (dictionary.c:1700-1703); back up so the missing digit isn't consumed.
            add_points = 20 - distance_right
            post_ptr -= 1
        else:
            failed = 1
    elif rb == K.RULE_NONALPHA:
        if not is_alpha(letter_w):
            add_points = 21 - distance_right
            post_ptr += letter_xbytes
        else:
            failed = 1
    elif rb == K.RULE_SPELLING:
        # 'W': zero-width assertion — matches only while spelling the word letter-by-letter
        # (pt 'm (_W -> Em;' palatalises a spelled consonant before the next letter). Undo
        # the speculative letter read since this consumes no input.
        post_ptr -= (1 + letter_xbytes)
        if getattr(tr, "_spelling", False):
            add_points = 20 - distance_right
        else:
            failed = 1
    elif rb == K.RULE_DOUBLE:
        if letter_w == last_letter_w:
            add_points = 21 - distance_right
            post_ptr += letter_xbytes
        else:
            failed = 1
    elif rb == K.RULE_DOLLAR:
        post_ptr -= 1
        command = prog[k]; k += 1
        # espeak's DollarRule keys the part-word lookup off the MATCH end
        # (word_start + consumed + group_length, dictionary.c:3030), independent of how far the
        # post-context has scanned. da `el (l$p_alt` must check `appel`, not the scanned `appell`.
        part_end = match_end_ptr if match_end_ptr is not None else post_ptr
        failed, add_points = _dollar_rule(tr, command, word_flags, dict_flags, buf, part_end)
        if command == K.DOLLAR_UNPR:
            # $unpron marks a cluster as "unpronounceable" for the FLAG_UNPRON_TEST rerun
            # (dictionary.c:1725 sets match.end_type = SUFX_UNPRON). Carry it on the rule's
            # end_type so Unpronouncable2 sees it (es `_) d ($unpr` -> "dr" is spelled).
            end_type = K.SUFX_UNPRON
    elif rb == ord("-"):
        if letter == ord("-") or (letter == ord(" ") and (word_flags & K.FLAG_HYPHEN_AFTER)):
            add_points = 22 - distance_right
        else:
            failed = 1
    elif rb == K.RULE_SYLLABLE:
        syllable_count = 1
        while k < len(prog) and prog[k] == K.RULE_SYLLABLE:
            k += 1
            syllable_count += 1
        p = post_ptr + letter_xbytes
        vowel_count = 0
        vowel = 0
        lw = letter_w
        while lw != K.RULE_SPACE and lw != 0:
            if vowel == 0 and tr.is_letter(lw, K.LETTERGP_VOWEL2):
                vowel_count += 1
            vowel = tr.is_letter(lw, K.LETTERGP_VOWEL2)
            lw, nb = _utf8_in(buf, p)
            p += nb
        if syllable_count <= vowel_count:
            add_points = 18 + syllable_count - distance_right
        else:
            failed = 1
    elif rb == K.RULE_NOVOWELS:
        p = post_ptr + letter_xbytes
        lw = letter_w
        ok = True
        while lw != K.RULE_SPACE and lw != 0:
            if tr.is_letter(lw, K.LETTERGP_VOWEL2):
                failed = 1
                ok = False
                break
            lw, nb = _utf8_in(buf, p)
            p += nb
        if ok and not failed:
            add_points = 19 - distance_right
    elif rb == K.RULE_INC_SCORE:
        post_ptr -= 1
        add_points = 20
    elif rb == K.RULE_DEC_SCORE:
        post_ptr -= 1
        add_points = -20
    elif rb == K.RULE_DEL_FWD:
        # find the next 'e' between the group end and the current scan position; on the
        # winning match it is rewritten to REPLACED_E so a later group skips it
        # (dictionary.c:1814-1822 + 2322-2323; English silent-e logic).
        if group_end is not None:
            for p in range(group_end, post_ptr):
                if 0 <= p < len(buf) and buf[p] == ord("e"):
                    del_fwd = p
                    break
    elif rb == K.RULE_ENDING:
        # 3 bytes: flags(16-23), flags(8-15), length|0x80 -> end_type
        et = (prog[k] << 16) | ((prog[k + 1] & 0x7f) << 8) | (prog[k + 2] & 0x7f)
        k += 3
        # LANG=tr: don't match a suffix if no previous syllable (LOPT_SUFFIX). en: off.
        if (tr.word_vowel_count == 0) and not (et & K.SUFX_P) and \
                (tr.config.get("param_suffix", 0) & 1):
            failed = 1
        else:
            end_type = et
    elif rb == K.RULE_NO_SUFFIX:
        if word_flags & K.FLAG_SUFFIX_REMOVED:
            failed = 1
        else:
            post_ptr -= 1
            add_points = 1
    elif rb == K.RULE_SKIPCHARS:
        # '(Jxy': skip word characters until the next rule element (xy) matches it
        # (dictionary.c:1788). The target prog[k] is NOT consumed here — the next iteration
        # matches it. Used by lv `L25) e (CJL18_` (skip 'tflīģeļ' to the L18 suffix 'u').
        p = post_ptr - 1            # first byte of the current letter
        lw = letter_w
        target = prog[k]
        is_lg = (target == K.RULE_LETTERGP2)
        tgroup = _letter_group_no(prog[k + 1]) if is_lg else None
        while lw != K.RULE_SPACE and lw != 0:
            if is_lg:
                if _is_letter_group(tr, buf, p, tgroup, 0) >= 0:
                    break
            elif lw == target:
                break
            _, nb = _utf8_in(buf, p)
            p += nb
            lw, _ = _utf8_in(buf, p)
        if lw == K.RULE_SPACE or lw == 0:
            failed = 1
        else:
            post_ptr = p            # next iteration reads the match and processes prog[k]
    else:
        if letter == rb:
            if (letter & 0xc0) != 0x80:
                add_points = 21 - distance_right
        else:
            failed = 1
    return failed, add_points, post_ptr, k, end_type, del_fwd


def _match_pre(tr, rb, prog, k, buf, letter, letter_w, letter_xbytes,
               last_letter_w, distance_left, distance_right, pre_ptr, word_flags, dict_flags,
               match_end_ptr=None):
    failed = 0
    add_points = 0
    if rb == K.RULE_LETTERGP:
        letter_group = _letter_group_no(prog[k]); k += 1
        if tr.is_letter(letter_w, letter_group):
            lg_pts = 20
            if letter_group == 2:
                lg_pts = 19
            add_points = lg_pts - distance_left
            pre_ptr -= letter_xbytes
        else:
            failed = 1
    elif rb == K.RULE_LETTERGP2:
        letter_group = _letter_group_no(prog[k]); k += 1
        n_bytes = _is_letter_group(tr, buf, pre_ptr, letter_group, 1)
        if n_bytes >= 0:
            add_points = 20 - distance_right
            pre_ptr -= (n_bytes - 1)
        else:
            failed = 1
    elif rb == K.RULE_NOTVOWEL:
        if not tr.is_letter(letter_w, 0):
            add_points = 20 - distance_left
            pre_ptr -= letter_xbytes
        else:
            failed = 1
    elif rb == K.RULE_DOUBLE:
        if letter_w == last_letter_w:
            add_points = 21 - distance_left
            pre_ptr -= letter_xbytes
        else:
            failed = 1
    elif rb == K.RULE_DIGIT:
        if is_digit(letter_w):
            add_points = 21 - distance_left
            pre_ptr -= letter_xbytes
        else:
            failed = 1
    elif rb == K.RULE_NONALPHA:
        if not is_alpha(letter_w):
            add_points = 21 - distance_right
            pre_ptr -= letter_xbytes
        else:
            failed = 1
    elif rb == K.RULE_DOLLAR:
        pre_ptr += 1
        command = prog[k]; k += 1
        if (command == K.DOLLAR_LIST) or ((command & 0xf0) == 0x20):
            # part-word lookup keys off the MATCH end (consumed+group_length), same as the
            # post-context branch (dictionary.c:1927 -> DollarRule).
            failed, add_points = _dollar_rule(tr, command, word_flags, dict_flags, buf, match_end_ptr)
    elif rb == K.RULE_SYLLABLE:
        syllable_count = 1
        while k < len(prog) and prog[k] == K.RULE_SYLLABLE:
            k += 1
            syllable_count += 1
        if syllable_count <= tr.word_vowel_count:
            add_points = 18 + syllable_count - distance_left
        else:
            failed = 1
    elif rb == K.RULE_STRESSED:
        pre_ptr += 1
        if tr.word_stressed_count > 0:
            add_points = 19
        else:
            failed = 1
    elif rb == K.RULE_IFVERB:
        pre_ptr += 1
        if tr.expect_verb:
            add_points = 1
        else:
            failed = 1
    elif rb == K.RULE_CAPITAL:
        pre_ptr += 1
        if word_flags & K.FLAG_FIRST_UPPER:
            add_points = 1
        else:
            failed = 1
    elif rb == K.RULE_SKIPCHARS:
        # 'xyJ)': skip word characters BACKWARDS until xy matches (dictionary.c:1995). The post-
        # context branch (J in '(Jxy') was already handled; the PRE branch was missing, so any
        # `...J)` left-context rule always failed and fell through to a lower-scoring rule. lv
        # `L41J) e` / `L41J) ē` (skip back over consonants to an L41 'international' letter ->
        # narrow [e]/[e:], not wide [E]/[E:]): flamenko -> flamˈeŋkoː (was …æŋ…), gofrēto ->
        # ɡˈofreːtuo (was …ræː…). The target prog[k] (a literal byte, or RULE_LETTERGP2 + group)
        # is NOT consumed here — the next pre-iteration re-reads prog[k] and matches the found xy.
        target = prog[k]
        is_lg = (target == K.RULE_LETTERGP2)
        tgroup = _letter_group_no(prog[k + 1]) if is_lg else None
        # p starts one byte forward (C: pre_ptr+1) so an empty jump leaves pre_ptr unchanged.
        p = pre_ptr + 1
        p2 = p
        g_bytes = -1

        def _b(idx):
            return buf[idx] if 0 <= idx < len(buf) else 0
        # C: while ((*p != *rule) && (*p != SPACE) && (*p != 0) && (g_bytes == -1))
        while (_b(p) != target and _b(p) != K.RULE_SPACE and _b(p) != 0
               and g_bytes == -1):
            p2 = p
            p -= 1
            if is_lg:
                g_bytes = _is_letter_group(tr, buf, p2, tgroup, 1)
        if _b(p) == target and not is_lg:
            pre_ptr = p2
        elif g_bytes >= 0:
            pre_ptr = p2 + 1
        else:
            failed = 1
    elif rb == K.RULE_NOVOWELS:
        # X) — no vowel between here and the start of the word (scanning backward)
        p = pre_ptr - letter_xbytes
        lw = letter_w
        ok = True
        while lw != K.RULE_SPACE and lw != 0:
            if tr.is_letter(lw, K.LETTERGP_VOWEL2):
                failed = 1
                ok = False
                break
            lw, nb = _utf8_back(buf, p - 1)
            p -= nb
        if ok and not failed:
            add_points = 3
    elif rb == ord("."):
        # dot in pre-section: match on any '.' before this point in the word
        # (dictionary.c:1977-1986). Scan backward to the word-start space; +50 if a dot found.
        p = pre_ptr
        while p >= 0 and buf[p] != ord(" "):
            if buf[p] == ord("."):
                add_points = 50
                break
            p -= 1
        if p < 0 or buf[p] == ord(" "):
            failed = 1
    elif rb == ord("-"):
        if letter == ord("-") or (letter == ord(" ") and (word_flags & K.FLAG_HYPHEN)):
            add_points = 22 - distance_right
        else:
            failed = 1
    else:
        if letter == rb:
            if letter == K.RULE_SPACE:
                add_points = 4
            elif (letter & 0xc0) != 0x80:
                add_points = 21 - distance_left
        else:
            failed = 1
    return failed, add_points, pre_ptr, k


def _dollar_rule(tr, command, word_flags, dict_flags, buf=None, part_end=None):
    # Port of the RULE_DOLLAR branch of MatchRule. $w_alt is gated on the word's dict
    # $alt flags. $p_alt / $list need a part-word *_list lookup (DollarRule) and are not
    # yet wired, so they fail (rare in core words).
    if command == K.DOLLAR_NOPREFIX:
        if word_flags & K.FLAG_PREFIX_REMOVED:
            return 1, 0
        return 0, 1
    if command == K.DOLLAR_UNPR:
        return 0, 0
    if (command & 0xf0) == 0x10:  # $w_alt: gate on the WHOLE word's dict $alt flag
        if dict_flags & (1 << (K.BITNUM_FLAG_ALT + (command & 0xf))):
            return 0, 23
        return 1, 0
    if (command & 0xf0) == 0x20 or command == K.DOLLAR_LIST:  # $p_alt / $list: espeak's DollarRule
        # Look up the word UP TO (and including) the match in *_list and check ITS $alt flag — NOT
        # the whole word's. For a suffix rule the part is the whole word (da bagage/-ant/-ab/-age,
        # so those still fire); for a mid-word match (da 'digital' at 'it', part 'digit') it fails,
        # which stops the spurious '' stress that the whole-word approximation produced.
        d = getattr(tr, "dict", None)
        if d is None or buf is None or part_end is None:
            if dict_flags & (1 << (K.BITNUM_FLAG_ALT + (command & 0xf))):
                return 0, 23
            return 1, 0
        part = bytes(buf[2:part_end]).decode("utf-8", "replace").strip()
        pflags = d.lookup_flags(part, tr.dict_condition) if part else 0
        if command == K.DOLLAR_LIST:
            if (pflags & K.FLAG_FOUND) and not (pflags & K.FLAG_ONLY):
                return 0, 23
            return 1, 0
        if pflags & (1 << (K.BITNUM_FLAG_ALT + (command & 0xf))):
            return 0, 23
        return 1, 0
    return 1, 0


def _apply_replacements(reps, word):
    """Apply the `.replace` table (port of SubstituteChar, translate.c:784) before rule
    matching: longest source-string first, matched case-insensitively (espeak lowercases
    the char to look it up), output lowercase. Used for Cyrillic->Latin transliteration in
    Serbo-Croatian (hr/bs/sr) and digraph normalisation elsewhere."""
    if not reps:
        return word
    rep_sorted = sorted(reps, key=lambda fr: -len(fr[0]))
    out = []
    i = 0
    n = len(word)
    while i < n:
        for frm, to in rep_sorted:
            seg = word[i:i + len(frm)]
            if seg and seg.lower() == frm.lower():
                out.append(to)
                i += len(frm)
                break
        else:
            out.append(word[i])
            i += 1
    return "".join(out)


_ACCENTED_VOWELS = set("àáâãäåæāăąèéêëēĕėęěìíîïĩīĭįòóôõöøœōŏőùúûüũūŭůűųýÿı")


def _is_vowel_letter(tr, ch):
    """A letter that can be a syllable nucleus in this language: the dict letter_bits vowel group,
    extra_vowels, syllabic consonants, accented Latin vowels, and 'y'."""
    c = ch.lower()
    lb = tr.config.get("letter_bits", {})
    vowels = lb.get(0, "aeiou") if isinstance(lb, dict) else "aeiou"
    extra = tr.config.get("extra_vowels", "") or ""
    # SetLetterVowel(tr,c) also makes c a syllable nucleus (groups A + VOWEL2); cy `w`/`y`
    # go through this path, so they must count as vowels here too (else `wrth`, `hwn`, `shwd`
    # look vowel-less and get spelled letter-by-letter instead of pronounced).
    setvow = tr.config.get("set_letter_vowel", "") or ""
    syll = tr.config.get("syllabic_consonants", "")  # cs/hr/sl/sk/sr: r,l are syllabic nuclei
    if 0xC0 <= ord(c) < 0xC0 + len(_REMOVE_ACCENT):
        # IsLetter (dictionary.c:788) tests an accented letter via remove_accent[]: the base
        # letter's groups decide, so cy ŵ/ŷ count as vowels because SetLetterVowel('w'/'y') does
        # (tŷ -> tˈɨː, dŵr -> dˈuːr, not spelled letter names).
        base = chr(_REMOVE_ACCENT[ord(c) - 0xC0]) if _REMOVE_ACCENT[ord(c) - 0xC0] else c
        if base != c and _is_vowel_letter(tr, base):
            return True
    return (c == "y" or c in vowels or c in extra or c in setvow
            or c in syll or c in _ACCENTED_VOWELS)


def _unpronounceable(tr, word, posn=0):
    """Port of Unpronouncable (translateword.c:1114): a word with no dict pronunciation whose first
    vowel is deeper than max_initial_consonants+1 letters in (counting from the start, NOT counting a
    leading LOPT_UNPRONOUNCABLE char — default 's') is "unpronouncable" and spoken letter by letter
    from the front until a pronounceable remainder is reached (nl mskraam -> ˈɛm + skraam). A word
    with no vowel at all (vowel_posn stays 9 > max+1) is the limiting case (en th, ca Mgfc).

    Latin-script, non-tonal languages only — others render native/tone-marked vowels not in the
    Latin vowel set. `posn` is the peel position (an apostrophe is only an end-marker after posn 0)."""
    cfg = tr.config
    if not word or len(word) < 2:
        return False
    if cfg.get("letter_bits_offset", 0) or cfg.get("tone_language"):
        return False
    lopt = cfg.get("lopt_unpronouncable", ord("s"))
    if lopt == 1:  # LOPT_UNPRONOUNCABLE==1: check disabled (many langs)
        return False
    if word[0] in (" ", "'"):
        return False
    count = 0
    c1 = None
    vowel_posn = 9
    for ch in word:
        if ch == " ":
            break
        if ch == "'" and (count > 1 or posn > 0):
            break  # "tv'" but not "l'"
        if count == 0:
            c1 = ch
        if not (ch == "'" and lopt == 3):  # LOPT_UNPRONOUNCABLE==3: don't count apostrophe
            count += 1
        if _is_vowel_letter(tr, ch):
            vowel_posn = count
            break
        if ch != "'" and not ch.isalpha():
            return False
        if ord(ch) >= 0x250:
            # a non-Latin letter (Cyrillic/Greek/Indic/...) whose native vowels aren't in the Latin
            # vowel set — not a Latin acronym. Guards languages that don't set letter_bits_offset
            # (ky/mk/nog/ba are Cyrillic but leave it unset, so the offset check alone misses them).
            return False
    if lopt == 2 and vowel_posn > 2:
        # LOPT_UNPRONOUNCABLE==2 (de/en/es): the deep-vowel decision is delegated to Unpronouncable2
        # (translateword.c:1173), a *_rules test — checked BEFORE the leading-`s` adjustment and the
        # max_initial_consonants heuristic (which are the else-path for langs with a shallow vowel).
        return unpronounceable2(tr, word)
    if c1 is not None and ord(c1) == lopt:
        vowel_posn -= 1  # disregard a leading LOPT_UNPRONOUNCABLE char (default 's') when counting
    return vowel_posn > (cfg.get("max_initial_consonants", 3) + 1)


def unpronounceable2(tr, word):
    """Port of Unpronouncable2 (translateword.c:1187). For LOPT_UNPRONOUNCABLE==2 languages
    (en/de/es), reruns the letter-to-sound rules over `word` under FLAG_UNPRON_TEST instead of the
    generic vowel-depth heuristic. Under that flag MatchRule only lets start-anchored rules
    (RULE_PRE_ATSTART) win, and translate_rules returns the first such match's end_type | 1 as the
    end_flags. The word is UNpronounceable (-> spell letter by letter) iff no start-anchored rule
    matched (end_flags == 0) or the one that matched is an explicit `$unpron` marker (SUFX_UNPRON):
    en `st` matches `_) st (` -> pronounceable (sˈənt); de `nvda` matches nothing -> spelled."""
    mnem = getattr(tr, "mnem", None)
    if mnem is None:
        return False  # no phoneme index available: fall back to pronounceable (unchanged behaviour)
    _ph, end_flags, _ep = translate_rules(tr, word, mnem, word_flags=K.FLAG_UNPRON_TEST,
                                          pre_substituted=True)
    return (end_flags == 0) or bool(end_flags & K.SUFX_UNPRON)


def translate_rules(tr, word, mnem_index, word_flags=0, want_endings=False, dict_flags=0,
                    left_ctx="", right_ctx="", pre_substituted=False):
    """Port of TranslateRules (dictionary.c:2080) for a single space-free word.

    Returns (phonemes, end_type, end_phonemes). When `want_endings` and a standard
    suffix/prefix ending rule wins, translation stops, `end_phonemes` holds the affix
    pronunciation, and `end_type` encodes the affix (the caller removes it and
    retranslates the stem). Otherwise end_type=0.
    (Accent removal, spell-word fallback, and language-switch are not yet wired.)

    ``left_ctx``/``right_ctx`` supply neighbouring-word text so a rule's pre/post
    context (RULE_SPACE ``_`` / RULE_DIGIT ``D``) can match ACROSS a word boundary the
    way espeak's MatchRule reads the shared clause buffer. Only the core ``word`` is
    translated; the context bytes sit in the buffer purely for pre/post matching (each
    separated from the word by a space, framed by the \\x00 sentinels). This is what
    lets the digit-context punctuation rules fire — ``D_) : (_DD_`` (omit colon in a
    time), ``D_) - (_D`` (dash), ``__) - (_D`` (minus) — for an isolated ``:`` or ``-``.
    """
    rules = tr.rules
    # SubstituteChar (translate.c:784) runs ONCE, at clause tokenisation (TranslateChar,
    # translate.c:1174), so the dict lookup and the rule matcher both see the same already-
    # substituted source. espyak's translate_word substitutes before its dict lookup and passes
    # the result here, so re-substituting would apply the table twice. That is invisible for an
    # idempotent table (ä->æ) but corrupts a non-idempotent one: Sindarin maps `x`->`cs` and
    # `ch`->`x`, so a second pass cascades ch->x->cs (ach -> ˈaks instead of ˈaχ). Callers that
    # have already substituted pass pre_substituted=True.
    if not pre_substituted:
        word = _apply_replacements(getattr(rules, "replacements", None), word)
    wb = word.encode("utf-8")
    lb = (left_ctx.encode("utf-8") + b" ") if left_ctx else b""
    rb = (b" " + right_ctx.encode("utf-8")) if right_ctx else b""
    buf = bytearray(b"\x00 " + lb + wb + rb + b" \x00")
    p = 2 + len(lb)             # index of first letter of the word (past any left context)
    end = 2 + len(lb) + len(wb)  # index of the space right after the word
    phonemes = ""
    tr.word_vowel_count = 0
    tr.word_stressed_count = 0
    any_alpha = 0

    prev_letter = None       # (source char, phonemes-length before it) — for the spell re-lookup
    while p < len(buf) and buf[p] not in (0, ord(" ")):
        wc, wc_bytes = _utf8_in(buf, p)
        if is_alpha(wc):
            any_alpha += 1
        c = buf[p]
        _phon_len_before = len(phonemes)

        if is_digit(wc):
            # tonal languages map a tone digit to a tone phoneme via the rules (cmn 3 -> 214 in the
            # default `.group`). Try the rules first; only fall back to the digit-name number lookup
            # if nothing matches (so en `mp3` still says "three").
            tm, tp = match_rule(tr, buf, p, 0, rules.default, word_flags, dict_flags)
            if tm.points > 0:
                if tm.phonemes:
                    phonemes = _append(tr, phonemes, tm.phonemes, mnem_index)
                p = tp
                continue
            num_ph = tr.lookup_num_digit(chr(wc)) if hasattr(tr, "lookup_num_digit") else ""
            phonemes = _append(tr, phonemes, num_ph, mnem_index)
            p += wc_bytes
            continue

        found = False
        match1 = None
        p_start = p  # char start; match_rule below reassigns p past the (failed) match

        # single >=3-byte char (Korean jamo, etc.): dispatch by codepoint via groups3
        if wc_bytes >= 3 and wc in rules.groups3:
            match1, p = match_rule(tr, buf, p, wc_bytes, rules.groups3[wc],
                                   word_flags, dict_flags)
            found = True

        # 2-letter group (keyed by the two bytes at this position, as espeak's c12)
        two = bytes(buf[p:p + 2])
        if not found and two in rules.groups2:
            g2 = rules.groups2[two]
            m2, p2 = match_rule(tr, buf, p, 2, g2, word_flags, dict_flags)
            if m2.points > 0:
                m2.points += 35
            g1 = rules.groups1.get(c)
            if g1 is not None:
                m1, p1 = match_rule(tr, buf, p, 1, g1, word_flags, dict_flags)
            else:
                m1, p1 = MatchRecord(), p
            if m2.points >= m1.points:
                match1, p = m2, p2
            else:
                match1, p = m1, p1
            found = True

        if not found:
            g1 = rules.groups1.get(c)
            if g1 is not None:
                match1, p = match_rule(tr, buf, p, 1, g1, word_flags, dict_flags)
            else:
                match1, p = match_rule(tr, buf, p, 0, rules.default, word_flags, dict_flags)
                if match1.points == 0:
                    # no rule: espeak strips the accent and re-translates the word
                    # (dictionary.c:2228). Only when the char isn't the whole word (a lone
                    # accented letter is spelled out instead). Fire for ASCII-letter bases.
                    base = (_REMOVE_ACCENT[wc - 0xC0]
                            if 0xC0 <= wc < 0xC0 + len(_REMOVE_ACCENT) else 0)
                    if (0x61 <= base <= 0x7A and len(wb) > wc_bytes
                            and getattr(tr, "config", {}).get("lopt_dieres")
                            and wc in _DIERESES_LIST):
                        # vowel with dieresis (dictionary.c:2238): replace it with its base letter
                        # IN PLACE and continue from this point, KEEPING the phonemes produced so
                        # far. The dieresis breaks a digraph, so the two vowels stay separate
                        # syllables (nl diënt -> i + ent -> di'Ent, not the ie-digraph d'int).
                        buf[p_start:p_start + wc_bytes] = bytes([base])
                        end -= (wc_bytes - 1)
                        p = p_start
                        continue
                    if 0x61 <= base <= 0x7A and len(wb) > wc_bytes:
                        # slice from the CHAR START (p_start), not the advanced p: the failed
                        # default match leaves p mid-character, which split the multi-byte
                        # accented char and corrupted the re-translated word (sjn fëanor).
                        new_word = (buf[2:p_start] + bytes([base])
                                    + buf[p_start + wc_bytes:end]).decode("utf-8", "replace")
                        return translate_rules(tr, new_word, mnem_index, word_flags,
                                               want_endings, dict_flags, pre_substituted=True)
                    # unrecognised ASCII letter in a multi-letter word: espeak sets
                    # FLAG_SPELLWORD and re-translates as individual letters (dictionary.c:2274).
                    # mto foreign names (no rule for 'd' in amsterdam). Scoped to ASCII so non-ASCII
                    # special letters (es ª ordinal) take their own path instead — EXCEPT a non-Latin
                    # script that opts in (spell_word_foreign_letter): an in-block letter its rules
                    # cannot pronounce (as র U+09B0, no `র` rule) triggers the same whole-word spell
                    # (আমার -> ˈa mˈɔ ˈakaɾ (bn)ɾˈɔ(as)), each letter by NAME and the unnamed letter
                    # switched to its alphabet's language (dictionary.c:2270, IsAlpha not ASCII-gated).
                    cfg = getattr(tr, "config", None) or {}
                    if any_alpha > 1 and is_alpha(wc) and (
                            wc < 0x80 or cfg.get("spell_word_foreign_letter")):
                        tr._spell_word = True
                        return phonemes, 0, ""
                    # unrecognised character: skip it
                    p += (wc_bytes - 1)

        # A character with NO rule match (in any group) that is non-alphabetic and non-combining
        # is spelled IN PLACE by its Unicode codepoint name (espeak's LookupLetter,
        # dictionary.c:2277): a Myanmar medial ွ U+103D / ှ U+103E or the visarga း U+1038 whose
        # .group rule only fires before an L02 letter and so produces nothing here. Emit a sentinel
        # carrying the codepoint; _render_phonemes replaces it with the in-band (en)…(shn)…
        # spelling. Gated per-language (compat_spell_codepoint) and to the script's Unicode block.
        if (word_flags & K.FLAG_UNPRON_TEST) and match1 is not None and match1.points == 0 \
                and is_alpha(wc):
            # Unpronouncable2 abort (dictionary.c:2270): under the test flag, an alphabetic letter
            # group that matched no start-anchored rule aborts the whole word (espeak's condition
            # `(any_alpha > 1) || (p[wc_bytes-1] > ' ')` is always true for a letter). points stays
            # 0 all the way out, so TranslateRules returns end_flags 0 and the word is judged
            # unpronounceable — en `ph`/`bh`/`sh` peel their first consonant instead of pronouncing
            # the silent-h cluster (`_B) h`), rather than pronouncing through it.
            return "", 0, ""

        if match1 is not None and match1.points == 0:
            cfg = getattr(tr, "config", None) or {}
            blk = cfg.get("compat_spell_codepoint")
            # espeak spells such a character only when it is NOT word-final after a pronounced
            # consonant: a medial/visarga that ends the word is silently dropped (ၵွ -> k), but
            # one with more letters after it is spelled in place (ၵွၵ -> k <103D> k). A character
            # that is the WHOLE word (no prior phonemes) is always spelled (ေ -> <1031>).
            more_follows = bytes(buf[p_start + wc_bytes:end]).strip(b" ") != b""
            if (blk and not is_alpha(wc) and not (0x300 <= wc <= 0x36f)
                    and blk[0] <= wc <= blk[1]
                    and wc not in _SPELL_CODEPOINT_SKIP
                    and (more_follows or not phonemes)):
                from espyak.api import _spell_cp_sentinel
                # espeak re-translates the consonant immediately before a spelled letter via its
                # DICTIONARY entry, not the rules (the SpeakIndividualLetters path): shn ၸ is the
                # rule `tS;` (tɕ) but the dict entry `tS` (tʃ), and the dict wins beside a spell
                # (ၸွၵ -> tʃ <103D> k, not tɕ …). Replace the previous letter's rule output with
                # its dict entry when they differ.
                if prev_letter is not None:
                    prev_ch, prev_len = prev_letter
                    dph, _dfl = tr.dict.lookup(prev_ch, LookupContext()) if tr.dict else (None, None)
                    if dph and phonemes[prev_len:] and dph != phonemes[prev_len:]:
                        phonemes = phonemes[:prev_len] + dph
                phonemes = phonemes + _spell_cp_sentinel(wc)
                prev_letter = None

        if match1 is None or match1.phonemes is None:
            continue
        if match1.points > 0:
            if word_flags & K.FLAG_UNPRON_TEST:
                # Unpronouncable2 test (dictionary.c:2293): the FIRST group that matches a
                # start-anchored rule (RULE_PRE_ATSTART; only those update `best` under
                # FLAG_UNPRON_TEST) settles the question — return its end_type | 1 as the
                # end_flags. A $unpron ($unpron -> SUFX_UNPRON) marker means "still
                # unpronounceable"; any other match means pronounceable. Never appends, so no
                # phonemes are produced here.
                return "", (match1.end_type | 1), ""
            if (match1.phonemes and match1.phonemes.startswith("_^_")
                    and not (word_flags & K.FLAG_DONT_SWITCH_TRANSLATOR)):
                # phonSWITCH (dictionary.c:2297): a rule producing a language switch as its
                # FIRST phoneme returns IMMEDIATELY with only the switch marker — espeak
                # re-translates the whole word in the named language and discards any phonemes
                # accumulated before the switch. cmn `xiong2` ($text pinyin for 雄): the first
                # Latin letter trips `_^_EN`, so the whole token switches to English, not the
                # per-letter `_^_EN_^_EN…yN35` glue espyak used to accumulate.
                return match1.phonemes, 0, ""
            end_type = match1.end_type & ~K.SUFX_UNPRON
            if want_endings and end_type != 0:
                # a standard ending matched: stop, return the affix phonemes + type
                if (end_type & K.SUFX_P) and (word_flags & K.FLAG_NO_PREFIX):
                    pass  # ignore the prefix match
                else:
                    if (end_type & K.SUFX_P) and ((end_type & 0x7f) == 0):
                        end_type |= (p - 2)  # prefix length = chars consumed so far
                    return phonemes, end_type, match1.phonemes
            if match1.del_fwd is not None and 0 <= match1.del_fwd < len(buf):
                # rewrite the marked forward 'e' to REPLACED_E so a later group skips it
                # (dictionary.c:2322-2323; English silent-e).
                buf[match1.del_fwd] = REPLACED_E
            # remember this single source letter and where its phonemes start, so a following
            # spelled codepoint can re-translate it via the dict (see the spell block above).
            if match1.phonemes:
                try:
                    src_char = bytes(buf[p_start:p_start + wc_bytes]).decode("utf-8")
                    prev_letter = (src_char, _phon_len_before)
                except (UnicodeDecodeError, ValueError):
                    prev_letter = None
            phonemes = _append(tr, phonemes, match1.phonemes, mnem_index)

    return phonemes, 0, ""


def _append(tr, phonemes, ph, mnem_index):
    if not ph:
        return phonemes
    count_vowels(tr, ph, mnem_index)
    # espeak's AppendPhonemes strcats already-ENCODED phoneme byte arrays (one byte per
    # phoneme), so each rule output's phoneme boundaries are baked in: a word-final letter pair
    # `t`+`s` stays two phonemes and can never re-merge into the `ts` affricate. espyak carries
    # mnemonic *text* and re-encodes it greedily at render, so `ts`(from c)+..+`t`+`s` -> "tsyts"
    # and the trailing `t`+`s` wrongly merge to the `ts` affricate (lv cyts -> t͡sˈyt͡s, pats ->
    # pˈat͡s). Guard that one case: if (and only if) the join would form a multi-char mnemonic
    # spanning the boundary, drop a `|` no-tie barrier there to preserve the real boundary. The
    # barrier is non-rendering and fires only at a genuine cross-output ambiguity, so a clean
    # join (every ca/smj/.. word) and a real multi-phoneme single output (`o:ts` for Mocarts)
    # are untouched.
    if (phonemes and not phonemes.endswith("|") and not ph.startswith("|")
            and _join_is_spurious(phonemes, ph, mnem_index)):
        return phonemes + "|" + ph
    return phonemes + ph


def _join_is_spurious(a, b, mnem_index):
    """True if some suffix of `a` + prefix of `b` (spanning the join, len>=2) is a phoneme
    mnemonic — i.e. the greedy re-encoder would merge across the boundary. Only such joins
    need a barrier; a clean concatenation never re-merges and is left exactly as espeak's
    strcat produces it."""
    table = mnem_index.table
    maxlen = mnem_index.maxlen
    if maxlen < 2:
        return False
    na, nb = len(a), len(b)
    for la in range(1, min(maxlen - 1, na) + 1):
        for lb in range(1, min(maxlen - la, nb) + 1):
            if a[na - la:] + b[:lb] in table:
                return True
    return False


_ADD_E_EXCEPTIONS = ("ion",)
_ADD_E_ADDITIONS = ("c", "rs", "ir", "ur", "ath", "ns", "u", "spong", "rang", "larg")


def remove_ending(tr, word, end_type):
    """Port of RemoveEnding (dictionary.c:2901). Returns (stem, end_flags).

    Removes a standard suffix indicated by the dictionary rules and (for English)
    reverses the y->i and e-dropping that adding the suffix performed.
    """
    chars = list(word.replace(chr(REPLACED_E), "e"))
    n_remove = end_type & 0x3f
    stem = chars[: len(chars) - n_remove] if n_remove else chars[:]
    ending = "".join(chars[len(chars) - n_remove:]) if n_remove else ""
    end_flags = (end_type & 0xfff0) | K.FLAG_SUFX

    if (end_type & K.SUFX_I) and stem and stem[-1] == "i":
        stem[-1] = "y"

    if end_type & K.SUFX_E:
        if tr.translator_name == K.L("e", "n"):
            last = ord(stem[-1]) if stem else 0
            prev = ord(stem[-2]) if len(stem) >= 2 else 0
            added = False
            if tr.is_letter(prev, K.LETTERGP_VOWEL2) and tr.is_letter(last, 1):
                tail = "".join(stem[-3:])
                if not any(tail.endswith(ex) for ex in _ADD_E_EXCEPTIONS):
                    added = True
            else:
                tail = "".join(stem)
                if any(tail.endswith(a) for a in _ADD_E_ADDITIONS):
                    added = True
            if added:
                stem.append("e")
                end_flags |= K.FLAG_SUFX_E_ADDED
        elif tr.config.get("suffix_add_e"):
            # other langs (nl/de/af): espeak unconditionally re-adds suffix_add_e to the stem so
            # the re-translated stem keeps its open-syllable vowel length (nl deze: stem dez+e ->
            # de:z, not closed-short dEz). The S?e suffix rules mean "double the vowel".
            stem.append(tr.config["suffix_add_e"])
            end_flags |= K.FLAG_SUFX_E_ADDED

    if (end_type & K.SUFX_V) and tr.expect_verb == 0:
        tr.expect_verb = 1

    if ending in ("s", "es"):
        end_flags |= K.FLAG_SUFX_S

    return "".join(stem), end_flags


def _is_letter_group(tr, buf, ix, group, pre):
    items = tr.rules.letter_groups.get(group) if getattr(tr, "rules", None) else None
    if not items:
        return -1
    # espeak stores .Lnn group members longest-first and takes the longest match (compiledict.c):
    # .L01 has both 'u' and the diphthong 'ui', so 'ui' must win (sjn Arvedui: e (CL01X matches
    # the 'ui' so X reaches the word end -> the =E retraction fires). Return the LONGEST match.
    best = -1
    has_null = False
    for item in items:
        if item == "~":
            has_null = True
            continue
        ib = item.encode("utf-8")
        length = len(ib)
        if pre:
            # match backwards: the bytes ending at ix
            start = ix - length + 1
            if start >= 0 and bytes(buf[start:ix + 1]) == ib and length > best:
                best = length
        elif bytes(buf[ix:ix + length]) == ib and length > best:
            best = length
    if best >= 0:
        return best
    return 0 if has_null else -1
