"""Offline synonym data and Lua regressions; never open live user dictionaries."""

import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest

import test_english_fuzzy as fuzzy_tests

SCRIPT = Path(__file__).resolve().parents[1] / "build_english_synonyms.py"
sys.path.insert(0, str(SCRIPT.parent))
spec = importlib.util.spec_from_file_location("build_english_synonyms", SCRIPT)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
REPO = SCRIPT.parents[2]
WORDNET_TABLE = REPO / "en_dicts/wordnet_synonyms.lua"


class SynonymBuilderTests(unittest.TestCase):
    def metadata(self, words, definition='a general meaning', pointers=()):
        return {'words': words, 'definition': definition, 'pointers': pointers}

    def test_usage_domain_pointer_scope_and_nonusage_relations(self):
        nouns = {'1': self.metadata(['colloquialism']), '2': self.metadata(['science']),
                 '3': self.metadata(['formality']), '4': self.metadata(['general', 'slang'])}
        record = self.metadata(['word', 'variant'], pointers=[
            (';u', '1', 'n', '0201'), (';c', '1', 'n', '0000'),
            (';u', '2', 'n', '0000'), (';u', '3', 'n', '0000')])
        reasons = builder.usage_rejections(record, nouns)
        self.assertEqual(dict(reasons), {'variant': {'marked_usage_domain'}})
        record['pointers'] = [(';u', '4', 'n', '0002')]
        self.assertEqual(dict(builder.usage_rejections(record, nouns)),
                         {None: {'marked_usage_domain'}})

    def test_gloss_scope_and_examples_do_not_ban_unmarked_formal_words(self):
        record = self.metadata(['whole', 'wholly'],
            "to a complete degree (`whole' is often used informally for `wholly')",
            [(';u', '1', 'n', '0000')])
        reasons = builder.usage_rejections(record, {'1': self.metadata(['colloquialism'])})
        self.assertNotIn(None, reasons)
        self.assertIn('whole', reasons)
        self.assertNotIn('wholly', reasons)
        self.assertEqual(dict(builder.usage_rejections(self.metadata(
            ['obscure', 'old'], 'a word describing an archaic building'), {})), {})
        parsed = builder.synset_metadata([
            '00000001 00 a 02 clear(a) 0 plain 0 001 ;u 00000002 n 0201 | '
            'readily understood; "the word is informal"'])['00000001']
        self.assertEqual(parsed['words'], ['clear', 'plain'])
        self.assertEqual(parsed['pointers'], [(';u', '00000002', 'n', '0201')])
        self.assertEqual(parsed['definition'], 'readily understood')

    def test_clean_before_cap_and_only_direct_selected_pos_choices(self):
        indexes = {part: {} for part in builder.PARTS}
        synsets = {part: {} for part in builder.PARTS}
        metadata = {part: {} for part in builder.PARTS}
        indexes['adj'] = {'quick': ['1', '2']}
        indexes['noun'] = {'quick': ['4']}
        synsets['adj'] = {'1': ['quick', 'slangword', 'casualword', 'rarespelling'],
                          '2': ['quick', 'fast', 'speedy', 'swift']}
        synsets['noun'] = {'4': ['quick', 'heart']}
        metadata['adj'] = {'1': self.metadata(synsets['adj']['1'], '(slang) a rapid person'),
                           '2': self.metadata(synsets['adj']['2'])}
        metadata['noun'] = {'4': self.metadata(synsets['noun']['4'])}
        words = {'quick', 'slangword', 'casualword', 'rarespelling', 'fast', 'speedy', 'swift', 'heart'}
        totals = {('quick', 'adj'): 10}
        clean, audit = builder.formal_table(indexes, synsets, metadata, totals, words, {'entries': {}})
        self.assertEqual(clean, {'quick': ['fast', 'speedy', 'swift']})
        self.assertEqual(len(audit), 3)
        clean, _ = builder.formal_table(indexes, synsets, metadata, totals, words,
                                       {'entries': {'quick': ['swift', 'fast']}})
        self.assertEqual(clean, {'quick': ['swift', 'fast']})
        for choices in [['slangword'], ['heart'], ['unattested']]:
            with self.assertRaisesRegex(ValueError, 'unmarked same-synset'):
                builder.formal_table(indexes, synsets, metadata, totals, words,
                                     {'entries': {'quick': choices}})
        clean, _ = builder.formal_table(indexes, synsets, metadata, totals, words,
                                       {'entries': {'quick': []}})
        self.assertEqual(clean, {})

    def test_unmarked_occurrence_and_reviewed_formal_exception(self):
        indexes = {part: {} for part in builder.PARTS}
        synsets = {part: {} for part in builder.PARTS}
        metadata = {part: {} for part in builder.PARTS}
        indexes['verb'] = {'support': ['1', '2']}
        synsets['verb'] = {'1': ['support', 'corroborate'], '2': ['support', 'corroborate']}
        metadata['verb'] = {'1': self.metadata(synsets['verb']['1'], '(archaic) an old sense'),
                            '2': self.metadata(synsets['verb']['2'])}
        clean, _ = builder.formal_table(indexes, synsets, metadata, {}, {'support'},
            {'entries': {'support': ['corroborate']}})
        self.assertEqual(clean, {'support': ['corroborate']})

    def test_index_offsets_skip_headers_and_filter_unknown_words(self):
        entries = builder.index_entries([
            "  1 Copyright header",
            "quick a 2 2 & + 2 1 00000001 00000002",
            "unknown n 1 0 1 0 00000003",
        ], {"quick"})
        self.assertEqual(entries, {"quick": ["00000001", "00000002"]})

    def test_synsets_strip_adjective_markers_not_compounds_or_names(self):
        words = builder.synset_words([
            "  1 Copyright header",
            "00000001 00 a 04 ready(p) 0 agile(a) 0 at_once 0 French 0 000 | gloss",
        ])
        self.assertEqual(words["00000001"], ["ready", "agile", "at_once", "French"])

    def test_word_frequencies_handle_adjective_satellites_and_parts_of_speech(self):
        totals = builder.word_frequencies([
            "quick%5:00:00:fast:01 1 20", "quick%3:00:00:: 2 6",
            "quick%4:02:00:: 1 7",
        ])
        self.assertEqual(totals["quick", "adj"], 26)
        self.assertEqual(totals["quick", "adv"], 7)

    def test_rank_deduplicate_cap_and_avoid_unrelated_parts(self):
        indexes = {part: {} for part in builder.PARTS}
        synsets = {part: {} for part in builder.PARTS}
        indexes["adj"] = {"quick": ["1", "2", "3"]}
        indexes["noun"] = {"quick": ["4"]}
        indexes["adv"] = {"quick": ["5"]}
        synsets["adj"] = {
            "1": ["quick", "speedy", "at_once", "Unknown"],
            "2": ["quick", "flying", "fast", "speedy", "nimble"],
            "3": ["quick", "warm"],
        }
        synsets["noun"] = {"4": ["quick", "skin"]}
        synsets["adv"] = {"5": ["quick", "quickly"]}
        vocabulary = {"quick", "speedy", "flying", "fast", "nimble", "warm", "skin", "quickly"}
        totals = {("quick", "adj"): 26, ("quick", "adv"): 7,
                  ("fast", "adj"): 18, ("flying", "adj"): 2}
        self.assertEqual(builder.synonym_table(indexes, synsets, totals, vocabulary),
                         {"quick": ["speedy", "fast", "flying"]})
        synsets["adj"]["2"] = ["quick", "speedy"]
        self.assertEqual(builder.synonym_table(indexes, synsets, totals, vocabulary),
                         {"quick": ["speedy", "warm"]})

    def test_untagged_words_still_work_and_short_input_has_no_entry(self):
        indexes = {part: {} for part in builder.PARTS}
        synsets = {part: {} for part in builder.PARTS}
        indexes["noun"] = {"item": ["1"], "go": ["2"]}
        synsets["noun"] = {"1": ["item", "object"], "2": ["go", "try"]}
        self.assertEqual(builder.synonym_table(indexes, synsets, {},
                                               {"item", "object", "go", "try"}),
                         {"item": ["object"]})

    def test_local_data_is_bounded_and_known_and_license_is_embedded(self):
        if not WORDNET_TABLE.exists():
            self.skipTest("Optional Git-ignored WordNet candidate table is not installed")
        data = WORDNET_TABLE.read_text(encoding="utf-8")
        vocabulary = builder.dictionary_words([
            REPO / "en_dicts/en.dict.yaml", REPO / "en_dicts/en_ext.dict.yaml",
            REPO / "en_dicts/english_inflection_words.dict.yaml",
        ])
        rows = re.findall(r'^  \["([a-z]+)"\] = \{(.+)\},$', data, re.M)
        self.assertGreater(len(rows), 5000)
        common = builder.dictionary_words([
            REPO / 'en_dicts/en.dict.yaml', REPO / 'en_dicts/english_inflection_words.dict.yaml'])
        policy = json.loads((REPO / 'others/english_synonyms/wordnet_formal_policy.json').read_text())
        reviewed = {w for v in policy['entries'].values() for w in v}
        table = {}
        for code, body in rows:
            words = re.findall(r'"([a-z]+)"', body)
            self.assertIn(code, vocabulary)
            self.assertGreaterEqual(len(code), 3)
            self.assertTrue(1 <= len(words) <= 3)
            self.assertEqual(len(set(words)), len(words))
            self.assertNotIn(code, words)
            self.assertTrue(set(words) <= common | reviewed)
            self.assertNotIn(code, table)
            table[code] = words
        self.assertEqual(table["quick"], ["fast", "speedy"])
        self.assertIn("glad", table["happy"])
        self.assertIn("significant", table["important"])
        self.assertNotIn('authoritative', table['important'])
        self.assertEqual(table['support'], ['corroborate', 'substantiate', 'confirm'])
        self.assertNotIn('robust', table)
        self.assertIn("WordNet 3.0 Copyright 2006 by Princeton University", data)
        self.assertIn('THIS SOFTWARE AND DATABASE IS PROVIDED "AS IS"', data)

    def test_reproducible_from_pinned_local_wordnet(self):
        source = Path("/usr/share/wordnet")
        if not source.is_dir():
            self.skipTest("Pinned WordNet 3.0 data is not installed")
        for name, expected in builder.SHA256.items():
            if builder.hashlib.sha256((source / name).read_bytes()).hexdigest() != expected:
                self.skipTest("Installed WordNet is a different release")
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), str(source)],
                                check=True, capture_output=True, text=True)
        self.assertIn('-- Complete words: 8592; synonym pairs: 17363.', result.stdout)
        if WORDNET_TABLE.exists():
            self.assertEqual(result.stdout, WORDNET_TABLE.read_text())

    def test_raw_generation_remains_available_with_original_counts(self):
        source = Path('/usr/share/wordnet')
        if not all((source / name).exists() for name in builder.SHA256):
            self.skipTest('Pinned WordNet 3.0 data is not installed')
        for name, expected in builder.SHA256.items():
            if builder.hashlib.sha256((source / name).read_bytes()).hexdigest() != expected:
                self.skipTest('Installed WordNet is a different release')
        result = subprocess.run([sys.executable, '-B', str(SCRIPT), str(source), '--raw'],
                                check=True, capture_output=True, text=True)
        self.assertIn('-- Complete words: 8672; synonym pairs: 17628.', result.stdout)
        self.assertIn('["quick"] = {"speedy", "fast", "flying"}', result.stdout)


