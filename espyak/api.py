"""Public entrypoint for espyak.

Mirrors ``espeak-ng -q --ipa -v <lang>``. The translation pipeline (rule compiler →
matcher → stress → render) is built up across phases; this module wires the pieces
together and exposes a stable surface.
"""
from espyak import data_paths
from espyak.phoneme_tab import get_source
from espyak.render import render_phoneme_list, encode_phoneme_string
from espyak.rule_compiler import RuleSet
from espyak.dictionary import Translator, translate_rules, set_word_stress, MnemIndex


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
        # rule engine (letter-to-sound). Loaded lazily per language.
        self._rules = RuleSet.compile_file(data_paths.rules_path(lang))
        self._tr = Translator(phsource=self._phsource)
        self._tr.rules = self._rules

    def _resolve_phoneme_table(self, lang):
        # voice file `phonemes <table>` line, else the lang code, else 'base1'
        if self._voice:
            try:
                with open(self._voice, encoding="utf-8") as fh:
                    for line in fh:
                        parts = line.split()
                        if parts and parts[0] == "phonemes":
                            return parts[1]
            except OSError:
                pass
        if self._phsource.table(lang):
            return lang
        return "base1"

    @property
    def phoneme_table(self):
        return self._phsource.table(self._ph_table_name)

    def render(self, phoneme_string, ipa=True, tie=None, separator=None):
        """Render a raw espeak phoneme mnemonic string (as produced by the rules, or as
        given inside ``[[...]]``) to IPA or Kirshenbaum output.

        This is the output half of the pipeline, usable on its own.
        """
        plist = encode_phoneme_string(phoneme_string, self.phoneme_table)
        return render_phoneme_list(
            plist, self.phoneme_table, ipa=ipa, tie=tie, separator=separator
        )

    def translate_word(self, word):
        """Translate a single lowercase word to its mnemonic phoneme string.

        Pipeline: letter-to-sound rules -> stress assignment. (Dictionary `_list`
        lookup, clause/number handling, and phoneme programs are still being wired;
        see the repo plan.)
        """
        ph = translate_rules(self._tr, word, self._mnem)
        ph = set_word_stress(self._tr, ph, self._mnem)
        return ph

    def phonemize(self, text, ipa=True, tie=None, separator=None):
        """Translate text to phonemes (word-by-word; full clause handling is P5)."""
        out = []
        for word in text.split():
            ph = self.translate_word(word.lower())
            plist = encode_phoneme_string(ph, self.phoneme_table)
            out.append(render_phoneme_list(plist, self.phoneme_table,
                                           ipa=ipa, tie=tie, separator=separator))
        return " ".join(out)
