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
    remove_ending, _apply_replacements,
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
from espyak.render import PhonemeListEntry

_DOUBLE_TYPES = frozenset((phFRICATIVE, phVFRICATIVE, phNASAL, phLIQUID))


def _normalize_tones(plist, table, insert_default=True):
    """Tone language (vi): every syllable carries a tone immediately after its vowel.
    Move an existing tone (digit phoneme) to right after the vowel, or insert the default
    tone '1' (phonDEFAULTTONE) if the syllable has none. With ``insert_default=False`` (my:
    Burmese) only the per-syllable tone collapse runs — toneless syllables stay toneless."""
    default = table.get("1")
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
            if tones:
                for t in reversed(tones[:-1]):
                    plist.pop(t)  # drop the earlier (default) tones
                tone_at = tones[-1] - (len(tones) - 1)
                if tone_at != i + 1:
                    plist.insert(i + 1, plist.pop(tone_at))  # move kept tone after the vowel
            elif insert_default and default is not None:
                plist.insert(i + 1, PhonemeListEntry(default))
            i += 1  # skip the tone we just placed
        i += 1


def _double_long_consonants(plist):
    """phonemelist.c: a length phoneme (`:`) after a fricative/nasal/liquid lengthens by
    doubling the consonant (it mm/ll/ss); after a DIPHTHONG it repeats the diphthong
    (af e@: -> iəiə, o@: -> ʊəʊə) — espeak renders a lengthened diphthong by writing it twice,
    not vowel+ː (which stays for monophthongs: A: -> ɑː)."""
    for i in range(1, len(plist)):
        e = plist[i]
        if e.deleted or e.ph.mnemonic != ":":
            continue
        prev = plist[i - 1].ph
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


