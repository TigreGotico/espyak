"""Public entrypoint for espyak.

Mirrors ``espeak-ng -q --ipa -v <lang>``. The translation pipeline (rule compiler →
matcher → stress → render) is built up across phases; this module wires the pieces
together and exposes a stable surface.
"""
from espyak import data_paths
from espyak.phoneme_tab import get_source
from espyak.render import render_phoneme_list, encode_phoneme_string
from espyak.rule_compiler import RuleSet
from espyak.dictionary import (
    Translator, translate_rules, set_word_stress, MnemIndex, DictList, LookupContext,
    remove_ending, _apply_replacements, _unpronounceable,
)
from espyak import constants as K
import unicodedata

# UCase_ga (translate.c): Irish eclipsis/lenition prefixes where a lowercase prefix directly
# before an uppercase letter is NOT a CamelCase word break. "?A" = prefix before any vowel.
_UCASE_GA = ("bp", "bhf", "dt", "gc", "hA", "mb", "nd", "ng", "ts", "tA", "nA")
_IRISH_VOWELS = set("aeiouáéíóúàèìòùAEIOUÁÉÍÓÚÀÈÌÒÙ")


def _ga_caps_prefix(tok, j):
    """True if tok[:j] + the uppercase tok[j] is an Irish capitalised-prefix (don't split)."""
    prefix, trig = tok[:j].lower(), tok[j]
    for p in _UCASE_GA:
        if prefix == p[:-1].lower():
            if p[-1] == "A":
                if trig in _IRISH_VOWELS:
                    return True
            elif trig.lower() == p[-1].lower():
                return True
    return False

# combining-mark codepoint -> espeak accent-name dictionary key (accents_tab, numbers.c)
_ACCENT_NAMES = {
    0x0301: "_acu", 0x0300: "_grv", 0x0302: "_cir", 0x0303: "_tld",
    0x0308: "_dia", 0x0327: "_ced", 0x030C: "_hac", 0x0306: "_brv",
    0x0307: "_dot", 0x0304: "_mcn", 0x0328: "_ogo", 0x030A: "_rng",
    0x0338: "_stk", 0x0337: "_stk", 0x030B: "_ac2", 0x0331: "_bar",
    0x0309: "_hok",
}
from espyak import language_data
from espyak.phoneme_program import Interpreter, set_regressive_voicing


from espyak.phoneme_tab import phNASAL, phLIQUID, phFRICATIVE, phVFRICATIVE, phVOWEL
from espyak.constants import phSTOP, phVSTOP
from espyak.render import PhonemeListEntry

_DOUBLE_TYPES = frozenset((phFRICATIVE, phVFRICATIVE, phNASAL, phLIQUID))


def _normalize_tones(plist, table, insert_default=True, clause_final_tone=None, force_default=False):
    """Tone language (vi): every syllable carries a tone immediately after its vowel.
    Move an existing tone (digit phoneme) to right after the vowel, or insert the default
    tone '1' (phonDEFAULTTONE) if the syllable has none. With ``insert_default=False`` (my:
    Burmese) only the per-syllable tone collapse runs — toneless syllables stay toneless.
    ``force_default=True`` is a BUG-REPLICATION path (shn, force_compat only): espeak discards the
    tone-mark phonemes its own rules produce and emits tone 1 for every syllable — we mirror that only
    when bug-exact output is requested. The default behaviour keeps the (correct) marked tones."""
    default = table.get("1")
    # vi: the LAST vowel of the clause (here, the word) carries the end-of-clause ngang tone 7 when
    # it would otherwise take the default tone 1 (ba -> bˈaː7, but ba ba -> bˈaː1 bˈaː7).
    _final_default = table.get(clause_final_tone) if clause_final_tone else None
    _last_vowel = next((k for k in range(len(plist) - 1, -1, -1)
                        if plist[k].ph.type == phVOWEL and not plist[k].deleted), None)
    # A tone that is the word's FIRST phoneme is orphaned — a Burmese visarga split from its
    # syllable by the asat word-break (း…စာကို -> 2stskˈo). Move it to after the word's last
    # vowel (stskˈo2). (A tone after the vowel, e.g. i1 then visarga 2 in i12, is not first, so
    # it is left for the collapse pass below.)
    live = [k for k in range(len(plist)) if not plist[k].deleted]
    if live and plist[live[0]].ph.mnemonic.isdigit() and plist[live[0]].ph.type != phVOWEL:
        last_v = next((k for k in reversed(live) if plist[k].ph.type == phVOWEL), None)
        if last_v is not None and last_v > live[0]:
            plist.insert(last_v + 1, plist.pop(live[0]))
    i = 0
    while i < len(plist):
        if plist[i].ph.type == phVOWEL and not plist[i].deleted:
            # find the tones within this syllable (before the next vowel). A syllable may carry
            # the vowel's inherent tone (my ီ -> i1) AND an explicit tone marker (visarga း -> 2);
            # the explicit one overrides, so keep only the LAST and drop the earlier defaults
            # (kri1 2 -> kri2, not kri12).
            j = i + 1
            tones = []
            while j < len(plist) and plist[j].ph.type != phVOWEL:
                if plist[j].ph.mnemonic.isdigit():
                    tones.append(j)
                j += 1
            if force_default:  # bug-exact: drop the marked tones, force the default tone (shn)
                for t in reversed(tones):
                    plist.pop(t)
                if default is not None:
                    plist.insert(i + 1, PhonemeListEntry(default))
            elif tones:
                for t in reversed(tones[:-1]):
                    plist.pop(t)  # drop the earlier (default) tones
                tone_at = tones[-1] - (len(tones) - 1)
                if tone_at != i + 1:
                    plist.insert(i + 1, plist.pop(tone_at))  # move kept tone after the vowel
            elif insert_default and default is not None:
                # the clause-final ngang tone (vi 7) only on a PRIMARY-stressed final syllable: a $u
                # function word stays secondary and keeps the plain tone 1 (cho -> tʃˌɔ1, ba -> bˈaː7)
                _d = (_final_default if (_final_default is not None and i == _last_vowel
                                         and plist[i].stresslevel >= 4) else default)
                plist.insert(i + 1, PhonemeListEntry(_d))
            i += 1  # skip the tone we just placed
        i += 1


def _shn_long_vowel_tone_copy(plist):
    """espeak force_compat bug (shn): the tone after a vowel that has an explicit `ipa` string
    renders as a COPY of that vowel's ipa, doubling it (ၵႄ -> kɛɛ, ၵၢ -> kaːaː), instead of the
    tone digit. Short/mnemonic vowels (no ipa: a, i, u) keep the digit (ၵႃ -> ka1)."""
    for i in range(1, len(plist)):
        ent = plist[i]
        if getattr(ent, "deleted", False):
            continue
        ph = ent.ph
        if not (ph.mnemonic.isdigit() and ph.type != phVOWEL):
            continue
        v = next((plist[k] for k in range(i - 1, -1, -1)
                  if not getattr(plist[k], "deleted", False)), None)
        if v is None or v.ph.type != phVOWEL:
            continue
        vipa = getattr(v, "ipa_override", None)
        if vipa is None:
            vipa = getattr(v.ph, "ipa", None)
        if vipa:
            ent.ipa_override = vipa


# In-band codepoint spelling (espeak's TranslateLetter, translateword.c:786). When a
# language's letter-to-sound rules can't translate a non-alphabetic character (a Myanmar
# medial ွ U+103D / ှ U+103E, the visarga း U+1038, ...), espeak does NOT drop it: it spells
# the character by its Unicode codepoint name *in place* on the shared ph_list2 buffer
# (dictionary.c:2277 `LookupLetter`). The spelled run is
#   (en)<alphabet name>(shn)<"letter"><hex-digit names>
# where the alphabet name (_my -> en "Myanmar") is rendered with the DEFAULT (en) voice via an
# in-band phonSWITCH, "letter" (l'et@) and the four hex-digit names come from shn's own _0.._9
# (the a-f hex letters fall back to the English `hex_letters` mnemonics, read with shn's table),
# and crucially the SOURCE language's render-time post-passes — shn's force-tone-1 default and the
# `_shn_long_vowel_tone_copy` bug — run ACROSS the switch boundary onto the English phonemes
# (mjˈɑː -> mjˈɑː1, A@ -> ɑːɑː). The result is invariant for a given codepoint, so it is cached.

# espeak hex_letters[] (translateword.c:775): English a-f names, read with the source phoneme table
_HEX_LETTERS = {"a": "'e:j", "b": "b'i:", "c": "s'i:", "d": "d'i:", "e": "'i:", "f": "'ef"}

# sentinel wrapping a codepoint that translate_rules could not pronounce and that espeak spells
# in place (\x01<hex>\x02). It survives stress assignment (no vowels) and is replaced by the
# rendered codepoint-spelling in _render_phonemes — the carrier for the in-band phonSWITCH.
_SPELL_CP_OPEN = "\x01"
_SPELL_CP_CLOSE = "\x02"


def _spell_cp_sentinel(cp):
    return _SPELL_CP_OPEN + format(cp, "x") + _SPELL_CP_CLOSE


def _re_tone_after_length(s):
    # a tone digit immediately before the length mark ː -> after it (sˈi2ː -> sˈiː2)
    import re
    return re.sub(r"([0-9])(ː)", r"\2\1", s)


def _double_long_consonants(plist, double_rfx_stop=False):
    """phonemelist.c: a length phoneme (`:`) after a fricative/nasal/liquid lengthens by
    doubling the consonant (it mm/ll/ss); after a DIPHTHONG it repeats the diphthong
    (af e@: -> iəiə, o@: -> ʊəʊə) — espeak renders a lengthened diphthong by writing it twice,
    not vowel+ː (which stays for monophthongs: A: -> ɑː).

    With double_rfx_stop (bn), a lengthened RETROFLEX stop also doubles (bn টা টা ->
    ʈʈ, ড়া -> ɖɖ): unlike a plain stop (kː) the retroflex ʈ/ɖ has an explicit single-char
    ipa, which espeak's IPA writer repeats instead of appending ː (দশটা -> dɔʃʈʈˈa)."""
    # espeak builds the phoneme list with phonLENGTHEN as a single SFLAG_LENGTHEN bit on the
    # preceding phoneme (translate.c:590), so repeated ':' (a dict entry's `q::abl`) collapse to
    # ONE length effect — fa ق.ظ q::abl -> qːabl, not qːːabl. Drop each ':' that merely follows
    # another ':' before the doubling pass runs (its length is already accounted for).
    prev_colon = False
    for i in range(1, len(plist)):
        e = plist[i]
        if e.deleted:
            continue
        is_colon = e.ph.mnemonic == ":"
        if is_colon and prev_colon:
            e.deleted = True
            continue
        prev_colon = is_colon
    for i in range(1, len(plist)):
        e = plist[i]
        if e.deleted or e.ph.mnemonic != ":":
            continue
        prev = plist[i - 1].ph
        if (double_rfx_stop and prev.type in (phSTOP, phVSTOP)
                and prev.place == "rfx" and prev.ipa is not None):
            e.ph = prev
            continue
        if prev.type not in _DOUBLE_TYPES and "rhotic" in getattr(prev, "flags", ()) and prev.ipa:
            # a geminate rhotic FLAP (`*`, ipa ɾ) doubles rather than taking ː: espeak's length
            # phoneme after a flap repeats the segment (ur متفرق r: -> ɾɾ), so the coda copy can
            # then trill (coda_trill_r -> rɾ). A flap is a synth phoneme (not a liquid type), so
            # it isn't caught by _DOUBLE_TYPES.
            e.ph = prev
            continue
        if prev.type in _DOUBLE_TYPES or (
                prev.type == phVOWEL and (
                    # a MONOPHTHONG with an explicit ipa string (mto i/a/o/e, af a) is lengthened
                    # by repeating it (i: -> ii); one rendered via its mnemonic (ipa None: mto u,
                    # af i) and a CLOSING diphthong (aɪ) take ː instead
                    (prev.starttype == prev.endtype and prev.ipa is not None)
                    # a CENTRING diphthong (endtype #@: e@ -> iə) also repeats (e@: -> iəiə)
                    or (prev.starttype != prev.endtype and prev.endtype == "#@"))):
            e.ph = prev  # replace the length marker with a copy of the consonant/diphthong


