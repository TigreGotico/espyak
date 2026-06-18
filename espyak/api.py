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
    remove_ending,
)
from espyak import constants as K
import unicodedata

# combining-mark codepoint -> espeak accent-name dictionary key (accents_tab, numbers.c)
_ACCENT_NAMES = {
    0x0301: "_acu", 0x0300: "_grv", 0x0302: "_cir", 0x0303: "_tld",
    0x0308: "_dia", 0x0327: "_ced", 0x030C: "_hac", 0x0306: "_brv",
    0x0307: "_dot", 0x0304: "_mcn", 0x0328: "_ogo", 0x030A: "_rng",
    0x0338: "_stk", 0x0337: "_stk", 0x030B: "_ac2", 0x0331: "_bar",
    0x0309: "_hok",
}
from espyak import language_data
from espyak.phoneme_program import Interpreter


class G2P:
    """Grapheme-to-phoneme translator for one language."""

    def __init__(self, lang="en", force_compat=True):
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
        self._rules = RuleSet.compile_file(data_paths.rules_path(lang))
        self._tr = Translator(phsource=self._phsource, config=self._config)
        self._tr.rules = self._rules
        self._dict = DictList.load(data_paths.list_path(lang), data_paths.extra_path(lang))

    def _resolve_phoneme_table(self, lang):
        # voice file `phonemes <table>` line, else the lang code, else base1/base.
        candidates = []
        if self._voice:
            try:
                with open(self._voice, encoding="utf-8") as fh:
                    for line in fh:
                        parts = line.split()
                        if parts and parts[0] == "phonemes":
                            candidates.append(parts[1])
                            break
            except OSError:
                pass
        candidates += [lang, "base1", "base"]
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

    def translate_word(self, word, tonic=-1):
        """Translate a single lowercase word to its mnemonic phoneme string.

        Pipeline: dictionary `_list` lookup -> (fallback) letter-to-sound rules ->
        stress assignment. `tonic` (>=0) forces the word's main stress to that level,
        used for the tonic (clause-stressed) word. (Clause/number handling and phoneme
        programs are still being wired; see the repo plan.)
        """
        ctx = LookupContext(
            first_upper=word[:1].isupper(),
            all_upper=word.isupper() and any(c.isalpha() for c in word),
            dict_condition=self._tr.dict_condition,
        )
        self._tr.expect_verb = 0
        ph, flags = self._translate_core(word.lower(), ctx)
        if "||" in ph:
            # multi-word dictionary entry (e.g. es "w" -> uβe||doβle): stress each
            # sub-word separately, preserving the word break for the renderer.
            parts = ph.split("||")
            last = len(parts) - 1
            stressed = [
                set_word_stress(self._tr, p, self._mnem,
                                dict_flags=(flags if i == last else 0),
                                tonic=(tonic if i == last else 4))
                for i, p in enumerate(parts)
            ]
            return "||".join(stressed)
        return set_word_stress(self._tr, ph, self._mnem, dict_flags=flags, tonic=tonic)

    def _translate_core(self, word, ctx, word_flags=0):
        """Dictionary lookup, else rules with prefix/suffix removal+retranslation.

        Returns (phonemes, dict_flags). Handles one prefix (recursing on the stem) or
        one suffix per call (TranslateWord3's prefix/suffix branches)."""
        dict_ph, dict_flags = self._dict.lookup(word, ctx)
        flags = dict_flags or 0
        if dict_ph:
            return dict_ph, flags
        if dict_flags is not None and (flags & K.FLAG_ABBREV):
            # $abbrev with no pronunciation -> spell out as individual letter names
            return self._spell_word(word), 0
        if not dict_ph and len(word) == 1 and not word.isascii():
            acc = self._spell_accented_letter(word)
            if acc:
                return acc, 0
        ph, end_type, end_ph = translate_rules(
            self._tr, word, self._mnem, word_flags=word_flags, want_endings=True,
            dict_flags=flags)
        if end_type and (end_type & K.SUFX_P) and not (word_flags & K.FLAG_NO_PREFIX):
            # prefix: remove it, translate the remaining stem, prepend the prefix phonemes
            prefix_len = end_type & 0x3f
            rest = word[prefix_len:]
            rctx = LookupContext(dict_condition=self._tr.dict_condition)
            rest_ph, _ = self._translate_core(rest, rctx)
            return end_ph + rest_ph, flags
        if end_type and not (end_type & K.SUFX_P):
            return self._translate_with_suffix(word, end_type, end_ph, flags), flags
        return ph, flags

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

    def _lookup_letter(self, ch, at_end, first):
        """Look up a single letter's name: the spelling entry `_X`, else the plain
        letter `X`, else letter-to-sound rules (LookupLetter)."""
        ctx = LookupContext(dict_condition=self._tr.dict_condition,
                            at_end=at_end, first_word=first)
        for key in ("_" + ch, ch):
            ph, _ = self._dict.lookup(key, ctx)
            if ph:
                return ph
        ph, _, _ = translate_rules(self._tr, ch, self._mnem)
        return ph

    def _translate_with_suffix(self, word, end_type, end_ph, dict_flags=0):
        """Remove a standard suffix, (re)translate the stem, append the suffix phonemes.

        Port of the suffix branch of TranslateWord3 (single-suffix; SUFX_M multiple
        suffixes and SUFX_Q/SUFX_T variants are not yet handled). The word's dict $alt
        flags are carried into the stem retranslation (canonical keeps $alt3)."""
        stem, end_flags = remove_ending(self._tr, word, end_type)
        stem = stem.strip()
        self._tr.expect_verb = 0
        sctx = LookupContext(dict_condition=self._tr.dict_condition, suffix_removed=True)
        sdict_ph, sdict_flags = self._dict.lookup(stem, sctx)
        if sdict_ph:
            stem_ph = sdict_ph
        else:
            stem_ph, _, _ = translate_rules(
                self._tr, stem, self._mnem,
                word_flags=end_flags | K.FLAG_SUFFIX_REMOVED, dict_flags=dict_flags)
        return stem_ph + end_ph

    def phonemize(self, text, ipa=True, tie=None, separator=None):
        """Translate text to phonemes (word-by-word; full clause handling is P5).

        The last word carries the clause tonic stress (STRESS_IS_PRIMARY); this matches
        espeak's single-clause behavior and is what makes an isolated monosyllable like
        "the" render stressed (ðˈə). Per-word tonic placement across a real clause is P5.
        """
        words = text.split()
        out = []
        for i, word in enumerate(words):
            tonic = 4 if i == len(words) - 1 else -1  # STRESS_IS_PRIMARY on tonic word
            ph = self.translate_word(word.lower(), tonic=tonic)
            plist = encode_phoneme_string(ph, self.phoneme_table)
            self._interp.run(plist)  # P1b: context-dependent phoneme programs
            out.append(render_phoneme_list(plist, self.phoneme_table,
                                           ipa=ipa, tie=tie, separator=separator))
        return " ".join(out)
