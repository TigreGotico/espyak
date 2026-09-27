"""Phoneme-list -> output string rendering.

Faithful port of espeak-ng's output path:
  - WritePhMnemonic          (dictionary.c:441)
  - GetTranslatedPhonemeString (dictionary.c:560)

Plus a phoneme-string *encoder* (the inverse: parse a mnemonic string such as the
content of ``[[...]]`` or a rule's phoneme output into a phoneme list), which lets the
output path be exercised end-to-end against the oracle independently of the matcher.

NOTE: the IPA/Kirshenbaum text output reflects the *translation-time* phoneme list
AFTER the phoneme *programs* run (context-dependent ChangePhoneme). Example: the en
phoneme ``r`` carries ``ipa ɹ`` but its program rewrites it to ``r/`` (no ipa -> ``r``)
when not followed by a vowel, so ``car`` renders ``…r`` not ``…ɹ``. This renderer is
faithful to whatever phoneme list it is given; producing that final list is the job of
the phoneme-program pass (see espyak/phoneme_program.py / task P1b). The bare encoder
here does NOT run programs, so program-dependent inputs differ until that pass lands.

Reference: espeak-ng 1.52.0.
"""
from espyak.phoneme_tab import phVOWEL, phSTRESS, phPAUSE, phVIRTUAL

# stress levels (synthesize.h)
STRESS_IS_SECONDARY = 3
STRESS_IS_PRIMARY = 4
STRESS_IS_PRIORITY = 5

# synthflags
SFLAG_SYLLABLE = 0x04
SFLAG_LENGTHEN = 0x08

# newword flags (synthesize.h PHLIST_*)
PHLIST_START_OF_WORD = 1
PHLIST_START_OF_CLAUSE = 2
PHLIST_START_OF_SENTENCE = 4

# Kirshenbaum (ascii 0x20..0x7f) -> IPA codepoint. The mapping (dictionary.c
# ipa1[96]) is maintained in scriptconv; rebuild the indexable list from it so
# there is a single source of truth for the Kirshenbaum ↔ IPA table.
from scriptconv.notation import kirshenbaum_to_ipa as _kirshenbaum_to_ipa

_IPA1 = [ord(_kirshenbaum_to_ipa(chr(0x20 + _i))) for _i in range(96)]

# stress characters for Kirshenbaum output, indexed by stress level. ("==,,''")
_STRESS_CHARS = "==,,''"


def _is_digit09(c):
    return ord('0') <= c <= ord('9')


class PhonemeListEntry:
    __slots__ = ("ph", "stresslevel", "synthflags", "newword", "ipa_override", "deleted",
                 "dict_no_reduce")

    def __init__(self, ph):
        self.ph = ph
        self.stresslevel = 0
        self.synthflags = 0
        self.newword = 0
        self.ipa_override = None  # set by the phoneme-program interpreter (conditional ipa)
        self.deleted = False      # ChangePhoneme(NULL) deletes the phoneme
        self.dict_no_reduce = False  # phonemes from a dict entry: skip stress-condition reductions

    @property
    def type(self):
        return self.ph.type