class SynonymLuaTests(unittest.TestCase):
    def setUp(self):
        # Reuse the existing dependency-free Lua runtime helper, not its tests.
        self.runtime = fuzzy_tests.EnglishFuzzyTests(methodName="runTest")
        self.addCleanup(self.runtime.doCleanups)
        self.runtime.setUp()
        self.run_lua = self.runtime.run_lua
        self.run_lua('''
            rime_api = {get_user_data_dir = function() return "/rime-test" end}
            loadfile = function(path, mode, sandbox)
                assert(path == "/rime-test/en_dicts/wordnet_synonyms.lua" and mode == "t")
                assert(type(sandbox) == "table" and next(sandbox) == nil)
                return function()
                    return {quick = {"speedy", "fast", "flying"}, happy = {"glad"}}
                end
            end
            -- Synonyms must be plain non-learning candidates, never phrases.
            Memory = function() error("Must not open a user dictionary") end
            Phrase = function() error("Must not create a learnable phrase") end
            warnings = 0
            log = {warning = function(message)
                assert(message == "English Booster: selected synonym data unavailable or invalid; trying fallback"
                    or message == "English Booster: no usable synonym data; synonym suggestions disabled")
                warnings = warnings + 1
            end}
            Candidate = function(kind, first, last, text, comment)
                return {type = kind, start = first, _end = last, text = text, comment = comment}
            end
            ShadowCandidate = function(source, kind, text, comment)
                return Candidate(kind, source.start, source._end, text, comment)
            end
        ''')
        self.run_lua("synonyms = dofile(" + repr(str(REPO / "lua/english_synonyms.lua")) + ")")
        self.run_lua('''
            function synonym_run(input, options)
                options = options or {}
                output = {}
                yield = function(candidate) output[#output + 1] = candidate end
                local context = {input = options.context_input or input,
                    get_option = function(self, name) return options.direct end}
                local config = {
                    get_string = function(self, path)
                        if path == "synonyms/data_file" then return options.data_file end
                        assert(path == "synonyms/fallback_file")
                        return options.fallback_file
                    end,
                    get_int = function() return options.limit end,
                    get_double = function() return options.quality end}
                local env = {engine = {context = context, schema = {config = config}}}
                local segment = {start = options.start or 0, _end = options._end or #input,
                    has_tag = function(self, tag) return tag == "abc" and not options.non_abc end}
                synonyms.init(env)
                synonyms.func(input, segment, env)
                return output, env
            end
            function case_rows(input, rows)
                local env = {engine = {context = {input = input}}}
                local translation = {iter = function()
                    local i = 0
                    return function() i = i + 1; return rows[i] end
                end}
                output = {}
                case_filter(translation, env)
                return output
            end
        ''')
        # Cache the default fixture; individual tests replace loadfile to exercise
        # other paths without opening real dictionary files.
        self.run_lua('assert(#synonym_run("quick") == 3)')

    def test_exact_word_only_no_short_prefix_fuzzy_or_punctuation(self):
        self.run_lua('''
            local result = synonym_run("quick")
            assert(#result == 3 and result[1].text == "speedy")
            for _, word in ipairs({"q", "qu", "qui", "quic", "quickly", "quik", "quick1", "quick!"}) do
                assert(#synonym_run(word) == 0, word)
            end
        ''')

    def test_direct_non_abc_and_partial_compositions_do_not_trigger(self):
        self.run_lua('''
            for _, options in ipairs({{direct = true}, {non_abc = true}, {start = 1},
                                      {_end = 4}, {context_input = "quickextra"}}) do
                assert(#synonym_run("quick", options) == 0)
            end
        ''')

    def test_limit_disabled_default_and_hard_cap(self):
        self.run_lua('''
            assert(#synonym_run("quick") == 3)
            assert(#synonym_run("quick", {limit = 1}) == 1)
            assert(#synonym_run("quick", {limit = 0}) == 0)
            assert(#synonym_run("quick", {limit = -1}) == 0)
            assert(#synonym_run("quick", {limit = 99}) == 3)
        ''')

    def test_private_table_replaces_default_and_is_cached_per_path(self):
        self.run_lua('''
            local loads = 0
            loadfile = function(path, mode, sandbox)
                assert(path == "/private/local.lua" and mode == "t")
                assert(type(sandbox) == "table" and next(sandbox) == nil)
                loads = loads + 1
                return function() return {quick = {"rapid", "swift", "fast"}} end
            end
            for _, word in ipairs({"quick", "Quick", "QUICK"}) do
                local rows = synonym_run(word, {data_file = "/private/local.lua"})
                assert(#rows == 3 and rows[1].text == "rapid" and rows[1].comment == "≈")
            end
            assert(loads == 1 and warnings == 0)
            local rows = synonym_run("quick")
            assert(rows[1].text == "speedy", "Fallback data must remain unchanged")
        ''')

    def test_empty_or_disabled_override_uses_default_or_skips_loading(self):
        self.run_lua('''
            loadfile = function() error("Must not load an override") end
            assert(synonym_run("quick", {data_file = ""})[1].text == "speedy")
            assert(#synonym_run("quick", {data_file = "/private/local.lua", limit = 0}) == 0)
            assert(warnings == 0)
        ''')

    def test_missing_or_invalid_lua_falls_back_without_exposing_private_details(self):
        self.run_lua('''
            loadfile = function() return nil, "private filename and dictionary content" end
            assert(synonym_run("quick", {data_file = "/private/missing.lua"})[1].text == "speedy")
            loadfile = function() return function() error("private details") end end
            assert(synonym_run("quick", {data_file = "/private/broken.lua"})[1].text == "speedy")
            assert(warnings == 2)
        ''')

    def test_malformed_tables_fall_back_instead_of_breaking_typing(self):
        self.run_lua('''
            local bad = {123, {}, {QUICK = {"fast"}}, {quick = {}},
                         {quick = "fast"}, {quick = {"two words"}},
                         {quick = {[1] = "fast", [3] = "swift"}},
                         {quick = {"fast", metadata = "swift"}}}
            for i, data in ipairs(bad) do
                loadfile = function() return function() return data end end
                assert(synonym_run("quick", {data_file = "/private/bad" .. i})[1].text == "speedy")
            end
            assert(warnings == #bad)
        ''')

    def test_two_private_tables_do_not_cross_contaminate_sessions(self):
        self.run_lua('''
            local loads = 0
            loadfile = function(path)
                loads = loads + 1
                return function() return {quick = {path == "/private/one.lua" and "rapid" or "swift"}} end
            end
            local first, env_one = synonym_run("quick", {data_file = "/private/one.lua"})
            local second, env_two = synonym_run("quick", {data_file = "/private/two.lua"})
            assert(first[1].text == "rapid" and second[1].text == "swift")
            assert(env_one.words.quick[1] == "rapid" and env_two.words.quick[1] == "swift")
            assert(synonym_run("quick", {data_file = "/private/one.lua"})[1].text == "rapid")
            assert(loads == 2 and warnings == 0)
        ''')

    def test_relative_paths_resolve_under_user_directory_and_share_cache(self):
        self.run_lua('''
            local loads = 0
            loadfile = function(path, mode, sandbox)
                assert(path == "/rime-test/en_dicts/mw2015_synonyms.lua" and mode == "t")
                assert(next(sandbox) == nil)
                loads = loads + 1
                return function() return {quick = {"rapid"}} end
            end
            assert(synonym_run("quick", {data_file = "en_dicts/mw2015_synonyms.lua"})[1].text == "rapid")
            assert(synonym_run("quick", {data_file = "/rime-test/en_dicts/mw2015_synonyms.lua"})[1].text == "rapid")
            assert(loads == 1 and warnings == 0)
        ''')

    def test_configurable_fallback_and_missing_both_tables(self):
        self.run_lua('''
            loadfile = function(path)
                if path == "/rime-test/en_dicts/alternative.lua" then
                    return function() return {quick = {"swift"}} end
                end
                return nil, "private details"
            end
            assert(synonym_run("quick", {data_file = "missing.lua",
                fallback_file = "en_dicts/alternative.lua"})[1].text == "swift")
            assert(warnings == 1)
            assert(#synonym_run("quick", {data_file = "missing.lua",
                fallback_file = "also-missing.lua"}) == 0)
            assert(warnings == 3)
        ''')

    def test_fresh_checkout_without_data_and_disabled_feature_do_not_break(self):
        self.run_lua("synonyms = dofile(" + repr(str(REPO / "lua/english_synonyms.lua")) + ")")
        self.run_lua('''
            local loads = 0
            loadfile = function() loads = loads + 1; return nil, "missing" end
            assert(#synonym_run("quick", {limit = 0}) == 0)
            assert(loads == 0 and warnings == 0)
            assert(#synonym_run("quick") == 0)
            assert(loads == 1 and warnings == 1)
        ''')

    def test_plain_candidates_label_range_and_priority(self):
        self.run_lua('''
            local result = synonym_run("quick")
            for _, candidate in ipairs(result) do
                assert(candidate.type == "synonym" and candidate.comment == "≈")
                assert(candidate.start == 0 and candidate._end == 5)
                assert(candidate.quality > -1 and candidate.quality < -0.75)
                assert(candidate.code == nil)
            end
            assert(result[1].quality > result[2].quality)
            assert(result[2].quality > result[3].quality)
        ''')

    def test_literal_and_case_preserved_even_with_only_synonym_candidates(self):
        self.run_lua('''
            for _, pair in ipairs({{"quick", "speedy"}, {"Quick", "Speedy"}, {"QUICK", "SPEEDY"}}) do
                local input, expected = pair[1], pair[2]
                local synonyms = synonym_run(input)
                local rows = case_rows(input, synonyms)
                assert(#rows == 4 and rows[1].text == input and rows[1].comment == "")
                assert(rows[2].text == expected and rows[2].comment == "≈")
            end
            local suggestions = synonym_run("quick")
            table.insert(suggestions, 1, Candidate("table", 0, 5, "quick", ""))
            local rows = case_rows("quick", suggestions)
            assert(#rows == 4 and rows[1].type == "table" and rows[1].text == "quick")
        ''')


if __name__ == "__main__":
    unittest.main()
