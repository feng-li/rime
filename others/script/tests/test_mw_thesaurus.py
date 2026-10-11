"""Synthetic HTML/MDX tests; no licensed dictionary text or live Rime writes."""

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "extract_mw_thesaurus.py"
spec = importlib.util.spec_from_file_location("extract_mw_thesaurus", SCRIPT)
extractor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extractor)


def sense(number, gloss, synonyms, other=""):
    return (f'<div class="muj"><span class="n6n">{number}</span><span class="xsx">'
            f'<span class="ltr">{gloss}</span><span class="zz0">example-not-a-word</span>'
            f'<div><div class="tec"><span>synonyms</span></div>{synonyms}</div>{other}</span></div>')


def section(word, part, body):
    return (f'<div class="blr"><div class="jk6"><div class="iye">{word}</div>'
            f'<div class="eyx">{part}</div></div>{body}</div>')


SAMPLE = '<div class="m3s">' + section("sample", "noun", sense(
    1, 'an <a href="entry://illustration">illustration</a>',
    '<a href="entry://example">example</a>, <span>specimen</span>, sample',
    '<div><div class="a3d"><span>related words</span></div>prototype</div>'
    '<div><div class="ycv"><span>near antonyms</span></div>exception</div>'
    '<div><div class="poy"><span>antonyms</span></div>whole</div>'
    '<div><div class="foa"><span>phrases</span></div>for instance</div>')) + '</div>'


class ParserTests(unittest.TestCase):
    def test_relations_are_separate_and_definition_and_example_links_do_not_leak(self):
        groups = extractor.parse_entry("sample", SAMPLE)
        self.assertEqual(len(groups), 1)
        group = groups[0]
        self.assertEqual(group["headword"], "sample")
        self.assertEqual(group["part_of_speech"], "noun")
        self.assertEqual(group["sense"], "1")
        self.assertEqual(group["definition"], "an illustration")
        self.assertEqual(group["synonyms"], ["example", "specimen", "sample"])
        self.assertEqual(group["related_words"], ["prototype"])
        self.assertEqual(group["near_antonyms"], ["exception"])
        self.assertEqual(group["antonyms"], ["whole"])
        self.assertEqual(group["phrases"], ["for instance"])
        table = {}
        extractor.add_synonyms(table, groups)
        self.assertEqual(table, {"sample": ["example", "specimen"]})

    def test_parts_of_speech_and_separate_sub_senses_remain_distinct(self):
        html = '<div class="m3s">' + section("sample", "noun", sense(1, "noun sense", "specimen"))
        html += section("sample", "verb", sense(1, "verb sense", "try") + sense(2, "another verb sense", "test"))
        html += '</div>'
        groups = extractor.parse_entry("sample", html)
        self.assertEqual([(g["part_of_speech"], g["sense"], g["synonyms"]) for g in groups],
                         [("noun", "1", ["specimen"]), ("verb", "1", ["try"]), ("verb", "2", ["test"])])
        self.assertEqual(groups[2]["definition"], "another verb sense")

    def test_dictionary_fallback_is_explicit_and_never_replaces_dedicated_section(self):
        dictionary = ('<div class="iye">sample</div><div class="eyx">noun</div>'
                      '<dl><dt class="ltp">Synonyms:</dt><dd>specimen, example</dd></dl>'
                      '<dl><dt class="jcz">Antonyms:</dt><dd>whole</dd></dl>')
        self.assertEqual(extractor.parse_entry("sample", dictionary), [])
        groups = extractor.parse_entry("sample", dictionary, True)
        self.assertEqual(groups[0]["synonyms"], ["specimen", "example"])
        self.assertEqual(groups[0]["source_section"], "dictionary_synonyms")
        self.assertEqual(extractor.parse_entry("sample", dictionary + SAMPLE, True),
                         extractor.parse_entry("sample", SAMPLE))

    def test_annotation_variants_entities_unicode_phrases_and_superscripts(self):
        body = '<div class="m3s">' + section('sample<sup>1</sup>', 'noun', sense(
            1, 'a thing', 'color (also colour), glad (often very glad),'
            '<a href="entry://role">rôle</a>, well-founded, rock &amp; roll,'
            'test<sup>2</sup><span class="bld">(chiefly British)</span>, rule 3')) + '</div>'
        words = extractor.parse_entry("sample", body)[0]["synonyms"]
        self.assertEqual(words, ["color", "colour", "glad", "rôle", "well-founded",
                                 "rock & roll", "test", "rule 3"])

    def test_single_quotes_multiple_classes_void_tags_and_nul_tail(self):
        body = SAMPLE.replace('class="m3s"', "id='th' class='extra m3s'")
        body = body.replace("example</a>", "example<img src='x'/></a>")
        groups = extractor.parse_entry("sample", body + '\x00' + SAMPLE)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["synonyms"], ["example", "specimen", "sample"])

    def test_phrasal_particles_never_become_bare_single_word_synonyms(self):
        words = extractor.word_list('snuff (out), die (away or down or out), '
                                    'clean (up), decrease, root [out], color (also colour)')
        self.assertEqual(words, ['snuff (out)', 'die (away or down or out)',
                                 'clean (up)', 'decrease', 'root [out]', 'color', 'colour'])
        data, _ = extractor.lua_data({'abolish': words}, 'synthetic')
        self.assertNotIn('"snuff"', data)
        self.assertNotIn('"die"', data)
        self.assertNotIn('"root"', data)

    def test_usage_metadata_does_not_leak_into_synonyms_or_split_notes(self):
        body = '<div class="m3s">' + section('sample', 'noun', sense(
            1, 'a thing', 'specimen, example<span class="bld"><span>(</span>'
            '<em>slang, chiefly British</em><span>)</span></span>, '
            'model<span class="bld">(formal)</span>')) + '</div>'
        group = extractor.parse_entry('sample', body, with_usage=True)[0]
        self.assertEqual(group['synonyms'], ['specimen', 'example', 'model'])
        self.assertEqual(group['synonym_terms'], [
            {'text': 'specimen', 'labels': []},
            {'text': 'example', 'labels': ['(slang, chiefly British)']},
            {'text': 'model', 'labels': ['(formal)']}])

    def test_unexpected_label_is_a_visible_error_not_a_false_synonym_list(self):
        with self.assertRaisesRegex(ValueError, "Unexpected thesaurus label"):
            extractor.parse_entry("sample", SAMPLE.replace('<span>synonyms</span>', '<span>antonyms</span>'))

    def test_lua_table_keeps_all_eligible_words_without_annotations_or_aliases(self):
        data, count = extractor.lua_data({"sample": ["Example", "specimen", "test", "instance", "well-founded"],
                                          "ice cream": ["dessert"], "go": ["try"]}, "test-sha")
        self.assertEqual(count, 1)
        self.assertIn('["sample"] = {"example", "specimen", "test", "instance"}', data)
        self.assertNotIn("well-founded", data)
        self.assertNotIn("ice cream", data)
        self.assertIn("test-sha", data)