def encode_phoneme_string(s, table):
    """Parse a phoneme mnemonic string into a list of PhonemeListEntry.

    Greedy longest-match against the table's mnemonics. Stress markers (phSTRESS
    phonemes such as ``'`` ``,`` ``%``) are consumed and attached to the following
    syllabic phoneme's stress level, mirroring how espeak merges stress into the
    syllable.
    """
    # build a longest-first list of known mnemonics for greedy matching
    mnems = sorted(table.phonemes.keys(), key=len, reverse=True)
    maxlen = len(mnems[0]) if mnems else 1
    # ta redefines '#' as a NULL phoneme for the virama (suppresses the inherent vowel), so a
    # consonant + '#' must parse as two phonemes (l, #) not the subscript-h combine 'l#' (= ɬ) that
    # other tables carry — otherwise the virama's ChangePhoneme(NULL) never runs (பில் -> piɬ not pil).
    _virama_hash = "#" in table.phonemes and "ChangePhoneme(NULL)" in str(
        getattr(table.phonemes.get("#"), "program", ""))

    entries = []
    pending_stress = None
    i = 0
    n = len(s)
    first_word_done = False
    pending_newword = False
    while i < n:
        c = s[i]
        if c in (" ", "\t"):
            # Within a word's phoneme string, a single space is just a phoneme
            # separator (no output). True word boundaries are "||" (handled below)
            # or come from multi-word translation (P5).
            i += 1
            continue
        if c == "|":
            if s[i:i + 2] == "||":
                # "||" is a word break in the phoneme string. But the bare phonPAUSE `_`
                # immediately before the break swallows the word-boundary space: espeak's
                # [[hai_||Ent]] renders `haiˈɛnt` while [[hai||Ent]] renders `hai ˈɛnt`
                # (compound joins spelled `_||` in a dict entry — de highend hˌaiˈɛnt, it
                # bestseller bˈɛst̪sˈeller — vs a plain `||` join, nordrhein nˈɔɾt raɪn). Only
                # the bare `_` suppresses: a longer pause such as `_:` (phonPAUSE_SHORT) keeps
                # the space (ru `три и один`: [[…_:||…]] -> `… …`, still spaced).
                if not (entries and entries[-1].ph.mnemonic == "_"):
                    pending_newword = True
                i += 2
            else:
                i += 1  # single "|" is a morpheme/tie barrier — not a phoneme
            continue
        # find the longest matching mnemonic starting at i
        # `||` is a hard word break (espeak stores it as a separate phonEND_WORD byte), so a
        # phoneme mnemonic must never straddle it. Cap the match window at the next `||` so a
        # pause phoneme spelled with a trailing barrier (`_|`) can't swallow the first `|` of a
        # `||` — that left a lone `|` (morpheme barrier) and dropped the word break, collapsing
        # the space espeak keeps after a pl/cs decimal-separator word (przecinek/čárka).
        wb = s.find("||", i)
        win = (wb - i) if wb > i else (n - i)
        m = None
        for L in range(min(maxlen, win), 0, -1):
            cand = s[i : i + L]
            if _virama_hash and len(cand) > 1 and cand.endswith("#"):
                # The virama '#' is a NULL phoneme: split it off ONLY when it ends a
                # syllable — i.e. after a consonant and before a consonant or word end
                # (bil# -> bil, ba:l#ja -> ba:lja). Keep the merge for the inherent schwa
                # V# (ba:kkV#i, a vowel base, elided before the next vowel) and for a real
                # subscript-h before a vowel (t# -> tʰ in t#i:).
                base = cand[:-1]
                base_vowel = base in table.phonemes and table.phonemes[base].type == phVOWEL
                j = i + L  # next phoneme, skipping any intervening stress markers ('t#\'i:')
                while j < n and table.phonemes.get(s[j]) is not None and table.phonemes[s[j]].type == phSTRESS:
                    j += 1
                nxt = table.phonemes.get(s[j]) if j < n else None
                nxt_vowel = nxt is not None and nxt.type == phVOWEL
                if not base_vowel and not nxt_vowel:
                    continue  # keep the NULL virama '#' separate from its consonant
            if cand in table.phonemes:
                m = cand
                break
        if m is None:
            # A literal digit with no phoneme (fa 'ARoq1' for ق/غ) renders as itself — espeak keeps
            # it in -x/--ipa (ɑroq1). Synthesize an inert phINVALID entry whose ipa is the digit;
            # non-tonal tables have no real digit phonemes so _reorder_tones leaves it in place.
            if c.isdigit():
                from espyak.phoneme_tab import Phoneme
                lit = Phoneme(c)
                lit.ipa = c
                entries.append(PhonemeListEntry(lit))
            # other unknown chars are skipped (espeak marks 255/unrecognised)
            i += 1
            continue
        ph = table.phonemes[m]
        i += len(m)
        if m == ":" and entries and entries[-1].ph.type == phPAUSE:
            # phonLENGTHEN (`:`) applies SFLAG_LENGTHEN to the PRECEDING list phoneme
            # (translate.c:590). A `_` pause is that phoneme when a length mark trails a `_||`
            # compound join (de highend hai_||::Ent), and a lengthened pause renders nothing —
            # espeak's [[hai_||::Ent]] and [[hai_::Ent]] both yield `haiˈɛnt`. Drop it so the
            # `::` doesn't surface as a stray ː (-> hˌaiˈɛnt, not hˌaiːˈɛnt).
            continue
        if m == "-" and pending_newword:
            # phonSYLLABIC immediately after a || word break (translate.c:585): it marks the
            # phoneme that PRECEDED the break syllabic and resets that phoneme's stress to the
            # pending next_stress (1, unstressed, since the previous vowel already consumed its
            # mark) — a flag, NOT an output phoneme, so it is consumed and never emitted. it_list
            # ``й = 'I||-b@-*'eve`` -> ɪ ... (the leading ``'I`` de-stresses to ɪ and no literal
            # hyphen renders). The pending newword carries on to the next real phoneme. A `-`
            # NOT after a || (zigano ``ts-ig'a/no``) is a normal syllabic-consonant marker and is
            # kept (rendered ts-iɡˈano), so this branch is gated on pending_newword.
            if entries:
                entries[-1].synthflags |= SFLAG_SYLLABLE
                entries[-1].stresslevel = pending_stress if pending_stress is not None else 1
            pending_stress = None
            continue
        if (ph.type == phVIRTUAL and ph.ipa is None and m == "-"
                and entries and entries[-1].ph.type != phVOWEL
                and pending_stress is not None and pending_stress >= STRESS_IS_SECONDARY):
            # A STRESSED syllabic consonant (a stress mark '/, immediately before a
            # consonant that the `-` then marks syllabic, e.g. ar `ع = [A-a:jn]` fed through
            # SetWordStress as `'A-a:jn`). espeak's phonemelist.c reinterprets a stressed
            # syllabic consonant as TWO segments carrying the tonic: the consonant geminates
            # and the first copy takes the primary/secondary mark (ˈʕʕ). The pending stress is
            # NOT consumed here — it also carries on to the following vowel, so the vowel keeps
            # its own tonic (ar ع -> `ˈʕʕˈaːjn`, both syllables stressed). An UNSTRESSED
            # syllabic consonant (no pending stress, e.g. ar `s̪-ˈuːrah`, `s̪-ifr`) falls
            # through to the literal-`-` branch below and is left byte-exact.
            prev = entries[-1]
            prev.synthflags |= SFLAG_SYLLABLE
            prev.stresslevel = pending_stress
            geminate = PhonemeListEntry(prev.ph)
            entries.append(geminate)
            continue
        if (ph.type == phVIRTUAL and ph.ipa is None and m == "-"
                and (not entries or entries[-1].ph.type == phVOWEL)):
            # the `-` syllabic-consonant marker (phsource/phonemes:135) makes the PREVIOUS
            # phoneme syllabic. GetTranslatedPhonemeString (dictionary.c:657) only writes it as a
            # flag appended to a PRECEDING non-vowel phoneme; it is never a standalone token. After
            # a vowel that is meaningless, so MakePhonemeList drops it and it produces no IPA (fo
            # number connective `u-o` -> uo). With NO preceding phoneme (a leading `-`, e.g. the
            # malformed da_list `final -ese` entry) there is nothing to mark, so espeak emits
            # nothing (final -> esˈe, not -esˈe). After a consonant the marker is kept (ar
            # `s̪-ˈifr`), as is the length mark `:` -> ː (a virtual with ipa).
            if entries:
                entries[-1].synthflags |= SFLAG_SYLLABLE
            continue
        if ph.type == phSTRESS and not m.isdigit():
            # punctuation stress markers ('/,/%/=) attach to the next vowel; digit-named
            # stress phonemes are tone marks (Vietnamese 1-7) that render in place.
            pending_stress = ph.stress_type
            continue
        entry = PhonemeListEntry(ph)
        if not entries:
            entry.newword = PHLIST_START_OF_WORD | PHLIST_START_OF_SENTENCE
        elif pending_newword or first_word_done:
            entry.newword = PHLIST_START_OF_WORD
            pending_newword = False
            first_word_done = False
        if ph.type == phVOWEL:
            entry.synthflags |= SFLAG_SYLLABLE
            # Unmarked vowels default to UNSTRESSED (1), not diminished (0): espeak
            # emits an explicit "%%" marker for diminished syllables. This distinction
            # is invisible to rendering but matters for ChangeIfDiminished programs.
            entry.stresslevel = pending_stress if pending_stress is not None else 1
            pending_stress = None
        entries.append(entry)
    return entries


