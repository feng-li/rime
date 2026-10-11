"""Synthetic academic-profile tests; no private dictionary text or live writes."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('review_mw_synonyms', SCRIPTS / 'review_mw_synonyms.py')
reviewer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reviewer)


class ReviewTests(unittest.TestCase):
    def test_every_row_screened_and_only_source_attested_candidates_kept(self):
        raw = {'sample': ['model', 'specimen', 'oddity'], 'remove': ['unusual']}
        eligible = {('sample', 'model'), ('sample', 'specimen'), ('remove', 'unusual')}
        table, audit, counts = reviewer.filter_table(raw, {'sample': 5, 'remove': 6}, eligible,
            {}, {'model'}, {'entries': {'sample': ['specimen', 'model']}})
        self.assertEqual(table, {'sample': ['specimen', 'model']})
        self.assertEqual(len(audit), 2)
        self.assertEqual(audit[0]['line'], 5)
        self.assertEqual(audit[1]['reasons'], ['outside_common_or_reviewed_academic_vocabulary'])
        self.assertEqual(sum(map(len, table.values())) + len(audit), sum(map(len, raw.values())))

    def test_usage_and_phrase_errors_cannot_be_overridden_by_manual_policy(self):
        raw = {'sample': ['model']}
        with self.assertRaisesRegex(ValueError, 'unmarked intact'):
            reviewer.filter_table(raw, {'sample': 5}, set(), {}, {'model'},
                                  {'entries': {'sample': ['model']}})
        with self.assertRaisesRegex(ValueError, 'original direct synonym'):
            reviewer.filter_table(raw, {'sample': 5}, {('sample', 'model')}, {}, {'model'},
                                  {'entries': {'sample': ['unattested']}})

    def test_unmarked_intact_evidence_wins_over_other_marked_senses(self):
        raw = {'sample': ['model', 'specimen']}
        table, audit, _ = reviewer.filter_table(raw, {'sample': 5}, {('sample', 'model')},
            {('sample', 'model'): {'marked_nonacademic_usage'},
             ('sample', 'specimen'): {'parenthesized_or_bracketed_expression'}},
            {'model', 'specimen'}, {'entries': {}})
        self.assertEqual(table, {'sample': ['model']})
        self.assertEqual(audit[0]['reasons'], ['parenthesized_or_bracketed_expression'])

    def test_empty_reviewed_list_withholds_ambiguous_entry(self):
        table, audit, _ = reviewer.filter_table({'sample': ['model']}, {'sample': 5},
            {('sample', 'model')}, {}, {'model'}, {'entries': {'sample': []}})
        self.assertEqual(table, {})
        self.assertEqual(audit[0]['reasons'], ['manual_academic_sense_review'])

    def test_usage_labels_are_not_confused_with_words_in_normal_definitions(self):
        self.assertTrue(reviewer.group_usage({'part_of_speech': 'noun, slang', 'definition': 'a thing'}))
        self.assertTrue(reviewer.group_usage({'part_of_speech': 'adjective', 'definition': 'archaic a thing'}))
        self.assertFalse(reviewer.group_usage({'part_of_speech': 'adjective', 'definition': 'being rare or unusual'}))
        self.assertFalse(reviewer.group_usage({'part_of_speech': 'verb', 'definition': 'to make obsolete'}))

    def test_lua_reader_rejects_duplicates_self_matches_and_executable_content(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'data.lua'
            text = reviewer.render({'sample': ['model', 'specimen']}, 'mdx', 'raw')
            path.write_text(text)
            self.assertEqual(reviewer.read_lua_table(path)[0], {'sample': ['model', 'specimen']})
            for bad in [text.replace('"model"', '"sample"'),
                        text.replace('"model"', '"two words"'),
                        text.replace('"specimen"', '"model"'),
                        text.replace('return {', 'os.execute("false"); return {'),
                        text.replace('  ["sample"]', '  ["sample"] = {"model"},\n  ["sample"]')]:
                path.write_text(bad)
                with self.assertRaises(ValueError):
                    reviewer.read_lua_table(path)

    def test_complete_private_export_audit_permissions_and_no_overwrite(self):
        record = ('<div class="m3s"><div class="iye">sample</div><div class="eyx">noun</div>'
                  '<div class="muj"><span class="n6n">1</span><span class="xsx">'
                  '<span class="ltr">a thing</span><div><div class="tec">synonyms</div>'
                  'model, specimen<span class="bld">(slang)</span>, snuff (out)</div>'
                  '</span></div></div>')
        class FakeMDX:
            def __init__(self, path): pass
            def __len__(self): return 1
            def items(self): return iter([(b'sample', record.encode())])
        reader = types.ModuleType('mdict_utils.base.readmdict')
        reader.MDX = FakeMDX
        progress = types.ModuleType('tqdm')
        progress.tqdm = lambda rows, **kwargs: rows
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.mdx'
            source.write_bytes(b'synthetic-mdx')
            raw = root / 'raw'
            raw.mkdir()
            (raw / 'manifest.json').write_text(json.dumps({'source': {
                'path': str(source), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}}))
            (raw / 'english_synonyms_data.lua').write_text(reviewer.render(
                {'sample': ['model', 'specimen', 'snuff']}, 'mdx', 'raw'))
            policy = root / 'policy.json'
            policy.write_text(json.dumps({'entries': {}}))
            dictionary = root / 'vocab.yaml'
            dictionary.write_text('...\nmodel\tmodel\nspecimen\tspecimen\nsnuff\tsnuff\n')
            with patch.dict(sys.modules, {'mdict_utils': types.ModuleType('mdict_utils'),
                'mdict_utils.base': types.ModuleType('mdict_utils.base'),
                'mdict_utils.base.readmdict': reader, 'tqdm': progress}), \
                 patch.object(reviewer.importlib.metadata, 'version', return_value='synthetic'):
                output = root / 'academic'
                result = reviewer.review(raw, output, policy, [dictionary], progress=False)
                self.assertEqual(result['counts']['raw_pairs'], 3)
                self.assertEqual(result['counts']['retained_pairs'], 1)
                self.assertEqual(result['counts']['removed_pairs'], 2)
                self.assertEqual(reviewer.read_lua_table(output / 'english_synonyms_data.lua')[0], {'sample': ['model']})
                audit = [json.loads(line) for line in (output / 'removed.jsonl').read_text().splitlines()]
                self.assertEqual(audit[0]['reasons'], ['marked_nonacademic_usage'])
                self.assertEqual(audit[1]['reasons'], ['parenthesized_or_bracketed_expression'])
                self.assertEqual(output.stat().st_mode & 0o777, 0o700)
                self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in output.iterdir()))
                self.assertEqual(reviewer.read_lua_table(raw / 'english_synonyms_data.lua')[0]['sample'], ['model', 'specimen', 'snuff'])
                with self.assertRaisesRegex(ValueError, 'new private'):
                    reviewer.review(raw, output, policy, [dictionary], progress=False)


if __name__ == '__main__':
    unittest.main()