class ExtractionTests(unittest.TestCase):
    def dependencies(self, records, declared=None):
        class FakeMDX:
            header = {b"Title": b"Synthetic &amp; Dictionary", b"Encoding": b"UTF-8"}
            def __init__(self, path): pass
            def __len__(self): return declared if declared is not None else len(records)
            def items(self): return iter(records)
        reader = types.ModuleType("mdict_utils.base.readmdict")
        reader.MDX = FakeMDX
        progress = types.ModuleType("tqdm")
        progress.tqdm = lambda rows, **kwargs: rows
        self.enterContext(patch.dict(sys.modules, {
            "mdict_utils": types.ModuleType("mdict_utils"),
            "mdict_utils.base": types.ModuleType("mdict_utils.base"),
            "mdict_utils.base.readmdict": reader, "tqdm": progress,
        }))
        self.enterContext(patch.object(extractor.importlib.metadata, "version", return_value="test"))

    def test_complete_private_export_provenance_redirects_and_optional_lua(self):
        self.dependencies([(b"sample", SAMPLE.encode()), (b"Sample", b"@@@LINK=sample\r\n"),
                           (b"sampler", b"@@@LINK=sample")])
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.mdx"
            source.write_bytes(b"synthetic-mdx")
            output = Path(directory) / "export"
            manifest = extractor.extract(source, output, rime_lua=True, progress=False)
            self.assertEqual(manifest["source"]["sha256"], hashlib.sha256(b"synthetic-mdx").hexdigest())
            self.assertEqual(manifest["source"]["title"], "Synthetic & Dictionary")
            self.assertEqual(manifest["counts"]["records_read"], 3)
            self.assertEqual(manifest["counts"]["redirect_records"], 2)
            self.assertEqual(json.loads((output / "synonyms.json").read_text()),
                             {"sample": ["example", "specimen"]})
            self.assertEqual(json.loads((output / "aliases.json").read_text())["sampler"], ["sample"])
            self.assertTrue((output / "english_synonyms_data.lua").exists())
            self.assertEqual(source.read_bytes(), b"synthetic-mdx")
            self.assertEqual(output.stat().st_mode & 0o777, 0o700)
            self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in output.iterdir()))
            with self.assertRaisesRegex(ValueError, "already exists"):
                extractor.extract(source, output, progress=False)

    def test_incomplete_mdx_is_not_published_and_temporary_output_is_cleaned(self):
        self.dependencies([(b"sample", SAMPLE.encode())], declared=2)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.mdx"
            source.write_bytes(b"synthetic-mdx")
            output = Path(directory) / "export"
            with self.assertRaisesRegex(ValueError, "incomplete export"):
                extractor.extract(source, output, progress=False)
            self.assertFalse(output.exists())
            self.assertEqual(list(Path(directory).iterdir()), [source])

    def test_wrong_layout_is_not_published(self):
        self.dependencies([(b"sample", b'<div>ordinary definition</div>')])
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.mdx"
            source.write_bytes(b"synthetic-mdx")
            with self.assertRaisesRegex(ValueError, "No recognized"):
                extractor.extract(source, Path(directory) / "export", progress=False)
            self.assertEqual(list(Path(directory).iterdir()), [source])


if __name__ == "__main__":
    unittest.main()