class G2P:
    """Grapheme-to-phoneme translator for one language."""

    def __init__(self, lang="en"):
        self.lang = lang
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
        # tr/he/...); espeak compiles it after _list, so later entries win ties.
        self._dict = DictList.load(data_paths.list_path(lang), data_paths.listx_path(lang),
                                   data_paths.extra_path(lang))
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

        def key(rule):
            return ([code.get(m, 0xffff) for m, _ in tok(rule.phonemes)], rule.match_str)
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

    def translate_word(self, word, tonic=-1, caps_stress=0):
        """Translate a single lowercase word to its mnemonic phoneme string.

        Pipeline: dictionary `_list` lookup -> (fallback) letter-to-sound rules ->
        stress assignment. `tonic` (>=0) forces the word's main stress to that level,
        used for the tonic (clause-stressed) word. `caps_stress` (>0) forces the main
        stress onto that syllable (Lojban LOPT_CAPS_IN_WORD: a capital marks stress).
        """
        ctx = LookupContext(
            first_upper=word[:1].isupper(),
            all_upper=word.isupper() and any(c.isalpha() for c in word),
            dict_condition=self._tr.dict_condition,
        )
        self._tr.expect_verb = 0
        self._suffix_nvowels = 0  # set by the suffix path; excluded from auto-secondary
        self._from_dict = False   # set by _translate_core when phonemes come from a dict entry
        self._spelled = False     # set by _translate_core for a $abbrev spelled-out word
        self._textmode_empty = False  # a $text->spell word that loops to '' (mto english)
        ph, flags = self._translate_core(word.lower(), ctx)
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

    def _translate_core(self, word, ctx, word_flags=0):
        """Dictionary lookup, else rules with prefix/suffix removal+retranslation.

        Returns (phonemes, dict_flags). Handles one prefix (recursing on the stem) or
        one suffix per call (TranslateWord3's prefix/suffix branches)."""
        if self._config.get("decompose_hangul"):
            word = unicodedata.normalize("NFC", word)
        # espeak's SubstituteChar (.replace table) normalises the source BEFORE the dict lookup,
        # not just for rule matching: da/sv/no map ä->æ, ö->ø, ü->y so a foreign accented letter
        # is pronounced as its native equivalent and never reaches its `$accent` dict entry, while
        # letters with no mapping (é) still hit `$accent` and get spelled.
        word = _apply_replacements(getattr(self._rules, "replacements", None), word)
        dict_ph, dict_flags = self._dict.lookup(word, ctx)
        flags = dict_flags or 0
        accent_entry = not dict_ph and getattr(self._dict, "_last_accent", False)
        if dict_ph:
            hangul = self._config.get("decompose_hangul")
            nfc_ph = unicodedata.normalize("NFC", dict_ph) if hangul else dict_ph
            if flags & K.FLAG_TEXTMODE:
                # $text: the entry value is text to re-translate (ta "tamil" -> தமிழ்,
                # Korean sandhi respellings) — feed it back through the rules.
                word = nfc_ph
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
        if self._config.get("decompose_hangul") and any("가" <= c <= "힣" for c in word):
            # syllable -> conjoining jamo (with fillers) for the rules (already NFC above).
            word = _decompose_hangul(word)
        self._tr._spell_word = False
        ph, end_type, end_ph = translate_rules(
            self._tr, word, self._mnem, word_flags=word_flags, want_endings=True,
            dict_flags=flags)
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
            # prefix: remove it, translate the remaining stem, prepend the prefix phonemes
            prefix_len = end_type & 0x3f
            rest = word[prefix_len:]
            rctx = LookupContext(dict_condition=self._tr.dict_condition)
            rest_ph, _ = self._translate_core(rest, rctx)
            return end_ph + rest_ph, flags
        if end_type and (end_type & K.SUFX_Q):
            # "lookup stem in *_list without the suffix" (it `_S1q`): if the stem is a
            # dictionary entry use it, otherwise keep the in-context rule output (don't
            # re-run the rules on the stem — that would re-expose a geminate to the
            # word-end rule, palla->pal, and lose intervocalic context, casa s->z).
            stem, _ = remove_ending(self._tr, word, end_type)
            sctx = LookupContext(dict_condition=self._tr.dict_condition, suffix_removed=True)
            sdict_ph, _ = self._dict.lookup(stem.strip(), sctx)
            return (sdict_ph + end_ph if sdict_ph else ph + end_ph), flags
        if end_type and not (end_type & K.SUFX_P):
            return self._translate_with_suffix(word, end_type, end_ph, flags, ph), flags
        # $accent entry ($accent in *_list): spell the letter as base + accent name(s). espeak
        # spells these (found==0); the letters a language pronounces instead are normalised away
        # by .replace above (da ä->æ) before they ever reach their $accent entry, so no extra
        # guard is needed here. Also covers the rules-give-nothing fallback.
        if accent_entry or (not ph.strip() and len(word) == 1 and not word.isascii()):
            acc = self._spell_accented_letter(word.lstrip("_"))
            if acc:
                return acc, 0
        return ph, flags

    def _spell_letters(self, word):
        """FLAG_SPELLWORD: re-translate the word as individual letters, each its OWN primary
        word (mto amsterdam -> ˈa ˈm̩ s tʰ ˈe ɾ dˈe ˈa ˈm̩): the letter's SOUND via the rules,
        falling back to its spelled NAME only when the rules give nothing (mto 'd' -> de)."""
        parts = []
        for ch in word:
            ph, _, _ = translate_rules(self._tr, ch, self._mnem)
            if not ph.strip():
                ph = self._lookup_letter(ch, False, False)
            if ph:
                parts.append(set_word_stress(self._tr, ph, self._mnem, tonic=4))
        return "||".join(parts)

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
        names = []
        bn = self._lookup_letter(base, at_end=False, first=True)
        if bn:
            names.append(bn)
        for mk in marks:
            key = _ACCENT_NAMES.get(ord(mk))
            if key:
                ph, _ = self._dict.lookup(key, LookupContext())
                if ph:
                    names.append(ph)
        if len(names) < 2:
            return None
        return self._join_spelled(names)

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
        sctx = LookupContext(dict_condition=self._tr.dict_condition, suffix_removed=True)
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
            stem_ph, _, _ = translate_rules(
                self._tr, stem, self._mnem,
                word_flags=end_flags | K.FLAG_SUFFIX_REMOVED, dict_flags=dict_flags)
        # record the suffix's vowel count so set_word_stress runs the auto-secondary on the
        # stem only (espeak stresses the stem, then appends the suffix unstressed). Only when
        # there is a real stem — some endings span the whole word (stem empty, e.g. en
        # "house"), where the "suffix" vowels ARE the word and must keep their stress.
        if stem_ph.strip("\"'"):
            self._suffix_nvowels = sum(1 for _m, p in self._mnem.tokenize(end_ph)
                                       if p.type == phVOWEL and "nonsyllabic" not in p.flags)
        return stem_ph + end_ph

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
        text = text.translate(_trans)
        words = []
        for raw_tok in text.split():
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
            for pi, tok in enumerate(parts):
                if not tok:
                    continue
                # split mixed/camelCase at a lowercase->uppercase boundary (espeak tokenizer):
                # mOn -> "m","On" (-> ˈɛm ˈɒn), fooBar -> "foo","Bar".
                # A hyphen-joined part (pi>0) is a separate word for stress but joins to the
                # previous with NO space (espeak FLAG_NOSPACE): Cèit-Ùna -> kʲˈɛːdʲˈuːnə.
                sub_first = True
                start = 0
                for j in range(1, len(tok)):
                    if tok[j].isupper() and tok[j - 1].islower():
                        if start == 0 and self.lang == "ga" and _ga_caps_prefix(tok, j):
                            continue  # Irish eclipsis/lenition prefix: hÓighe stays one word
                        words.append((tok[start:j], pi > 0 and sub_first))
                        sub_first = False
                        start = j
                words.append((tok[start:], pi > 0 and sub_first))
        out = []
        for i, (word, nospace) in enumerate(words):
            # tonic word carries the clause stress; tone languages (vi) reduce it to
            # secondary since the tone, not stress, carries syllable prominence.
            tonic = self._config.get("tonic_stress", 4) if i == len(words) - 1 else -1
            if out and not nospace:
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
            rendered = self._render_word(word.lower(), tonic, ipa, tie, separator,
                                         caps_stress=caps_stress)
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
            out.append(rendered)
        # a word-final break token (e.g. a Burmese asat ်) renders empty but leaves a trailing
        # separator space; espeak emits none, so trim it.
        return "".join(out).rstrip(" ")

    _EN_FALLBACK = None

    @classmethod
    def _en_fallback(cls):
        if cls._EN_FALLBACK is None:
            cls._EN_FALLBACK = G2P("en")
        return cls._EN_FALLBACK

    def _render_word(self, word, tonic, ipa, tie, separator, caps_stress=0):
        from espyak.numbers import ORDINAL_SUFFIXES, translate_number, translate_ordinal
        self._u_out_str = None  # set by translate_word for reduced-$u clause-accent words
        num_flags = self._config.get("numbers", K.NUM_HUNDRED_AND)
        dsep = "," if (num_flags & K.NUM_DECIMAL_COMMA) else "."
        # NB: str.isdigit() is True for superscripts/other Unicode digits ('²') that int() rejects,
        # so require ASCII before routing to the (int-based) number path — '²' falls through to
        # normal translation instead of crashing.
        def _dig(s):
            return s.isascii() and s.isdigit()
        if (len(word) > 2 and word[-2:] in ORDINAL_SUFFIXES and _dig(word[:-2])):
            ph = translate_ordinal(self._dict, word[:-2], word[-2:], flags=num_flags)
            if ph:
                return self._render_phonemes(ph, ipa, tie, separator)
        if word and (_dig(word) or (_dig(word.replace(dsep, "", 1))
                                    and dsep in word and not word.startswith(dsep)
                                    and not word.endswith(dsep))):
            ph = translate_number(self._dict, word, flags=num_flags, decimal_sep=dsep)
            if ph:
                return self._render_phonemes(ph, ipa, tie, separator)
        ph = self.translate_word(word, tonic=tonic, caps_stress=caps_stress)
        if ph.startswith("_^_"):
            # foreign word: re-translate in the named language and wrap (lang)...(orig)
            target = ph[3:].split("|")[0].lower().strip()
            tg = self._switch_g2p(target)
            if tg is not None:
                inner = tg._render_word(word, tonic, ipa, tie, separator)
                return "(%s)%s(%s)" % (target, inner, self.lang)
            ph = ""
        return self._render_phonemes(ph, ipa, tie, separator)

    def _render_phonemes(self, ph, ipa, tie, separator):
        plist = encode_phoneme_string(ph, self.phoneme_table)
        if getattr(self, "_from_dict", False) and not self._config.get("reduce_dict_vowels"):
            # dict-entry phonemes: skip stress-condition reductions (espeak's SFLAG_DICTIONARY)
            for e in plist:
                e.dict_no_reduce = True
        reg = self._config.get("regression", 0)
        if reg:
            set_regressive_voicing(plist, self.phoneme_table, reg)
        self._interp.run(plist)  # P1b: context-dependent phoneme programs
        out_str = getattr(self, "_u_out_str", None)
        if out_str is not None:
            # reduced-$u word: programs ran on the un-tonic levels (vowels laxed correctly);
            # overlay the clause-accent stress marks from the tonic version onto the vowels
            # in order (laxing is ChangePhoneme, so the vowel count is preserved).
            out_levels = [e.stresslevel for e in encode_phoneme_string(out_str, self.phoneme_table)
                          if e.ph.type == phVOWEL]
            vi = 0
            for e in plist:
                if e.ph.type == phVOWEL and not e.deleted:
                    if vi < len(out_levels):
                        e.stresslevel = out_levels[vi]
                    vi += 1
            # sl additionally shortens these program-unstressed vowels: drop the rule-emitted
            # length marker after a vowel (sva -> sʋˈa not sʋˈaː). smj keeps length (the laxed
            # vowel stays long: gis -> kˈɪːs), so this is gated separately from the de-stress.
            if self._config.get("drop_u_length"):
                for k in range(1, len(plist)):
                    if plist[k].ph.mnemonic == ":" and plist[k - 1].ph.type == phVOWEL:
                        plist[k].deleted = True
        _double_long_consonants(plist)
        if self._config.get("tone_language") or self._config.get("tone_collapse"):
            _normalize_tones(plist, self.phoneme_table,
                             insert_default=bool(self._config.get("tone_language")))
        return render_phoneme_list(plist, self.phoneme_table,
                                   ipa=ipa, tie=tie, separator=separator)

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