def write_ph_mnemonic(ph, use_ipa, plist_entry=None):
    """Port of WritePhMnemonic (dictionary.c:441). Returns the rendered phoneme name."""
    # IPA: prefer the interpreter's conditional ipa override, else the static attribute
    if use_ipa:
        p = None
        if plist_entry is not None and plist_entry.ipa_override is not None:
            p = plist_entry.ipa_override
        elif ph.ipa is not None:
            p = ph.ipa
        if p is not None:
            if p == "":
                return ""
            if ord(p[0]) == 0x20:
                return ""  # space => no name
            if ord(p[0]) < 0x20:
                p = p[1:]  # leading flags byte
            # '|' is a no-tie barrier, dropped from plain output
            return p.replace("|", "")

    out = []
    first = True
    for ch in ph.mnemonic:
        c = ord(ch)
        if ch == "/":
            break  # discard phoneme variant indicator
        if use_ipa:
            if first and ch == "_":
                break  # don't show pause phonemes
            if ch == "#" and ph.type == phVOWEL:
                break  # '#' is subscript-h, only for consonants
            if not first and _is_digit09(c):
                first = False
                continue  # ignore digits after the first character
            if 0x20 <= c < 128:
                c = _IPA1[c - 0x20]
            out.append(chr(c))
        else:
            out.append(ch)
        first = False
    return "".join(out)