def _decompose_hangul(word):
    """Break Hangul syllable blocks (U+AC00–D7A3) into conjoining jamo L/V/T, matching
    espeak's translateword.c: lead 11 (ㅇ, silent initial) is dropped; the final is
    always emitted (0x11A7 filler when none), so ko_rules see the jamo it has groups for."""
    out = []
    for ch in word:
        code = ord(ch) - 0xac00
        if 0 <= code <= 0xd7a3 - 0xac00:
            initial = (code // 28) // 21
            if initial != 11:
                out.append(chr(initial + 0x1100))
            out.append(chr((code // 28) % 21 + 0x1161))  # medial vowel
            out.append(chr(code % 28 + 0x11a7))           # final (filler if none)
        else:
            out.append(ch)
    return "".join(out)


def _reduce_extra_primaries(ph):
    """espeak's prefix-primary reduction (translateword.c:557): keep the first primary
    stress mark in a prefix, reduce any later primary marks to secondary."""
    out = []
    seen = False
    i, n = 0, len(ph)
    while i < n:
        if ph[i:i + 2] == "''":      # priority marker — leave intact
            out.append("''")
            i += 2
        elif ph[i] == "'":           # primary stress
            out.append(",," if seen else "'")
            seen = True
            i += 1
        else:
            out.append(ph[i])
            i += 1
    return "".join(out)


class G2P:
    """Grapheme-to-phoneme translator for one language."""

    def __init__(self, lang="en", force_compat=False):
        # force_compat=True reproduces espeak-ng byte-for-byte, BUGS INCLUDED (e.g. shn discards its
        # own tone marks). The default (False) is the linguistically correct G2P; every place it
        # deviates from espeak is gated on this flag and recorded in docs/divergences.md.
        self.lang = lang
        self.force_compat = force_compat
        self._phsource = get_source()
        self._voice = data_paths.voice_path(lang)
        # phoneme table name defaults to the language code; voice file may override.
        self._ph_table_name = self._resolve_phoneme_table(lang)
        self._mnem = MnemIndex(self.phoneme_table)
        self._interp = Interpreter(self._phsource, self.phoneme_table)
        # rule engine (letter-to-sound). Loaded lazily per language.
        self._config = language_data.get_config(lang)
        if self._voice_dictrules:
            # voice-file `dictrules` are authoritative; union with any hardcoded config value.
            merged = sorted(set(self._config.get("dictrules", ())) | set(self._voice_dictrules))
            self._config = {**self._config, "dictrules": merged}
        self._rules = RuleSet.compile_file(data_paths.rules_path(lang))
        self._sort_rules_by_phoneme_code()
        self._tr = Translator(phsource=self._phsource, config=self._config)
        self._tr.rules = self._rules
        # _listx is the supplementary lexical-stress / vocalized dictionary (ar/ru/it/bg/
        # tr/he/...). CompileDictionary (compiledict.c:1581) compiles _list and _listx in an
        # order gated on langopts.listx, and each entry is PREPENDED to its hash chain (the
        # last file compiled ends up first in the chain, so it wins LookupDict2). Only
        # cmn/yue/zh set langopts.listx=1 -> compile order (_list, _listx) -> _listx wins.
        # Every OTHER language compiles (_listx, _list) -> _LIST wins the tie (it `lord $alt`
        # in _list beats `lord $alt2` in _listx -> ɔ, not o). espyak's lookup takes the
        # last-loaded entry (reversed(entries)), so load the winning file LAST. _extra is
        # compiled after both in espeak, so it always wins -> load it last of all.
        if self._config.get("listx"):
            _list_files = [data_paths.list_path(lang), data_paths.listx_path(lang)]
        else:
            _list_files = [data_paths.listx_path(lang), data_paths.list_path(lang)]
        self._dict = DictList.load(*_list_files, data_paths.extra_path(lang))
        self._dict.case_sensitive_letters = bool(self._config.get("case_sensitive_letters"))
        # the matcher's $p_alt / $list DollarRule needs a part-word dict lookup (LookupFlags)
        self._tr.dict = self._dict

    def _sort_rules_by_phoneme_code(self):
        # espeak sorts each group's rules by the COMPILED phoneme-code string, then the match
        # string (compiledict.c string_sorter); the matcher's last-best-wins (>=) tie-break
        # then picks the sort-last equal scorer. The codes are phoneme-table indices, so we
        # must sort by those, NOT the mnemonic ASCII: tn code(b)<code(B) keeps b->B winning,
        # while ga code(@)<code(v) makes mh->v win over r)m->@m. (A mnemonic sort gets ga
        # right but tn wrong, since 'B'<'b' in ASCII but code(b)<code(B).)
        code = {m: i for i, m in enumerate(self.phoneme_table.phonemes)}
        tok = self._mnem.tokenize

        # group_seq leads the key: it's constant within a single .group block (so this is identical
        # to the plain code sort there), but when one match group is fed by TWO .group blocks (bn's
        # duplicate .group এ: এ->& then এ->e), the later block sorts last and wins the >= tie-break.
        def key(rule):
            return (rule.group_seq, [code.get(m, 0xffff) for m, _ in tok(rule.phonemes)], rule.match_str)
        for d in (self._rules.groups1, self._rules.groups2, self._rules.groups3):
            for rules in d.values():
                rules.sort(key=key)

    def _resolve_phoneme_table(self, lang):
        # voice file `phonemes <table>` line(s), else the lang code, else base1/base.
        # A voice may list several `phonemes` lines (e.g. xex: "phonemes pt-br" then
        # "phonemes pt"); a later line overrides, so try them last-first, falling back to
        # earlier ones when a name isn't a real table (pt-br -> pt).
        voiced = []
        self._voice_dictrules = []
        if self._voice:
            try:
                with open(self._voice, encoding="utf-8") as fh:
                    for line in fh:
                        parts = line.split()
                        if not parts:
                            continue
                        if parts[0] == "phonemes" and len(parts) > 1:
                            voiced.append(parts[1])
                        elif parts[0] == "dictrules":
                            # `dictrules N M ...` permanently sets those numbered ?-conditions
                            # (pt/ca/es/fr final-s->ʃ etc. are gated on ?1). Numbers up to a
                            # trailing comment.
                            for p in parts[1:]:
                                if p.isdigit():
                                    self._voice_dictrules.append(int(p))
                                else:
                                    break
            except OSError:
                pass
        candidates = list(reversed(voiced)) + [lang, "base1", "base"]
        for name in candidates:
            if self._phsource.table(name) is not None:
                return name
        return "base"

    @property
    def phoneme_table(self):
        return self._phsource.table(self._ph_table_name) or self._phsource.table("base1")

    def render(self, phoneme_string, ipa=True, tie=None, separator=None):
        """Render a raw espeak phoneme mnemonic string (as produced by the rules, or as
        given inside ``[[...]]``) to IPA or Kirshenbaum output.

        This is the output half of the pipeline, usable on its own.
        """
        plist = encode_phoneme_string(phoneme_string, self.phoneme_table)
        return render_phoneme_list(
            plist, self.phoneme_table, ipa=ipa, tie=tie, separator=separator
        )

    def translate_word(self, word, tonic=-1, caps_stress=0, all_upper=None, first_upper=None,
                       at_end=True):
        """Translate a single lowercase word to its mnemonic phoneme string.

        Pipeline: dictionary `_list` lookup -> (fallback) letter-to-sound rules ->
        stress assignment. `tonic` (>=0) forces the word's main stress to that level,
        used for the tonic (clause-stressed) word. `caps_stress` (>0) forces the main
        stress onto that syllable (Lojban LOPT_CAPS_IN_WORD: a capital marks stress).
        ``at_end`` is False for a non-clause-final word so a $atend-gated entry (smj O -> o:
        only at clause end) fails and falls to the rules (mid-clause O -> oɔ); it defaults True
        (the historical isolated-word assumption) and is only threaded for atend_clause_final langs.
        """
        ctx = LookupContext(
            # the caller passes the ORIGINAL-case flags: the word arriving here is already lowercased,
            # so word.isupper()/word[0].isupper() can't recover them (et USA -> $abbrev $allcaps; a
            # $capital entry needs first_upper).
            first_upper=word[:1].isupper() if first_upper is None else first_upper,
            all_upper=(word.isupper() and any(c.isalpha() for c in word))
            if all_upper is None else all_upper,
            at_end=at_end,
            dict_condition=self._tr.dict_condition,
        )
        self._tr.expect_verb = 0
        self._suffix_nvowels = 0  # set by the suffix path; excluded from auto-secondary
        self._suffix_dict_flags = 0  # a flags-only stem entry's flags adopted by the suffix path
        self._from_dict = False   # set by _translate_core when phonemes come from a dict entry
        self._neutral_tone = False  # cmn neutral tone (pinyin 5): the syllable is unstressed
        self._spelled = False     # set by _translate_core for a $abbrev spelled-out word
        self._spell_prerendered = False  # name-first spell returns final IPA (as foreign-letter spell)
        self._textmode_empty = False  # a $text->spell word that loops to '' (mto english)
        ph, flags = self._translate_core(word.lower(), ctx)
        if _SPELL_CP_OPEN in ph:
            # the rules emitted an in-band codepoint-spelling sentinel (\x01<hex>\x02) for a
            # character they could not pronounce (a Myanmar medial / visarga). Stress the ordinary
            # phonemes around it separately and keep the sentinel intact for _render_phonemes;
            # the spelled run carries its own spelling stress (SetSpellingStress) so it must not be
            # fed through set_word_stress (which strips the control bytes and would lose it).
            import re as _re
            parts = _re.split(r"(\x01[0-9a-f]+\x02)", ph)
            out = []
            last = len(parts) - 1
            for i, part in enumerate(parts):
                if part.startswith(_SPELL_CP_OPEN):
                    out.append(part)
                elif part:
                    out.append(set_word_stress(self._tr, part, self._mnem, dict_flags=flags,
                                               tonic=(tonic if i == last else -1)))
            return "".join(out)
        if self._spelled:
            # a spelled-out abbreviation is already stressed by _join_spelled (SetSpellingStress);
            # don't re-run set_word_stress, which would put the clause tonic on the last sub-word
            # of a multi-word letter name (bs acw 'w' = dvostruko və -> vˈə instead of və).
            return ph
        if caps_stress and not (flags & 0x8):  # caps-marked syllable (not a $u word)
            flags = (flags & ~0x7) | (caps_stress & 0x7)
        self._u_out_str = None
        ph_clean = ph.strip("\"'")
        if ph_clean.startswith("_^_"):
            return ph_clean  # language-switch marker, resolved in phonemize
        if (self._config.get("unstress_u_words") and (flags & 0x8)
                and not (flags & K.FLAG_STRESS_END) and "||" not in ph and tonic >= 4):
            # $u (unstressed function word) carrying the clause accent in a language that
            # REDUCES such words (mk/smj; espeak's intonation model). The phoneme programs
            # must see the word's natural (un-tonic) stress so each vowel laxes per its own
            # program (mk ChangeIfNotStressed: или->ˈɪlɪ; smj ChangeIfUnstressed laxes
            # monosyllabic gis->kˈɪːs but not villap's secondary-stressed iː). Output keeps
            # the clause accent, overlaid in _render_phonemes. `$u+` (FLAG_STRESS_END, e.g.
            # mk verb имам) keeps its stress; languages that PROMOTE isolated $u words to
            # full stress (ru: для->dɭʲˈɑ) do not set unstress_u_words, so are unaffected.
            self._u_out_str = set_word_stress(self._tr, ph, self._mnem,
                                              dict_flags=flags, tonic=tonic)
            return set_word_stress(self._tr, ph, self._mnem, dict_flags=flags, tonic=-1)
        if "||" in ph and "|" in ph.replace("||", ""):
            # the value contains a `|` MORPHEME barrier (one multi-morpheme sub-word, ar صلعم
            # s[alla:|?allahu|Alajhi||wa||sallam): espeak treats the WHOLE thing as ONE word for
            # stress (a single SetWordStress over all 11 vowels; the || only break the rendering),
            # so the language stress rule (ar 3R) lands the primary near the antepenult -> wˈa.
            return set_word_stress(self._tr, ph, self._mnem, dict_flags=flags, tonic=tonic)
        if "||" in ph and self._config.get("whole_word_stress"):
            # ur: a `||` multi-word letter/abbreviation name is ONE stress domain. espeak's
            # SetWordStress scans the whole phoneme buffer across the word-break spaces, so the
            # language rule (ur stressRule 1RH = last heaviest non-final syllable) places a single
            # primary over all the vowels and the auto-secondary loop fills the rest — NOT a primary
            # per sub-word. (ح bar.i:||He: -> bar.ˈiː heː, not bˈar.i hˈeː.)
            return set_word_stress(self._tr, ph, self._mnem, dict_flags=flags, tonic=tonic)
        if "||" in ph:
            # multi-word dictionary entry: stress each sub-word separately, preserving the
            # word break for the renderer. A non-final sub-word is unstressed when it has no
            # explicit `'` AND is either a single vowel (a non-tonic monosyllable: gn
            # espeak -> i||sp'ik -> i spˈik) or the language is S_PRIORITY_STRESS (it
            # a||bi||tʃ'i -> a/bi unstressed). Multi-syllable unmarked parts keep their
            # lexical stress (es uβe||doβle -> uˈβe doˈβle); `'`-marked parts stay primary
            # (it fbi -> 'ef||b'i||'ai -> ˈef bˈi ˈai).
            priority = bool(self._config.get("stress_flags", 0) & K.S_PRIORITY_STRESS)
            parts = ph.split("||")
            last = len(parts) - 1
            # If a part already carries an explicit primary (`'`), the clause accent is placed
            # there — an unmarked LAST part is NOT forced to the tonic (ms com = d'Ot||kOm ->
            # dˈɔt kɔm, the kɔm bare, not dˈɔt kˈɔm).
            has_primary = any("'" in p for p in parts)

            def _part_tonic(p, is_last, idx):
                # honour explicit stress marks in the part (gn nvda -> ,ene||B,e||D,e_'a
                # keeps each letter's secondary, final primary): no forced tonic.
                if "'" in p or "," in p:
                    return -1
                if is_last and not has_primary:
                    if self._config.get("compound_first_stress") and len(parts) == 2:
                        return 3  # ar compound unit (كغ = kilu:||gHra:m): nucleus is the FIRST
                        # element, so the last part takes a secondary (kˈiluː ɣɹˌaːm).
                    return tonic
                # an unmarked part FLANKED by explicit primaries takes a secondary (ms dymm
                # d'uli||jang||mah'a||m'uli@ -> the bare jang -> jˌanɡ); an EDGE unmarked part
                # (gn i before the only primary) stays bare.
                if (any("'" in parts[j] for j in range(idx))
                        and any("'" in parts[j] for j in range(idx + 1, len(parts)))):
                    return 3  # STRESS_IS_SECONDARY
                # a 3+-word phrase with NO lexical accent gets clause intonation: onset (first)
                # secondary, interior bare, nucleus (last) primary (ku hwd hEr||wEki||dIn ->
                # hˌɛr wɛki dˈɪn). A 2-word phrase keeps both accented (es uβe||doβle).
                if not has_primary and len(parts) >= 3:
                    return 3 if idx == 0 else 1
                single = sum(1 for _m, ph_ in self._mnem.tokenize(p)
                             if ph_.type == phVOWEL and "nonsyllabic" not in ph_.flags) <= 1
                return 1 if (single or priority) else 4
            stressed = [
                set_word_stress(self._tr, p, self._mnem,
                                dict_flags=(flags if i == last else 0),
                                tonic=_part_tonic(p, i == last, i))
                for i, p in enumerate(parts)
            ]
            for _i in range(1, len(stressed)):
                # stress clash: a part whose FIRST stressed syllable is a secondary (,,) drops it
                # when the previous part ends in a primary — the two stressed syllables are adjacent
                # across the word break (es é = 'e||aTEntw'aDa -> ˈe aθɛntwˈaða; ü = 'u||k,,on||... ->
                # ˈu kon ...). Only the first mark, so an interior primary is kept.
                _part = stressed[_i]
                _marks = [(_part.find(m), m) for m in ("'", ",,", "%%") if _part.find(m) >= 0]
                if not _marks:
                    continue
                _pos, _mark = min(_marks)
                _prev = stressed[_i - 1]
                _lp = _prev.rfind("'")
                # the previous part must END in a primary syllable (the primary on its LAST vowel)
                # for the syllables to be adjacent — ms d'uli||jang keeps jˌanɡ (primary on u, not li).
                _prev_ends_primary = _lp > _prev.rfind(",,") and sum(
                    1 for _m, _ph in self._mnem.tokenize(_prev[_lp + 1:])
                    if _ph.type == phVOWEL) == 1
                if _mark == ",," and _prev_ends_primary:
                    stressed[_i] = _part[:_pos] + _part[_pos + 2:]
            return "||".join(stressed)
        return self._apply_alt_attribute(
            set_word_stress(self._tr, ph, self._mnem, dict_flags=flags, tonic=tonic,
                            suffix_vowels=getattr(self, "_suffix_nvowels", 0)), flags)

    def _apply_alt_attribute(self, ph, flags):
        """ApplySpecialAttribute2 (translateword.c, LOPT_ALT&2: it/pt/sl). A $alt/$alt2 word
        shifts the vowel right after the PRIMARY stress: $alt opens it (e->E, o->O), $alt2
        closes it (E->e, O->o). sl 'ena' ($alt): 'e:na -> 'E:na -> ˈɛːna."""
        if not (self._config.get("lopt_alt")
                and (flags & (K.FLAG_ALT_TRANS | K.FLAG_ALT2_TRANS))):
            return ph
        i = ph.find("'")
        if i < 0 or i + 1 >= len(ph):
            return ph
        j = i + 1
        repl = ({"E": "e", "O": "o"} if (flags & K.FLAG_ALT2_TRANS)
                else {"e": "E", "o": "O"}).get(ph[j])
        return ph[:j] + repl + ph[j + 1:] if repl else ph

    def _translate_core(self, word, ctx, word_flags=0, inherit_flags=0):
        """Dictionary lookup, else rules with prefix/suffix removal+retranslation.

        Returns (phonemes, dict_flags). Handles one prefix (recursing on the stem) or
        one suffix per call (TranslateWord3's prefix/suffix branches).

        ``inherit_flags`` carries the parent word's dict flags into a prefix-stripped
        stem: TranslateWord3 reuses one ``dictionary_flags`` array across the prefix
        loop (translateword.c:428), so the stem's rules still see the whole word's
        $alt flag (only overwritten by the stem's own lookup when the original was 0).
        That keeps nl gestage/inzage on the `age (_$w_alt a:Q@` rule (ɣ, not French ʒ)."""
        if self._config.get("decompose_hangul"):
            word = unicodedata.normalize("NFC", word)
        # espeak's SubstituteChar (.replace table) normalises the source BEFORE the dict lookup,
        # not just for rule matching: da/sv/no map ä->æ, ö->ø, ü->y so a foreign accented letter
        # is pronounced as its native equivalent and never reaches its `$accent` dict entry, while
        # letters with no mapping (é) still hit `$accent` and get spelled.
        word = _apply_replacements(getattr(self._rules, "replacements", None), word)
        # CheckDottedAbbrev / LookupDictList (translateword.c:1046, dictionary.c:2737): the clause
        # reader spaces every dot in a single-letter run (a.b.c -> "a . b . c"), so LookupDictList
        # reconstructs the key by joining the letters with dots but DROPPING the trailing dot (a.b.
        # -> "a.b"). espyak keeps the dotted token whole, so reproduce the reconstruction here: an
        # entry like eo `a.k` or fa `ق.ظ` is matched, while a trailing-dot-only entry (fo `m.a.`)
        # is NOT — its real espeak fate is letter-by-letter spelling (handled below when unmatched).
        dotted_letters = self._check_dotted_abbrev(word)
        if dotted_letters is not None:
            word = ".".join(dotted_letters)
        dict_ph, dict_flags = self._dict.lookup(word, ctx)
        flags = dict_flags or 0
        # translateword.c keeps the prefix-parent's dictionary_flags across the prefix
        # loop, only overwriting it from the stem's own lookup when the original was 0
        # (lines 422-428). So a prefix-stripped stem's rules see the WHOLE word's $alt
        # flag -> nl gestage/inzage stay on `age (_$w_alt a:Q@` (ɣ, not the French ʒ).
        if inherit_flags:
            flags = inherit_flags
        accent_entry = not dict_ph and getattr(self._dict, "_last_accent", False)
        if dict_ph:
            hangul = self._config.get("decompose_hangul")
            nfc_ph = unicodedata.normalize("NFC", dict_ph) if hangul else dict_ph
            if flags & K.FLAG_TEXTMODE:
                # $text: the entry value is text to re-translate (ta "tamil" -> தமிழ்,
                # Korean sandhi respellings). espeak recurses through TranslateWord on the
                # replacement (dictionary.c:2881), so the replacement gets a FRESH dict lookup
                # before the rules — a respelling that is itself a dict headword uses that entry's
                # pronunciation/stress (de matthias->mathias = matˈiːɑːs, jonathan->jonatan = $1).
                word = nfc_ph
                if not (self._config.get("neutral_tone_unstress")
                        and nfc_ph[-1:] == "5"):
                    rctx = LookupContext(dict_condition=self._tr.dict_condition)
                    sub_ph, sub_flags = self._dict.lookup(word, rctx)
                    if sub_flags is not None and not (sub_flags & K.FLAG_TEXTMODE):
                        if sub_ph:
                            self._from_dict = True
                            return sub_ph, sub_flags or 0
                        # flags-only entry (de jonatan -> $1): carry the replacement's stress
                        # flags into the rules pass so $1/$2 place the primary (jˈoːnatˌɑːn).
                        flags = sub_flags
                if (self._config.get("neutral_tone_unstress") and nfc_ph[-1:] == "5"
                        and (len(nfc_ph) < 2 or not nfc_ph[-2].isdigit())):
                    self._neutral_tone = True  # cmn neutral tone -> unstressed (戚 qi5 -> tɕhi1)
            elif hangul and any("가" <= c <= "힣" for c in nfc_ph):
                word = nfc_ph  # Korean Hangul respelling without an explicit $text flag
            else:
                # phonemes come straight from a dict entry (SFLAG_DICTIONARY): espeak skips
                # the stress-condition reductions (ChangeIfNotStressed/...) on these unless
                # LOPT_REDUCE&1 (only Italian), so an unstressed long vowel keeps its length
                # (fo hina -> hiːna).
                self._from_dict = True
                return dict_ph, flags
        if dict_flags is not None and (flags & K.FLAG_ABBREV):
            # $abbrev with no pronunciation -> spell out as individual letter names
            self._spelled = True
            return self._spell_word(word), 0
        if not dict_ph and dotted_letters is not None:
            # CheckDottedAbbrev (translateword.c:1046): a run of single letters separated by dots
            # (a.b.c, A.C., m.a.) with no matching dict entry is spelled out letter by letter
            # (a.b.c -> ˌeɪbˌiːsˈiː). The whole-word dict lookup ran first (so the fa ق.ظ / ar د.ج
            # dict entries win and are NOT respelled); reaching here means the reconstructed key
            # had no pronunciation, so SpeakIndividualLetters spells the joined letters.
            self._spelled = True
            return self._spell_word("".join(dotted_letters)), 0
        if not dict_ph and not accent_entry and _unpronounceable(self._tr, word):
            # Unpronouncable (translateword.c): a word with no dict pronunciation and no vowel letter
            # is spelled out (ca Mgfc, en th). Latin-script + non-tonal only (guard in _unpronounceable).
            self._spelled = True
            return self._spell_word(word), 0
        if self._config.get("decompose_hangul") and any("가" <= c <= "힣" for c in word):
            # syllable -> conjoining jamo (with fillers) for the rules (already NFC above).
            word = _decompose_hangul(word)
        self._tr._spell_word = False
        ph, end_type, end_ph = translate_rules(
            self._tr, word, self._mnem, word_flags=word_flags, want_endings=True,
            dict_flags=flags)
        if (not ph.strip() and word and word.isascii() and any(c.isalpha() for c in word)
                and self._config.get("letter_bits_offset")
                and not (flags & K.FLAG_TEXTMODE and getattr(self, "_textmode_empty", False))):
            # alphabets[] block-switch (dictionary.c:2252-2261): a $text dictionary entry whose
            # value is Latin text (pa ਸੋਫਟਵਿਅਰ -> "software") re-translates that text, but the
            # current language's script is non-Latin (letter_bits_offset != 0). The Latin letters
            # belong to the implicit Latin/English block, an AL_WORDS alphabet whose language is
            # not the current one, so espeak emits a word-level phonSWITCH to English and brackets
            # the run (en)…(orig). Carry the replacement text in the _^_ switch marker so the
            # switched language translates that text (software), not the original Gurmukhi token.
            return "_^_en|" + word, flags
        if ph.lstrip("\"'").startswith("_^_") and word.isascii():
            # the rules emitted a phonSWITCH directly (pa_rules has explicit `_^_EN` rules for some
            # Latin sequences) AND also tripped FLAG_SPELLWORD on an untranslatable letter. espeak
            # returns immediately on a phonSWITCH (dictionary.c:2297), so the switch wins over the
            # spell-word: carry the replacement text so English translates `software`, not the token.
            target = ph.lstrip("\"'")[3:].split("|")[0].lower().strip()
            return "_^_%s|%s" % (target, word), flags
        if getattr(self._tr, "_spell_word", False):
            self._spelled = True
            if flags & K.FLAG_TEXTMODE:
                # a $text-replaced word that then needs spelling re-reads the ORIGINAL word, which
                # replaces again and loops -> espeak yields nothing (mto english -> ínglish -> '').
                # This empty is intentional: it must NOT trigger the foreign-word en-switch.
                self._textmode_empty = True
                return "", 0
            return self._spell_letters(word), 0
        if end_type and (end_type & K.SUFX_P) and not (word_flags & K.FLAG_NO_PREFIX):
            # confirm_prefix (translateword.c:341-364): before committing to a prefix, espeak
            # re-translates the WHOLE word with FLAG_NO_PREFIX to see whether it also carries a
            # standard suffix. If it does, that suffix is removed and the stem re-translated; if
            # the stem then no longer triggers the prefix rule, the prefix is *discarded* and the
            # suffix result wins (de unserer: `un` prefix + `erer` suffix -> stem `uns` is too
            # short to re-trigger `un (@P2`, so the word is `uns`+`@r3` = ˈʊnzər3, not zˈeːrɜ).
            if not (end_type & K.SUFX_B):
                ph2, end2, end_ph2 = translate_rules(
                    self._tr, word, self._mnem,
                    word_flags=word_flags | K.FLAG_NO_PREFIX, want_endings=True,
                    dict_flags=flags)
                if end2 and not (end2 & K.SUFX_P):
                    stem2, _ = remove_ending(self._tr, word, end2)
                    _sp, sp_end_type, _se = translate_rules(
                        self._tr, stem2.strip(), self._mnem,
                        word_flags=word_flags, want_endings=True, dict_flags=flags)
                    if not (sp_end_type & K.SUFX_P):
                        # prefix no longer recognised on the suffix-stripped stem: keep the suffix,
                        # drop the prefix, and fall through to the standard suffix branches below
                        # (SUFX_Q keeps the in-context stem — ro reci -> rˈetʃʲ, not rˈekʲ).
                        end_type, end_ph, ph = end2, end_ph2, ph2
            if end_type & K.SUFX_P:
                # still a prefix: remove it, translate the stem, prepend the prefix phonemes
                prefix_len = end_type & 0x3f
                rest = word[prefix_len:]
                rctx = LookupContext(dict_condition=self._tr.dict_condition, prefix_removed=True)
                rest_ph, _ = self._translate_core(rest, rctx, inherit_flags=flags)
                if self._config.get("lopt_prefixes") and ",," not in rest_ph:
                    # LOPT_PREFIXES (af/da/de/nl): "keep a secondary stress on the stem"
                    # (translateword.c:553). espeak runs SetWordStress(stem, tonic=3) so the
                    # stem's main vowel becomes SECONDARY, then reduces all but the first
                    # primary mark in the prefix; the final word-stress pass places the primary.
                    # Applied only at the INNERMOST prefix level: a stem that already carries a
                    # secondary (nested prefix, on+begrip) keeps its single secondary, not a second.
                    rest_ph = set_word_stress(self._tr, rest_ph, self._mnem,
                                              dict_flags=flags, tonic=3)
                    end_ph = _reduce_extra_primaries(end_ph)
                return end_ph + rest_ph, flags
        if end_type and (end_type & K.SUFX_Q):
            # "lookup stem in *_list without the suffix" (it `_S1q`): if the stem is a
            # dictionary entry use it, otherwise keep the in-context rule output (don't
            # re-run the rules on the stem — that would re-expose a geminate to the
            # word-end rule, palla->pal, and lose intervocalic context, casa s->z).
            stem, _qflags = remove_ending(self._tr, word, end_type)
            sctx = LookupContext(dict_condition=self._tr.dict_condition, suffix_removed=True,
                                 suffix_is_s=bool(_qflags & K.FLAG_SUFX_S))
            sdict_ph, _ = self._dict.lookup(stem.strip(), sctx)
            return (sdict_ph + end_ph if sdict_ph else ph + end_ph), flags
        if end_type and not (end_type & K.SUFX_P):
            self._suffix_dict_flags = 0
            sph = self._translate_with_suffix(word, end_type, end_ph, flags, ph)
            return sph, (flags or self._suffix_dict_flags)
        # $accent entry ($accent in *_list): spell the letter as base + accent name(s). espeak
        # spells these (found==0); the letters a language pronounces instead are normalised away
        # by .replace above (da ä->æ) before they ever reach their $accent entry, so no extra
        # guard is needed here. Also covers the rules-give-nothing fallback.
        if accent_entry or (not ph.strip() and len(word) == 1 and not word.isascii()):
            acc = self._spell_accented_letter(word.lstrip("_"))
            if acc:
                return acc, 0
            if accent_entry and self._config.get("accent_empty_no_fallback"):
                # lb: the $accent path is exclusive. With no accent-name spelling in the dict
                # (`_grv`/`_acu`/… absent) LookupLetterAccent writes nothing, so espeak emits an
                # EMPTY word — it never falls back to the letter-to-sound rules (à -> '', not ˈaː).
                return "", 0
        return ph, flags

    def _spell_letters(self, word):
        """FLAG_SPELLWORD: re-translate the word as individual letters, each its OWN primary
        word (mto amsterdam -> ˈa ˈm̩ s tʰ ˈe ɾ dˈe ˈa ˈm̩): the letter's SOUND via the rules,
        falling back to its spelled NAME only when the rules give nothing (mto 'd' -> de).

        A non-Latin script that opts in (spell_word_foreign_letter, as) instead spells each letter
        by its NAME first (TranslateLetter/LookupLetter, name-first: as ম -> mˈɔ not the rule mV),
        and a letter with no name in the source is rendered through its alphabet's language
        (as র -> (bn)ɾˈɔ(as)) — the per-letter phonSWITCH espeak uses for an unnamed in-block char."""
        if self._config.get("spell_word_foreign_letter"):
            return self._spell_letters_named(word)
        parts = []
        for ch in word:
            ph, _, _ = translate_rules(self._tr, ch, self._mnem)
            if not ph.strip():
                ph = self._lookup_letter(ch, False, False)
            if ph:
                parts.append(set_word_stress(self._tr, ph, self._mnem, tonic=4))
        return "||".join(parts)

    def _spell_letters_named(self, word):
        """Name-first spell-word (TranslateLetter, as): each letter by its NAME, a letter with no
        name switched to its alphabet's language. The named-letter runs are rendered together via
        _render_phonemes (so the ||-break spacing/stress matches mto), the foreign-letter segments
        (already IPA `(bn)…(as)`) spliced between. Returns fully-rendered IPA; _render_word returns
        it verbatim (self._spell_prerendered)."""
        self._spell_prerendered = True
        out = []
        run = []  # consecutive named letters (rendered as one ||-group)
        for ch in word:
            ph = self._lookup_letter(ch, at_end=False, first=True)
            if ph:
                run.append(set_word_stress(self._tr, ph, self._mnem, tonic=4))
                continue
            sw = self._spell_foreign_letter(ch)
            if sw is None:
                continue
            if run:
                out.append(self._render_phonemes("||".join(run), True, None, None))
                run = []
            out.append(sw)
        if run:
            out.append(self._render_phonemes("||".join(run), True, None, None))
        return " ".join(s for s in out if s)

    def _spell_foreign_letter(self, ch):
        """A single letter with no name in the source language is spelled through its alphabet's
        language (TranslateLetter, translateword.c:910): as র (no `র` name) switches to its
        alphabet `_bn` language bn and renders the letter's name there -> (bn)ɾˈɔ(as). The bn
        marker/return are wrapped exactly as a phonSWITCH; the result is one ||-segment so it sits
        as its own spelled word in the joined output."""
        from espyak import language_data
        entry = language_data.alphabet_from_char(ord(ch))
        if entry is None:
            return None
        lo, hi, name_key, switch_lang, flags = entry
        if (switch_lang is None or switch_lang == self.lang
                or (flags & language_data.AL_NOT_LETTERS)):
            return None
        tg = self._switch_g2p(switch_lang)
        if tg is None:
            return None
        # the letter's NAME in the switch language (bn র -> rO -> ɾˈɔ), stressed as a spelled letter.
        inner = tg._lookup_letter(ch, at_end=False, first=True)
        if not inner:
            return None
        rendered = tg._render_phonemes(
            set_word_stress(tg._tr, inner, tg._mnem, tonic=4), True, None, None)
        if not rendered.strip():
            return None
        return "(%s)%s(%s)" % (switch_lang, rendered, self._ph_table_name)

    def _check_dotted_abbrev(self, word):
        """Port of CheckDottedAbbrev (translateword.c:1046).

        espeak's clause reader turns `a.b.c` into `a . b . c ` (each dot spaced), then this
        walks single-letter+dot segments: a letter must be followed by a dot (with a trailing
        space, or end of run) — the final letter may have no dot. A `'s` after the run is kept
        (u.s.a.'s). On a run of count>1 letters it returns the joined letters (`abc`) for
        SpeakIndividualLetters; otherwise None (no abbreviation — leave the word as-is).
        """
        n = len(word)
        if n < 3 or "." not in word:
            return None
        letters = []
        i = 0
        while True:
            if i >= n or not word[i].isalpha():
                break
            ch = word[i]
            nxt = word[i + 1] if i + 1 < n else ""
            if nxt == ".":
                after = word[i + 2] if i + 2 < n else ""
                if after == "" or after == "'":
                    # trailing dot at end of word (a.b.) or before an apostrophe (u.s.a.'s):
                    # accept this letter and stop the run.
                    letters.append(ch)
                    break
                # a.X — only a real single-letter+dot segment continues the run; a dot
                # followed by anything other than another single-letter+dot (e.g. 'a.bc')
                # is not part of the abbreviation, so the next char must itself be a letter
                # that the loop will validate.
                letters.append(ch)
                i += 2
                continue
            if nxt == "" and letters:
                # final letter of the run with no trailing dot (a.b -> 'a','b')
                letters.append(ch)
                break
            # a letter not followed by a dot and not the final letter of a started run
            # (e.g. the 'b' in 'a.bc'): the abbreviation ends before it.
            break
        if len(letters) > 1:
            return letters
        return None

    def _spell_word(self, word):
        """Spell a word as individual letter names (SpeakIndividualLetters +
        SetSpellingStress). Each letter name is stressed, then non-final primaries are
        reduced to secondary by espeak's count%3 rule."""
        names = []
        n = len(word)
        for idx, ch in enumerate(word):
            name = self._lookup_letter(ch, at_end=(idx == n - 1), first=(idx == 0))
            if name:
                names.append(name)
        return self._join_spelled(names)

    def _join_spelled(self, names):
        """Stress each letter/accent name then apply SetSpellingStress. With
        langopts.spelling_stress the first letter keeps primary and the rest go to
        secondary; otherwise the last is primary with espeak's count%3 reduction."""
        stressed = [set_word_stress(self._tr, nm, self._mnem, tonic=4) for nm in names]
        n_stress = len(stressed)
        spelling_stress = self._config.get("spelling_stress", False)
        out = []
        for count, part in enumerate(stressed, 1):
            if spelling_stress:
                reduce = count > 1
            else:
                reduce = count != n_stress and (((count % 3) != 0) or (count == n_stress - 1))
            if reduce:
                part = part.replace("''", "'", 1).replace("'", ",,", 1)
            out.append(part)
        return "".join(out)

    def _spell_accented_letter(self, ch):
        """Speak an accented letter as base-letter name + accent name(s) ($accent).

        Decomposes via Unicode NFD instead of porting espeak's letter_accents table."""
        decomp = unicodedata.normalize("NFD", ch)
        if len(decomp) < 2:
            return None
        base, marks = decomp[0], decomp[1:]
        bn = self._lookup_letter(base, at_end=False, first=True)
        accent_names = []
        for mk in marks:
            key = _ACCENT_NAMES.get(ord(mk))
            if key:
                ph, _ = self._dict.lookup(key, LookupContext())
                if ph:
                    accent_names.append(ph)
        if not bn or not accent_names:
            return None
        # espeak's langopts.accents&1 (af, gn) spells the accent name BEFORE the base letter
        # (à -> "grave a"), not after (numbers.c LookupAccentedLetter, accents & 1).
        if self._config.get("accents_before"):
            # espeak accents&1 (af/gn): the accent name precedes the base letter and each is
            # its own primary-stressed unit (no count%3 spelling reduction) — à -> "grave a".
            return "".join(set_word_stress(self._tr, nm, self._mnem, tonic=4)
                           for nm in (accent_names + [bn]))
        # accent-AFTER path (numbers.c LookupAccentedLetter, accents&1 clear, _acu/_dia
        # accent_flags 0): the base letter takes a SECONDARY (phonSTRESS_2) and the accent name
        # keeps its own (primary) stress — é -> ˌiɛ ɑːkˈʉtː, NOT the spelling-stress first-primary
        # rule (which wrongly stressed the base: fi/et/lv/smj). The accent name's dict value
        # (_acu A:'ku-t:) already carries the primary, so stress it on its own (tonic=-1).
        base = set_word_stress(self._tr, bn, self._mnem, tonic=3)
        names = [set_word_stress(self._tr, nm, self._mnem, tonic=-1) for nm in accent_names]
        return "".join([base] + names)

    # spelling sets dict_condition group 1 so the rules' letter-NAME forms (gated `?1`,
    # e.g. pt "n" -> ɛn) win over the letter's sound. Languages that name letters via the
    # dict (`_X`) or with unconditional rules are unaffected.
    _SPELL_CONDITION = 1 << 1

    def _lookup_letter(self, ch, at_end, first):
        """Look up a single letter's name: the spelling entry `_X`, else the plain
        letter `X`, else letter-to-sound rules (LookupLetter)."""
        ctx = LookupContext(dict_condition=self._tr.dict_condition,
                            at_end=at_end, first_word=first)
        for key in ("_" + ch, ch):
            # case-sensitive: a lowercase letter must not borrow an UPPERCASE `_X` name entry
            # (smj `_O`/`O` name uppercase O; lowercase o spells via the rules -> oɔ, not o:).
            if not self._dict.has_exact(key):
                continue
            ph, _ = self._dict.lookup(key, ctx)
            if ph:
                return ph
        saved = self._tr.dict_condition
        self._tr.dict_condition = saved | self._SPELL_CONDITION
        # RULE_SPELLING ('W') marks a letter named WITHIN an acronym (connected to the next
        # letter) — it applies to non-final letters (pt internal s -> sʲ in adsl) but NOT the
        # last letter, which keeps its full name (pt final g -> ge in ecg, not the (_W -> Ze rule).
        self._tr._spelling = not at_end
        try:
            ph, _, _ = translate_rules(self._tr, ch, self._mnem)
        finally:
            self._tr.dict_condition = saved
            self._tr._spelling = False
        return ph

    def _translate_with_suffix(self, word, end_type, end_ph, dict_flags=0, incontext_ph=None):
        """Remove a standard suffix, (re)translate the stem, append the suffix phonemes.

        Port of the suffix branch of TranslateWord3 (single-suffix; SUFX_M multiple
        suffixes and SUFX_Q/SUFX_T variants are not yet handled). The word's dict $alt
        flags are carried into the stem retranslation (canonical keeps $alt3)."""
        stem, end_flags = remove_ending(self._tr, word, end_type)
        stem = stem.strip()
        self._tr.expect_verb = 0
        sctx = LookupContext(dict_condition=self._tr.dict_condition, suffix_removed=True,
                             suffix_is_s=bool(end_flags & K.FLAG_SUFX_S))
        # A SINGLE-letter vowelless stem (e.g. eu gara - 'ara' suffix -> 'g') is not a real word
        # stem; skipping the dict avoids matching single-letter *name* entries (eu 'g'->'ge'),
        # which would inject a spurious vowel (gara -> gea**a instead of gaɾa). A MULTI-letter
        # stem is looked up even if vowelless — Arabic script writes no short vowels, so the
        # consonantal stem رض ($u pronoun ه removed) is the real, vocalized dict entry RadHdH.
        has_vowel = len(stem) > 1 or any(self._tr.is_letter(ord(c), 0) for c in stem)
        sdict_ph, sdict_flags = self._dict.lookup(stem, sctx) if has_vowel else (None, None)
        if (end_type & K.SUFX_E) and not (end_flags & K.FLAG_SUFX_E_ADDED) \
                and incontext_ph and incontext_ph.strip():
            # SUFX_E ("double the vowel") rules already lengthened the stem in context (nl deze ->
            # de:z); re-translating the bare stem loses it (dez -> dEs). espeak keeps the in-context
            # match. (English re-adds an 'e' instead, so FLAG_SUFX_E_ADDED gates this off there.)
            stem_ph = incontext_ph
        elif sdict_ph:
            stem_ph = sdict_ph
        else:
            # translateword.c: the stem lookup sets dictionary_flags2; when the WHOLE word
            # carried no flags, the stem's flags are adopted (`if (dictionary_flags[0]==0)`).
            # A flags-only stem entry (en update -> $1) thus places its stress on the
            # suffix-stripped stem (updates -> ˈʌpdeɪts, not ʌpdˈeɪts) — the adopted flags are
            # passed up via _suffix_dict_flags so the final SetWordStress sees the $1.
            stem_flags = dict_flags if dict_flags else (sdict_flags or 0)
            if not dict_flags and sdict_flags:
                self._suffix_dict_flags = sdict_flags
            stem_ph, _, _ = translate_rules(
                self._tr, stem, self._mnem,
                word_flags=end_flags | K.FLAG_SUFFIX_REMOVED, dict_flags=stem_flags)
        # record the suffix's vowel count so set_word_stress runs the auto-secondary on the
        # stem only (espeak stresses the stem, then appends the suffix unstressed). Only when
        # there is a real stem — some endings span the whole word (stem empty, e.g. en
        # "house"), where the "suffix" vowels ARE the word and must keep their stress.
        # `suffix_keeps_stress` langs (eu) instead stress the whole stem+suffix word, so the
        # suffix vowels are NOT excluded (translateword.c stresses `phonemes` with the suffix in it).
        if stem_ph.strip("\"'") and not self._config.get("suffix_keeps_stress"):
            self._suffix_nvowels = sum(1 for _m, p in self._mnem.tokenize(end_ph)
                                       if p.type == phVOWEL and "nonsyllabic" not in p.flags)
        return stem_ph + end_ph

    def _split_caps_word(self, tok, words, caps_letters, first_sub):
        """Split a token at camelCase / letter-name boundaries (espeak tokenizer), appending
        (word, nospace) tuples to ``words``. ``first_sub`` marks the first sub-word of a
        FLAG_NOSPACE-joined part (hyphen-joined, or a '&'-split remainder)."""
        # smj: a doubled coda-class continuant (m f v s l r ŋ) opening the lowercase run after a
        # long-vowel letter name peels its FIRST letter onto the letter-name word as a coda — the
        # geminate straddles the word break (bA:lldaj -> bˈeː ˈɑːl ltˈɑj, dA:vva -> dˈeː ˈɑːv vˈɑ,
        # mA:ŋŋga -> ˈɛm ˈɑːŋ ŋkˈɑ). Same condition as the '&'-coda peel: the doubled consonant must
        # be in mfvslrŋ and the remainder must contain a lowercase vowel (A:jja stays whole — j∉set;
        # A:nna stays whole — n∉set; A:lln has no vowel in the spelled `lln`; A:kka -> kk is a stop).
        _peel, _peel_vowels = set("mfvslrŋ"), set("aeiouyáäoö")
        sub_first = True
        start = 0
        for j in range(1, len(tok)):
            split_here = False
            peel = ""
            if tok[j].isupper() and tok[j - 1].islower():
                if start == 0 and self.lang == "ga" and _ga_caps_prefix(tok, j):
                    continue  # Irish eclipsis/lenition prefix: hÓighe stays one word
                split_here = True
            elif caps_letters and tok[j].islower() and tok[j - 1] == ":":
                # smj: a long-vowel letter name (capital + length colon) is spelled, so it
                # breaks from a following lowercase run (bA:ldan -> "b","A:","ldan" -> be
                # a-long ltan). A bare capital keeps its lowercase run (mOnnO: -> m,Onn,O:).
                split_here = True
                rest = tok[j:]
                if (len(rest) >= 3 and rest[0] == rest[1] and rest[0] in _peel
                        and any(c in _peel_vowels for c in rest[1:])):
                    peel = rest[0]
            if split_here:
                # the peeled coda rides on the letter-name word behind a \x02 sentinel so the
                # render loop spells the letter name (A: -> ˈɑː) then appends the coda glyph as
                # its IPA (smj m/f/v/s/l/r are identity-mapped) -> ˈɑːl, mirroring the '&' coda.
                lw = tok[start:j] + ("\x02" + peel if peel else "")
                words.append((lw, first_sub and sub_first))
                sub_first = False
                start = j + len(peel)
        words.append((tok[start:], first_sub and sub_first))

    def phonemize(self, text, ipa=True, tie=None, separator=None):
        """Translate text to phonemes (word-by-word; full clause handling is P5).

        The last word carries the clause tonic stress (STRESS_IS_PRIMARY); this matches
        espeak's single-clause behavior and is what makes an isolated monosyllable like
        "the" render stressed (ðˈə). Per-word tonic placement across a real clause is P5.
        """
        # Malayalam chillu: base consonant + virama + ZWJ is the atomic chillu (a dead
        # consonant). espeak normalises the sequence to the atomic char so the la+virama rules
        # (ി (ल्K -> I) don't mis-fire, then breaks after it. Map + break: നിര്‍ഝ -> നിർ ഝ ->
        # nˈiɾ ɟʰ…; ...ില്‍ -> ...ിൽ -> …il (not …ɪl).
        for seq, atom in (("ണ്‍", "ൺ"), ("ന്‍", "ൻ"),
                          ("ര്‍", "ർ"), ("ല്‍", "ൽ"),
                          ("ള്‍", "ൾ"), ("ക്‍", "ൿ")):
            if seq in text:
                text = text.replace(seq, atom + " ")
        # normalize typographic apostrophes/primes to ' (espeak ReadClause). A remaining (plain)
        # ZWJ (U+200D) is a word break, kept so it doesn't garble any cluster. Ethiopic
        # punctuation (U+1361 wordspace .. U+1368) is a word/clause separator: without it the
        # word-final consonant rule (am: @) ል (_ -> l) can't fire (አስፍረዋል። -> …wal not …walɨ).
        _trans = {0x2019: "'", 0x00B4: "'", 0x2032: "'", 0x0092: "'", 0x200D: "‍ "}
        _trans.update({cp: " " for cp in range(0x1361, 0x1369)})
        # Myanmar (Burmese) is written without spaces; espeak segments it by isolating the asat
        # ် (U+103A) and the dot-below ့ (U+1037) as their own tokens (each translates to the
        # break phoneme _|), and treats ၊ ။ (U+104A/B) as clause punctuation. သီဟိုဠ်မှ ->
        # သီဟိုဠ ် မှ -> ðˈi1hol  mhˈa.
        for cp in (0x103A, 0x1037):
            ch = chr(cp)
            if ch in text:
                text = text.replace(ch, " " + ch + " ")
        _trans[0x104A] = " "
        _trans[0x104B] = " "
        _trans[0x1039] = " "   # Myanmar virama (stacked consonants): a plain word break
        # shn (Shan): espeak mis-classifies the tone marks ႇ/ႈ/ႉ/ႊ (U+1087-108A) as clause
        # separators, not syllable marks — it splits the syllable so the bare vowel drops
        # (ၵေႇ -> 'ၵေ'+'ႇ' -> k). force_compat reproduces this bug; the default engine keeps them.
        if self.force_compat:
            for ch in self._config.get("compat_separators", ""):
                _trans[ord(ch)] = " "
        # a '/' is a word break that is itself spoken as its character name (ca a/e -> a barra e,
        # en a/b -> a slash b), so isolate it as its own token.
        _trans[ord("/")] = " / "
        # language chars_ignore table (tr_languages.c / readclause.c IgnoreOrReplaceChar): drop or
        # replace input codepoints before tokenising. fa rewrites U+200C (ZWNJ) to '-' and drops
        # U+0640 (TATWEEL); this is espeak's real behaviour, so it applies in both modes.
        _trans.update(self._config.get("chars_ignore", {}))
        # '_' is in espeak's breaks[] table (translate.c:113), so the clause reader turns it into a
        # space (a word break) for every language. A leading '-' on the word after the break is then
        # a hyphen whose following letter sets FLAG_NOSPACE (translate.c:1224-1230): the '-' is
        # dropped and the new word glues to the previous with no space, each word independently
        # stressed (fo `eingilskmaður_og_-kona` -> aɟndʒˌɪlsmɛˈɑːʋʊɹ ɔˈœːkoːnˈa). Mark the NOSPACE
        # join with U+0001 so it survives the whitespace split below; a plain '_' is just a space.
        text = text.replace("_-", "\x01").replace("_", " ")
        text = text.translate(_trans)
        # Build the (token, nospace_join) list: whitespace is an ordinary break; a '\x01' (the
        # former '_-') breaks AND glues the following word to the previous with no space.
        raw_toks = []
        for chunk in text.split():
            for j, seg in enumerate(chunk.split("\x01")):
                seg = seg.lstrip("-") if j > 0 else seg
                if seg:
                    raw_toks.append((seg, j > 0))
        words = []
        for raw_tok, nospace_join in raw_toks:
            # a '-' at a word boundary (trailing, or leading after a non-join break) is a hyphen
            # with a space on the outside: espeak removes it without pronouncing it, and the word
            # translates exactly as if it were not there (translate.c:1309-1335 — none of the
            # internal-hyphen branches fire). fo `barna-` keeps its word-final `rn`->`dn` rule
            # (badnˈa, not bˈarna); `test-` == `test` in every language.
            if not nospace_join:
                raw_tok = raw_tok.lstrip("-")
            raw_tok = raw_tok.rstrip("-")
            if not raw_tok:
                continue
            # a '-' between two letters is a word break (espeak translate.c:1316: "'-'
            # between two letters is a hyphen, treat as a space"): Cèit-Ùna -> Cèit, Ùna.
            parts = []
            seg = 0
            for k in range(len(raw_tok)):
                if (raw_tok[k] == "-" and 0 < k < len(raw_tok) - 1
                        and raw_tok[k - 1].isalpha() and raw_tok[k + 1].isalpha()):
                    parts.append(raw_tok[seg:k])
                    seg = k + 1
            parts.append(raw_tok[seg:])
            caps_letters = self._config.get("caps_are_letters")
            for pi, tok in enumerate(parts):
                if not tok:
                    continue
                # the '_-' break glued this word to the previous (FLAG_NOSPACE) — only its first
                # sub-word carries the join; later camelCase sub-words space normally.
                join = nospace_join and pi == 0
                # split mixed/camelCase at a lowercase->uppercase boundary (espeak tokenizer):
                # mOn -> "m","On" (-> ˈɛm ˈɒn), fooBar -> "foo","Bar".
                # A hyphen-joined part (pi>0) is a separate word for stress but joins to the
                # previous with NO space (espeak FLAG_NOSPACE): Cèit-Ùna -> kʲˈɛːdʲˈuːnə.
                if caps_letters and "&" in tok:
                    # smj: '&' is a separate spelled word ("og" -> ˈɔːɡ). espeak's char tokenizer
                    # terminates the run at '&' (not alpha, not punct_within_word), emits '&' as
                    # its own word, then continues. A doubled coda-class continuant (m f v s l r ŋ)
                    # that opens a pronounceable remainder peels its first letter onto the '&' word
                    # as a FLAG_NOSPACE coda (b&mmi -> bˈeː ˈɔːɡm mˈiː, b&ŋŋi -> bˈeː ˈɔːɡŋ ŋˈiː);
                    # other clusters (nn, jj, stops, or a remainder with no lowercase vowel) stay
                    # whole (g&nna -> ɡˈeː ˈɔːɡ nnˈɑ).
                    _peel, _low_vowels = set("mfvslrŋ"), set("aeiouyáäoö")
                    for si, seg in enumerate(tok.split("&")):
                        if si > 0:
                            coda = ""
                            if (len(seg) >= 3 and seg[0] == seg[1] and seg[0] in _peel
                                    and any(c in _low_vowels for c in seg[1:])):
                                coda, seg = seg[0], seg[1:]
                            words.append(("&" + coda, False))
                        if seg:
                            self._split_caps_word(seg, words, caps_letters,
                                                  first_sub=((pi > 0 or join) and si == 0))
                    continue
                self._split_caps_word(tok, words, caps_letters, first_sub=(pi > 0 or join))
        out = []
        for i, (word, nospace) in enumerate(words):
            # tonic word carries the clause stress; tone languages (vi) reduce it to
            # secondary since the tone, not stress, carries syllable prominence.
            tonic = self._config.get("tonic_stress", 4) if i == len(words) - 1 else -1
            if (tonic >= 0 and self._config.get("u_tonic") is not None
                    and (self._dict.lookup_flags(word) & 0x8)):
                # vi: a $u function word as the clause nucleus stays SECONDARY (cho -> tʃˌɔ), unlike a
                # content word which takes the PRIMARY clause tonic (ba -> bˈaː).
                tonic = self._config.get("u_tonic")
            _wflags = self._dict.lookup_flags(word.split("\x02")[0])
            if (tonic >= 0 and len(words) > 1 and self._config.get("u_post_nuclear")
                    and (_wflags & 0x8) and not (_wflags & K.FLAG_STRESS_END)):
                # smj: a TRAILING plain-$u function word in a multi-word render is post-nuclear —
                # the clause accent already landed on a preceding (spelled letter-name / camelCase)
                # word, so the $u word keeps its NATURAL stress, not the clause primary
                # (A:ga -> ˈɑː kɑ, A:dagi -> ˈɑː tˌɑɡɪː, BeGa -> pˈiɛ kɑ). A $u word that is the
                # ONLY word is still promoted to the nucleus (ga -> kˈɑ). A $u+ word (FLAG_STRESS_END,
                # da/sij/ma) KEEPS its stress, so it still takes the clause primary (dijA:da -> tˈɑ).
                tonic = -1
            if out and not nospace:
                # a preceding empty token (a Burmese break mark: asat ်, dot ့) leaves a trailing
                # separator already; don't add a second one (espeak emits no double space). The
                # empty token itself appends "", so scan back past empties to the real last item.
                _last = next((x for x in reversed(out) if x != ""), None)
                if _last != " ":
                    out.append(" ")
            caps_stress = 0
            if self._config.get("caps_in_word") and word != word.lower():
                # Lojban: a capital marks the stressed syllable (espeak inserts ˈ before the
                # first capital, stressing the next vowel) -> stress the (nth+1) syllable.
                nv = 0
                for ch in word:
                    if ch.isupper():
                        caps_stress = nv + 1
                        break
                    if ch.lower() in "aeiouy":
                        nv += 1
            if word[:1] == "&":
                # smj '&' word ("og"): render the dict letter-name, then append any peeled coda
                # consonant as its own glyph (FLAG_NOSPACE join): '&m' -> ˈɔːɡm.
                rendered = self._render_word("&", tonic, ipa, tie, separator) + word[1:]
                out.append(rendered)
                continue
            if "\x02" in word:
                # smj long-vowel letter name with a peeled geminate coda (A:\x02l): spell the
                # letter name (A: -> ˈɑː), then append the coda consonant as its glyph -> ˈɑːl.
                lname, coda = word.split("\x02", 1)
                rendered = self._render_word(lname.lower(), tonic, ipa, tie, separator) + coda
                out.append(rendered)
                continue
            # atend_clause_final (smj): a $atend-gated letter name (O -> o:, i -> i:) only applies
            # when the word is the LAST in the clause; a non-final caps-letter token rule-translates
            # instead (dO:t -> d | O | t, the mid-clause O -> oɔ not the o: letter name). Default
            # languages keep the historical isolated-word at_end=True (one word per phonemize call).
            at_end = (not self._config.get("atend_clause_final")) or (i == len(words) - 1)
            rendered = self._render_word(word.lower(), tonic, ipa, tie, separator,
                                         caps_stress=caps_stress,
                                         all_upper=word.isupper() and any(c.isalpha() for c in word),
                                         first_upper=word[:1].isupper(), at_end=at_end)
            if (not rendered and self.lang != "en" and word.isascii()
                    and any(c.isalpha() for c in word)
                    and not getattr(self, "_textmode_empty", False)):
                # phonSWITCH (translate.c): a word unpronounceable in the current (non-Latin)
                # script is re-translated by the Latin default voice (English) and bracketed
                # with the language switch — bg/fa/ka: foot -> (en)fˈʊt(bg). A Latin-script
                # language never yields an empty translation for an alphabetic word, so the
                # empty result self-identifies the foreign word.
                en_ph = self._en_fallback()._render_word(word.lower(), tonic, ipa, tie, separator)
                if en_ph:
                    rendered = "(en)" + en_ph + "(" + self.lang + ")"
            if (not rendered and word == "း" and self.force_compat
                    and self._config.get("compat_spell_orphan_visarga")):
                # shn: a visarga း orphaned by the asat split renders empty here (it is its own
                # token, no surrounding syllable for the rules to attach it to), but espeak's
                # TranslateLetter still spells its codepoint "Myanmar letter 1038" in place. Use the
                # same in-band codepoint speller as the mid-word case. The preceding empty break
                # token (asat) already left a trailing space in `out`; drop it so the spelled run
                # joins with a single separator (espeak emits no double space).
                rendered = self._spell_codepoint_inband(ord("း"), ipa, tie, separator)
                while out and out[-1] in (" ", ""):
                    out.pop()
                if out:
                    out.append(" ")  # exactly one separator before the spelled visarga
            out.append(rendered)
        # a word-final break token (e.g. a Burmese asat ်) renders empty but leaves a trailing
        # separator space; espeak emits none, so trim it.
        result = "".join(out).rstrip(" ")
        if ipa and self._config.get("spirantize"):
            # ca/es voiced stops b/d/ɡ spirantize to β/ð/ɣ after a vowel — INCLUDING across a word
            # break, which the per-word render misses (ca a/e -> ə βˈarə ˈɛ). Within-word cases are
            # already handled by the rules, so this only patches a word-initial stop after a vowel.
            import re
            _spir = {"b": "β", "d": "ð", "g": "ɣ", "ɡ": "ɣ"}
            result = re.sub(
                r"([aeiouɛɔəɐ])( [ˈˌ]?)([bdɡg])",
                lambda m: m.group(1) + m.group(2) + _spir[m.group(3)],
                result)
            # a voiced stop after a vowel and before a liquid spirantizes too (eu aljebraiko ->
            # alxeβɾaɪko, aerodromo -> aeɾoðɾomo, ca pedra -> peðɾə); es handles this in its rules so
            # the stop is already β/ð/ɣ here, but eu/ca rules miss the pre-liquid context.
            result = re.sub(
                r"([aeiouɛɔəɐ])([bdɡg])([ɾlr])",
                lambda m: m.group(1) + _spir[m.group(2)] + m.group(3),
                result)
        if ipa and self._config.get("trill_r_not_after_stop"):
            # de r is the alveolar TRILL r only PREVOCALICALLY after a non-stop consonant or word
            # boundary (unsre -> ʊnzrə); the de 'r' program otherwise renders the tap ɾ (via CALL
            # base1/*). A stop before it (dreißig -> dɾaɪsɪç), a vowel before it (intervocalic
            # verein -> fɛɾaɪn, ChangePhoneme(R)), or a non-prevocalic position (tür -> tyːɾ) keep ɾ.
            import re as _re
            result = _re.sub(r"(?<![ptkbdɡgaɑeɛiɪoɔuʊyʏøœəɐː])ɾ(?=[ˈˌ]?[aɑeɛiɪoɔuʊyʏøœəɐ])", "r", result)
        if ipa and self._config.get("palatal_u_to_y"):
            # pinyin ü: after a palatal initial (j/q/x = j/ɕ/tɕ/tɕh) the written 'u' is /y/, and in
            # -üan the 'a' is /æ/ (juan -> jyæn, xun -> ɕyən). espyak rendered it as plain u.
            import re as _re
            result = _re.sub(r"([jɕ]h?[ˈˌ]?)ua", r"\1yæ", result)
            result = _re.sub(r"([jɕ]h?[ˈˌ]?)u", r"\1y", result)
        if ipa and self._config.get("coda_trill_r"):
            # bn র is the tap ɾ prevocalically and word-finally; before a consonant (syllable coda)
            # it is the trill r (ধর্ম -> dʰɔrmɔ). Promote ɾ -> r only when a consonant follows.
            import re as _re
            result = _re.sub(r"ɾ(?=[ˈˌ]?[mnŋɲsʃʒhvzflrɾɽjw])", "r", result)
        if ipa and self._config.get("geminate_r_trill"):
            # fo: a geminate rr renders r + approximant ɹ (the first segment of the cluster trills);
            # espyak gives ɹɹ, oracle rɹ. Promote the first ɹ of an ɹɹ cluster to the trill r.
            import re as _re
            result = _re.sub(r"ɹ(?=ɹ)", "r", result)
        if ipa and self._config.get("word_final_r_approximant"):
            # fo: a word-final trill `r` after a vowel weakens to the approximant `ɹ` only when the
            # NEXT word begins with a vowel (liaison): `ognar og` -> ɔɡnˈaɹ ɔˈœː, but `ognar gøta`
            # keeps the trill (ɔɡnˈar ɡ2ːdˈa). Clause-final `r` (end of string) also keeps the trill.
            # Per-word rendering can't see the boundary, so patch it in the joined multi-word output.
            import re as _re
            _V = "aɑeɛiɪoɔuʊyʏøœəɐ"
            result = _re.sub(r"([%s]ː?)r(?= [ˈˌ]?[%s])" % (_V, _V), r"\1ɹ", result)
        return result

    # cmn switch-segment vowel set + the unstressed-reduction map espeak's cmn render applies to the
    # English phonemes of an (en)…(cmn) word switch. A non-final word de-stresses and its vowels
    # reduce; the rhotic ɑː ("R" name) collapses to a syllabic r (no tone follows it).
    _CMN_EN_VOWELS = ("aɪ", "aʊ", "eɪ", "oʊ", "ɔɪ", "ɪə", "eə", "ʊə",
                      "ɑː", "ɔː", "uː", "iː", "ɜː",
                      "ə", "ɪ", "ʊ", "e", "æ", "ʌ", "ɒ", "ɔ", "ɑ", "a", "i", "u", "o", "ɛ", "ɐ")

    def _cmn_switch_segment_tone5(self, inner):
        """cmn render-time tone post-pass over an (en)…(cmn) WORD switch — applied ONLY to the
        switched English segment, never to native cmn words.

        espeak re-translates a pinyin $text token (雄 -> ``xiong2``) whose first Latin letter trips
        ``_^_EN``: the whole token switches to English (``kʃˈəŋ tˈuː``). cmn's render-time post-pass
        then runs ACROSS the (en)…(cmn) boundary (translate.c: source-language stress/tone over the
        switched phonemes) — exactly the shn cross-boundary effect of d921a45 but over a word switch:
        the NON-FINAL English words de-stress and their vowels reduce (dʒɪˈɒŋ -> dʒɪ5ə5ŋ: stress
        dropped, ɒ->ə; ˈɑː -> r), the FINAL word keeps its primary stress, and cmn's default tone 5
        is appended to every English vowel (tˈuː -> tˈuː5, wˈɒn -> wˈɒ5n -> kʃə5ŋtˈuː5).
        """
        words = inner.split(" ")
        out = []
        for wi, w in enumerate(words):
            out.append(self._cmn_tone5_word(w, final=(wi == len(words) - 1)))
        return "".join(out)

    def _cmn_tone5_word(self, w, final):
        vowels = self._CMN_EN_VOWELS
        res = []
        i = 0
        n = len(w)
        while i < n:
            ch = w[i]
            if ch in ("ˈ", "ˌ"):
                if final:
                    res.append(ch)  # the final word keeps its stress mark
                i += 1
                continue
            # longest-match a vowel nucleus at this position
            matched = None
            for v in vowels:
                if w.startswith(v, i):
                    matched = v
                    break
            if matched is None:
                res.append(ch)
                i += 1
                continue
            i += len(matched)
            # length mark belongs to the nucleus (tone goes AFTER it: tˈuː -> tˈuː5)
            length = ""
            if i < n and w[i] == "ː":
                length = "ː"
                i += 1
            if not final and matched == "ɑː":
                # the rhotic "R" name reduces to a syllabic r with NO tone digit (ˈɑː -> r)
                res.append("r")
                continue
            if not final and matched == "ɒ":
                matched = "ə"  # an unstressed ɒ reduces to schwa (dʒɪˈɒŋ -> dʒɪ5ə5ŋ)
            res.append(matched + length + "5")
        return "".join(res)

    _EN_FALLBACK = None

    @classmethod
    def _en_fallback(cls):
        if cls._EN_FALLBACK is None:
            cls._EN_FALLBACK = G2P("en")
        return cls._EN_FALLBACK

    def _stress_number_words(self, ph):
        """espeak stresses number words. Some languages' _list fragments already encode stress
        (en f'aIv, es T'inko, de 'fynf) AND deliberately leave connectors unstressed (en _and,
        _point); others omit stress entirely (fr sE~k, fa pandZ -> need sˈɛ̃k / pˈandʒ). Only when
        the WHOLE number result is stress-free do we add word stress to each ||-separated word — so
        a language whose data encodes stress (including its unstressed point/and) is never touched."""
        if any(c in "'%,=" for c in ph):
            return ph
        return "||".join(
            set_word_stress(self._tr, w, self._mnem, tonic=4) if w else w
            for w in ph.split("||"))

    def _render_word(self, word, tonic, ipa, tie, separator, caps_stress=0, all_upper=False,
                     first_upper=False, at_end=True):
        from espyak.numbers import ORDINAL_SUFFIXES, translate_number, translate_ordinal
        self._u_out_str = None  # set by translate_word for reduced-$u clause-accent words
        num_flags = self._config.get("numbers", K.NUM_HUNDRED_AND)
        dsep = "," if (num_flags & K.NUM_DECIMAL_COMMA) else "."
        # NB: str.isdigit() is True for superscripts/other Unicode digits ('²') that int() rejects,
        # so require ASCII before routing to the (int-based) number path — '²' falls through to
        # normal translation instead of crashing.
        def _dig(s):
            return s.isascii() and s.isdigit()
        if not word.isascii():
            # native-script decimal digits (fa ۱, ar ٠, Devanagari ०, ...) -> ASCII so they route to
            # the number path (۱ -> jek). unicodedata.decimal rejects superscripts/subscripts ('²'),
            # so those still fall through to normal translation as intended.
            word = "".join(
                str(unicodedata.decimal(c)) if unicodedata.decimal(c, None) is not None else c
                for c in word)
        if (len(word) > 2 and word[-2:] in ORDINAL_SUFFIXES and _dig(word[:-2])):
            ph = translate_ordinal(self._dict, word[:-2], word[-2:], flags=num_flags)
            if ph:
                return self._render_phonemes(ph, ipa, tie, separator)
        if word and (_dig(word) or (_dig(word.replace(dsep, "", 1))
                                    and dsep in word and not word.startswith(dsep)
                                    and not word.endswith(dsep))):
            ph = translate_number(self._dict, word, flags=num_flags, decimal_sep=dsep)
            if ph:
                ph = self._stress_number_words(ph)
                return self._render_phonemes(ph, ipa, tie, separator)
        if any(c.isdigit() for c in word) and any(c.isalpha() for c in word):
            # a mixed digit/letter token that is neither a pure number nor an ordinal (handled above)
            # is split at the digit<->letter boundaries and each run spoken separately (en co2 -> ko
            # two, h2o -> h two o, or ୧ম -> eko mo).
            _parts, _cur, _cd = [], "", None
            for _c in word:
                _is = _c.isdigit()
                if _cur and _is != _cd:
                    _parts.append(_cur)
                    _cur = ""
                _cur += _c
                _cd = _is
            if _cur:
                _parts.append(_cur)
            if len(_parts) > 1:
                _r = [self._render_word(p, tonic, ipa, tie, separator) for p in _parts]
                return " ".join(x for x in _r if x)
        ph = self.translate_word(word, tonic=tonic, caps_stress=caps_stress, all_upper=all_upper,
                                 first_upper=first_upper, at_end=at_end)
        if getattr(self, "_spell_prerendered", False):
            # name-first spell-word (_spell_letters_named) already produced final IPA with its own
            # (lang)…(orig) switches spliced in; return it verbatim (do not re-encode as phonemes).
            return ph
        if ph.startswith("_^_"):
            # foreign word: re-translate in the named language and wrap (lang)...(orig)
            _payload = ph[3:].split("|", 1)
            target = _payload[0].lower().strip()
            # a `_^_<lang>|<text>` marker (alphabets[] $text block-switch, pa software) carries the
            # replacement text the switched language must translate, not the original token.
            switch_word = _payload[1] if len(_payload) > 1 else word
            tg = self._switch_g2p(target)
            if tg is not None:
                inner = tg._render_word(switch_word, tonic, ipa, tie, separator)
                if (ipa and target == "en"
                        and self._config.get("switch_segment_tone5") and " " in inner):
                    inner = self._cmn_switch_segment_tone5(inner)
                # TranslateLetter (translateword.c): an isolated letter from a foreign alphabet that
                # the current language neither owns (our_alphabet) nor aliases (alt_alphabet) and that
                # isn't AL_DONT_NAME is preceded by the alphabet's spoken name (it cirillico: а ->
                # tʃɪrˈillɪko(ru)ˈɑ(it)). Italian names Cyrillic but not Greek (AL_DONT_NAME); the name
                # phonemes come from the language's own `_cyr` *_list entry.
                prefix = self._foreign_alphabet_name(word, ipa, tie, separator)
                # the return tag is the phoneme-table language (ms uses `phonemes id` -> (id))
                return "%s(%s)%s(%s)" % (prefix, target, inner, self._ph_table_name)
            ph = ""
        if not ph.strip():
            named = self._name_and_render_foreign_letter(word, tonic, ipa, tie, separator)
            if named is not None:
                return named
        return self._render_phonemes(ph, ipa, tie, separator)

    def _name_and_render_foreign_letter(self, word, tonic, ipa, tie, separator):
        """TranslateLetter single-letter-word path (translateword.c:786, dictionary.c:2252).

        A whole-word that is ONE character of a foreign AL_WORDS alphabet block which the current
        language cannot translate is NOT switched as a word (that needs >1 char, dictionary.c:2270
        `any_alpha > 1`); instead espeak spells it as an isolated letter: it announces the block's
        alphabet name, then renders the letter in the block's language. The current language has no
        local `_xx` name for the block, so the name is spoken by the default English voice
        ((en)hˈɪndi(gu)), and the letter render in the switch language is appended (xˈə).

        gu ख़ (nukta-combined ખ઼ -> Devanagari U+0959): (en)hˈɪndi(gu)xˈə.
        """
        from espyak import language_data
        # the .replace table already ran inside translate_word; reapply it to see the real char(s).
        w = _apply_replacements(getattr(self._rules, "replacements", None), word.lower())
        if len(w) != 1:
            return None
        cp = ord(w)
        entry = language_data.alphabet_from_char(cp)
        if entry is None:
            return None
        lo, hi, name_key, switch_lang, flags = entry
        my_off = self._config.get("letter_bits_offset", 0)
        if (switch_lang is None or switch_lang == self.lang
                or not (flags & language_data.AL_WORDS)
                or (flags & language_data.AL_DONT_NAME)
                or lo == my_off):
            return None
        tg = self._switch_g2p(switch_lang)
        if tg is None:
            return None
        inner = tg._render_word(w, tonic, ipa, tie, separator)
        if not inner.strip():
            return None
        # the block's alphabet name: the source language's own `_xx` *_list entry if present,
        # otherwise the English name spoken by the default (en) voice ((en)hˈɪndi(gu)).
        local_ph, _ = self._dict.lookup(name_key, LookupContext())
        if local_ph and local_ph.strip():
            name = self._render_phonemes(
                set_word_stress(self._tr, local_ph, self._mnem, tonic=4), ipa, tie, separator)
            prefix = name
        else:
            # Lookup(translator3, alphabet->name, ...): the English voice's *_list entry keyed by
            # the alphabet NAME (`_hi` -> h'Indi = "hindi"), not the literal letters of the key.
            en = self._en_fallback()
            en_ph, _ = en._dict.lookup(name_key, LookupContext())
            if not en_ph or not en_ph.strip():
                return None
            en_name = en._render_phonemes(
                set_word_stress(en._tr, en_ph, en._mnem, tonic=4), ipa, tie, separator)
            if not en_name.strip():
                return None
            prefix = "(en)%s(%s)" % (en_name, self._ph_table_name)
        return prefix + inner

    # Foreign alphabets named before an isolated letter (TranslateLetter): map the unicode block to
    # the *_list mnemonic key holding the spoken name. Only blocks WITHOUT AL_DONT_NAME are listed,
    # since espeak skips the name for the others (it Greek = AL_DONT_NAME -> α stays ˈalfa).
    _ALPHABET_NAME_KEY = ((0x400, 0x52f, "_cyr"),)

    def _foreign_alphabet_name(self, word, ipa, tie, separator):
        """The rendered alphabet-name prefix for an all-foreign-script word, or "". Gated to
        languages whose config opts in (name_foreign_alphabet) and that own a matching *_list
        name entry; Italian names Cyrillic letters (а -> tʃɪrˈillɪko(ru)…)."""
        if not self._config.get("name_foreign_alphabet") or not word:
            return ""
        c = ord(word[0])
        key = next((k for lo, hi, k in self._ALPHABET_NAME_KEY if lo <= c <= hi), None)
        if key is None:
            return ""
        # only when the WHOLE token is in that one foreign block (a mixed token is handled elsewhere)
        if not all(lo <= ord(ch) <= hi for ch in word for lo, hi, k in self._ALPHABET_NAME_KEY
                   if k == key):
            return ""
        ctx = LookupContext(dict_condition=self._tr.dict_condition)
        name_ph, _ = self._dict.lookup(key, ctx)
        if not name_ph:
            return ""
        # render with the dict-entry flag reset: the name is its own little word
        self._from_dict = False
        return self._render_phonemes(name_ph, ipa=ipa, tie=tie, separator=separator)

    _SPELL_CACHE = {}

    def _spell_codepoint_inband(self, cp, ipa, tie, separator):
        """Port of TranslateLetter (translateword.c:786) for an untranslatable codepoint.

        Builds the in-band phonSWITCH spelling on a SHARED phoneme list: the alphabet name
        ``_my`` is rendered with the default (en) voice's phoneme table, the literal "letter"
        (l'et@) and the four hex-digit names come from the source language, and the source
        language's render-time post-passes (shn's force-tone-1 default + ``_shn_long_vowel_tone_copy``)
        run ACROSS the en/shn boundary so the English consonants pick up shn's tone copy
        (mjˈɑː -> mjˈɑː1, A@ -> ɑːɑː). The ``(en)…(shn)…`` switch markers are emitted by the
        IPA writer exactly as espeak's GetTranslatedPhonemeString does for a phonSWITCH phoneme.

        The result is invariant for a given codepoint (independent of surrounding context), so
        it is cached per ``(cp, ipa, tie, separator)``.
        """
        ckey = (self.lang, cp, ipa, tie, separator)
        cached = G2P._SPELL_CACHE.get(ckey)
        if cached is not None:
            return cached
        en = self._en_fallback()
        # the alphabet name (_my) is spoken by the default English voice; the hex-letter
        # fallback (a-f) is the English `hex_letters` mnemonic read with the SOURCE table.
        segs = [("en", en, "mj'A:nmA@")]                         # (en) "Myanmar"
        segs.append((self._ph_table_name, self, "l'et@"))         # (shn) "letter"
        for ch in format(cp, "x"):
            if ch.isdigit():
                ph, _ = self._dict.lookup("_" + ch, LookupContext())
                segs.append((self._ph_table_name, self, ph or ("_" + ch)))
            else:
                # a-f: read the English hex-letter mnemonic with the SOURCE phoneme table (no switch)
                segs.append((self._ph_table_name, self, _HEX_LETTERS[ch]))
        out = []
        cur = self._ph_table_name
        for tag, g2p, mnem in segs:
            text = self._render_spelled_segment(g2p, mnem, ipa, tie, separator)
            if tag != cur:
                out.append("(%s)" % tag)
                cur = tag
            out.append(text)
        if cur != self._ph_table_name:
            out.append("(%s)" % self._ph_table_name)
        result = "".join(out)
        G2P._SPELL_CACHE[ckey] = result
        return result

    def _render_spelled_segment(self, g2p, mnem, ipa, tie, separator):
        """Render one spelled letter-name segment, applying THIS (source) language's tone
        post-passes (the cross-boundary effect) but using ``g2p``'s phoneme table for the
        segment's own phonemes (the in-band switch)."""
        table = g2p.phoneme_table
        stressed = set_word_stress(g2p._tr, mnem, g2p._mnem, tonic=4)
        plist = encode_phoneme_string(stressed, table)
        g2p._interp._translation_given = False
        g2p._interp.run(plist)
        _double_long_consonants(plist)
        # the source language's tone normalization runs across the switch: every toneless
        # nucleus gets the default tone 1, explicit tones are kept. Unlike a normal shn word
        # this is NOT the force_compat tone-1 discard (these are pre-built letter names whose
        # tones espeak keeps) — so insert_default but force_default=False.
        if self._config.get("tone_language"):
            _normalize_tones(plist, self.phoneme_table, insert_default=True, force_default=False)
        if self.force_compat and self._config.get("compat_long_vowel_tone"):
            _shn_long_vowel_tone_copy(plist)
        out = render_phoneme_list(plist, table, ipa=ipa, tie=tie, separator=separator)
        # espeak's order for a lengthened toned letter name is vowel + length + tone
        # (si:2 -> sˈiː2, d'i: -> dˈiː1); the renderer's _reorder_tones puts the tone right after
        # the vowel (before the length ː), so swap a tone-digit immediately before a ː back after it.
        return _re_tone_after_length(out)

    def _render_phonemes(self, ph, ipa, tie, separator):
        if _SPELL_CP_OPEN in ph:
            # the phoneme string carries one or more in-band codepoint-spelling sentinels
            # (\x01<hex>\x02): a Myanmar character the rules could not pronounce. espeak spells
            # it in place on the shared buffer with a phonSWITCH; the spelled run is its own
            # spoken letter sequence, set off from the surrounding phonemes by a space on each
            # side (espeak's SetSpellingStress pause / word boundary). Split, render the ordinary
            # phonemes around it, and splice the cached spelling between.
            import re as _re
            parts = _re.split(r"\x01([0-9a-f]+)\x02", ph)
            out = []
            for k, part in enumerate(parts):
                if k % 2 == 1:
                    spelled = self._spell_codepoint_inband(int(part, 16), ipa, tie, separator)
                    out.append(" " + spelled + " ")
                elif part:
                    out.append(self._render_phonemes(part, ipa, tie, separator))
            return "".join(out).strip(" ")
        plist = encode_phoneme_string(ph, self.phoneme_table)
        if getattr(self, "_from_dict", False) and not self._config.get("reduce_dict_vowels"):
            # dict-entry phonemes: skip stress-condition reductions (espeak's SFLAG_DICTIONARY)
            for e in plist:
                e.dict_no_reduce = True
        reg = self._config.get("regression", 0)
        if reg:
            set_regressive_voicing(plist, self.phoneme_table, reg)
        self._interp._translation_given = getattr(self, "_from_dict", False)
        self._interp.run(plist)  # P1b: context-dependent phoneme programs
        out_str = getattr(self, "_u_out_str", None)
        if out_str is not None:
            # reduced-$u word: programs ran on the un-tonic levels (vowels laxed correctly);
            # overlay the clause-accent stress marks from the tonic version onto the vowels in
            # order. out_str and ph come from the same phoneme string (only the stress differs), so
            # their vowels align 1:1 by position — advance the index for EVERY vowel, including ones
            # a program deleted (indic_schwa ChangePhoneme(NULL)), so a deletion doesn't shift the
            # overlay (hi आपको: schwa deleted -> oː still gets the tonic primary, not the schwa level).
            out_levels = [e.stresslevel for e in encode_phoneme_string(out_str, self.phoneme_table)
                          if e.ph.type == phVOWEL]
            vi = 0
            for e in plist:
                if e.ph.type == phVOWEL:
                    if not e.deleted and vi < len(out_levels):
                        e.stresslevel = out_levels[vi]
                    vi += 1
            # sl additionally shortens these program-unstressed vowels: drop the rule-emitted
            # length marker after a vowel (sva -> sʋˈa not sʋˈaː). smj keeps length (the laxed
            # vowel stays long: gis -> kˈɪːs), so this is gated separately from the de-stress.
            if self._config.get("drop_u_length"):
                for k in range(1, len(plist)):
                    if plist[k].ph.mnemonic == ":" and plist[k - 1].ph.type == phVOWEL:
                        plist[k].deleted = True
        _double_long_consonants(plist, double_rfx_stop=bool(self._config.get("double_rfx_stop")))
        if self._config.get("tone_language") or self._config.get("tone_collapse"):
            _normalize_tones(plist, self.phoneme_table,
                             insert_default=bool(self._config.get("tone_language")),
                             clause_final_tone=self._config.get("clause_final_tone"),
                             force_default=bool(self.force_compat
                                                and self._config.get("compat_force_tone1")))
        if self.force_compat and self._config.get("compat_long_vowel_tone"):
            _shn_long_vowel_tone_copy(plist)
        # a PRIORITY stress (level 5, from a '' mark in the rules) dominates the word: the other
        # primaries reduce to secondary (da debutant d?eb'y''?&nt: y primary + ant priority ->
        # dʔebˌyˈant). Words with only ordinary primaries (eremitage 4,4) keep them all.
        if any(e.ph.type == phVOWEL and e.stresslevel == 5 for e in plist):
            for e in plist:
                if e.ph.type == phVOWEL and e.stresslevel == 4:
                    e.stresslevel = 3
        result = render_phoneme_list(plist, self.phoneme_table,
                                     ipa=ipa, tie=tie, separator=separator)
        if getattr(self, "_neutral_tone", False):
            # cmn neutral tone is unstressed: drop the one tonic mark espeak omits.
            result = result.replace("ˈ" if ipa else "'", "", 1)
        if ipa and (self._config.get("stress_flags", 0) & K.S_FIRST_PRIMARY):
            # ca S_FIRST_PRIMARY: within ONE multi-word dict entry (a || expansion rendered here as a
            # single token) only the first primary survives; later parts reduce to secondary (ccoo ->
            # cumisiˈonz uβɾˌeɾəs). Applied per-token so separately-rendered tokens — digit splits
            # (co2 -> kˈɔ ðˈos) and '/' splits (a/e -> ə βˈarə ˈɛ) — each keep their own primary.
            first = result.find("ˈ")
            if first >= 0:
                result = result[:first + 1] + result[first + 1:].replace("ˈ", "ˌ")
        return result

    _SWITCH_CACHE = {}

    def _switch_g2p(self, lang):
        """Cached G2P for a language switched to via `_^_<lang>` (foreign words)."""
        g = G2P._SWITCH_CACHE.get(lang)
        if g is None and lang not in G2P._SWITCH_CACHE:
            try:
                g = G2P(lang)
            except Exception:
                g = None
            G2P._SWITCH_CACHE[lang] = g
        return g
