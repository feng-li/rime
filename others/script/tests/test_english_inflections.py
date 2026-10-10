"""Offline tests: python3 -m unittest discover -s others/script/tests."""

import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "build_english_inflections.py"
spec = importlib.util.spec_from_file_location("build_english_inflections", SCRIPT)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class InflectionBuilderTests(unittest.TestCase):
    def test_only_confirmed_verbs_and_known_bases(self):
        vocabulary = {"force", "forced", "forcing", "forces", "cat", "cats", "fake", "faked"}
        forms = builder.verb_forms([
            "force V: forced | forcing | forces",
            "cat N: cats",
            "fake V?: faked",
            "Invent V: invented | inventing | invents",
            "missing V: forced",
        ], vocabulary)
        self.assertEqual(forms, {"force": ["forced", "forcing", "forces"]})

    def test_reject_uncertain_and_rare_forms(self):
        vocabulary = {"read", "reading", "reads", "readding", "stop", "stopped", "stoped", "stopping", "stoping", "stops"}
        forms = builder.verb_forms([
            "read V: read | reading, readding 2 | reads",
            "stop V: stopped, stoped!< 1 | stopping, stoping!< 1 | stops",
        ], vocabulary)
        self.assertEqual(forms["read"], ["reading", "reads"])
        self.assertEqual(forms["stop"], ["stopped", "stopping", "stops"])

    def test_variants_senses_and_irregulars(self):
        vocabulary = {"run", "ran", "running", "runs", "hang", "hung", "hanged", "hanging", "hangs", "learn", "learned", "learnt", "learning", "learns"}
        forms = builder.verb_forms([
            "run V: ran | run | running | runs",
            "hang V: hung, hanged {execute} | hanging | hangs",
            "learn V: learned, learnt 1 | learning | learns",
        ], vocabulary)
        self.assertEqual(forms["run"], ["ran", "running", "runs"])
        self.assertEqual(forms["hang"], ["hung", "hanged", "hanging", "hangs"])
        self.assertEqual(forms["learn"], ["learned", "learnt", "learning", "learns"])

    def test_source_dictionary_excludes_comments_aliases_and_names(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "en.dict.yaml"
            source.write_text("---\nname: en\n...\nforce\tforce\n# fake\tfake\nJanuary\tJan\nAaron\tAaron\nrun\trun\n", encoding="utf-8")
            self.assertEqual(builder.dictionary_words([source]), {"force", "run"})

    def test_attested_new_forms_have_spelling_entries(self):
        vocabulary = {"force", "forced", "forcing", "forces", "panic"}
        forms = builder.verb_forms(["force V: forced | forcing | forces", "panic V: panicked | panicking | panics"], vocabulary)
        self.assertEqual(forms["panic"], ["panicked", "panicking", "panics"])
        words = builder.render_words(forms, vocabulary, "test-hash")
        self.assertIn("panicking\tpanicking\n", words)
        self.assertNotIn("forcing\tforcing\n", words)
        self.assertNotIn("panic\tpanic\n", words)

    def test_deduplication_and_stable_order(self):
        vocabulary = {"force", "forced", "forcing", "forces", "go", "went"}
        forms = builder.verb_forms([
            "go V: went, went",
            "force V: forced | forcing | forces",
            "force V: forced | forcing | forces",
        ], vocabulary)
        self.assertEqual(list(forms), ["force", "go"])
        rendered = builder.render(forms, "test-hash")
        self.assertEqual(rendered.count("forced\tforce\t"), 1)
        self.assertIn("went\tgo\t0.001\n", rendered)
        self.assertIn("SHA256: test-hash", rendered)

    def test_bundled_data_matches_vocabulary_and_examples(self):
        repo = SCRIPT.parents[2]
        path = repo / "en_dicts/english_inflections.dict.yaml"
        vocabulary = builder.dictionary_words([repo / "en_dicts/en.dict.yaml", repo / "en_dicts/en_ext.dict.yaml"])
        new_words = builder.dictionary_words([repo / "en_dicts/english_inflection_words.dict.yaml"])
        combined = vocabulary | new_words
        body = path.read_text(encoding="utf-8").split("\n...\n", 1)[1]
        rows = [line.split("\t") for line in body.splitlines() if line]
        pairs = {(code, text) for text, code, weight in rows}
        self.assertEqual(len(pairs), len(rows))
        self.assertTrue(all(code in vocabulary and text in combined and code != text for code, text in pairs))
        self.assertEqual(new_words, {word for _, word in pairs} - vocabulary)
        for base, words in {"force": ["forced", "forcing", "forces"], "run": ["ran", "running", "runs"],
                            "go": ["went", "gone", "going", "goes"], "study": ["studied", "studying", "studies"],
                            "stop": ["stopped", "stopping", "stops"], "make": ["made", "making", "makes"]}.items():
            for word in words:
                self.assertIn((base, word), pairs)
        self.assertNotIn(("force", "forceing"), pairs)
        self.assertNotIn(("go", "goed"), pairs)


if __name__ == "__main__":
    unittest.main()