def _reorder_tones(plist):
    """Tone phonemes (digit-named phSTRESS, the cmn/yue Chao contours) attach to the syllable
    nucleus: espeak emits the tone right after the vowel, before the coda, but the rules append it
    at the syllable end. Move each tone to just after its preceding vowel (cmn fan3 -> fˈa2n, not
    fˈan2). Only tonal languages have digit-named phonemes, so this is a no-op elsewhere."""
    out = list(plist)
    i = 0
    while i < len(out):
        ph = out[i].ph
        if ph.type == phSTRESS and ph.mnemonic.isdigit():
            j = i - 1
            while j >= 0 and out[j].ph.type != phVOWEL:
                j -= 1
            if 0 <= j < i - 1:
                out.insert(j + 1, out.pop(i))
                continue
        i += 1
    return out


def render_phoneme_list(plist, table, ipa=True, tie=None, separator=None):
    """Port of GetTranslatedPhonemeString (dictionary.c:560).

    ``tie`` (a character) ties multi-character phoneme names; ``separator`` (a
    character) separates phonemes. They are mutually exclusive, matching the
    espeakPHONEMES_TIE / separator semantics.
    """
    plist = _reorder_tones(plist)
    use_ipa = ipa
    use_tie = tie if tie else None
    separate = separator if (separator and not tie) else None

    pieces = []
    for ix, entry in enumerate(plist):
        if entry.deleted:
            continue
        ph = entry.ph
        buf = []

        body = write_ph_mnemonic(ph, use_ipa, entry)

        if (entry.newword & PHLIST_START_OF_WORD) and not (
            entry.newword & (PHLIST_START_OF_SENTENCE | PHLIST_START_OF_CLAUSE)
        ):
            buf.append(" ")

        if (not entry.newword) or (separate == " "):
            if separate is not None and ix > 0 and body:
                c0 = ord(body[0])
                if c0 < 0x2b0 or c0 > 0x36f:  # not if starts with a superscript/diacritic
                    buf.append(separate)

        if entry.synthflags & SFLAG_SYLLABLE:
            stress = entry.stresslevel
            if stress > 1:
                if stress > STRESS_IS_PRIORITY:
                    stress = STRESS_IS_PRIORITY
                if use_ipa:
                    c = 0x2cc  # secondary
                    if stress > STRESS_IS_SECONDARY:
                        c = 0x02c8  # primary
                    buf.append(chr(c))
                else:
                    buf.append(_STRESS_CHARS[stress])

        # write the phoneme body, applying ties between alphabetic chars
        count = 0
        for ch in body:
            c = ord(ch)
            if use_tie is not None:
                if count > 0 and (c < 0x2b0 or c > 0x36f) and ch.isalpha():
                    buf.append(use_tie)
            buf.append(ch)
            count += 1

        if entry.synthflags & SFLAG_LENGTHEN:
            lp = table.get(":")  # phonLENGTHEN mnemonic is ':'
            if lp:
                buf.append(write_ph_mnemonic(lp, use_ipa))

        pieces.append("".join(buf))

    return "".join(pieces)
