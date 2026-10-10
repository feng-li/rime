"""Offline Lua tests, using the Lua runtime already required by librime-lua."""

import ctypes
import ctypes.util
from pathlib import Path
import unittest


class EnglishFuzzyTests(unittest.TestCase):
    def setUp(self):
        library = ctypes.util.find_library("lua5.4")
        if not library:
            self.skipTest("Lua 5.4 runtime is not installed")
        self.lua = ctypes.CDLL(library)
        self.lua.luaL_newstate.restype = ctypes.c_void_p
        self.lua.luaL_openlibs.argtypes = [ctypes.c_void_p]
        self.lua.luaL_loadstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        self.lua.lua_pcallk.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                      ctypes.c_int, ctypes.c_ssize_t, ctypes.c_void_p]
        self.lua.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        self.lua.lua_tolstring.restype = ctypes.c_char_p
        self.lua.lua_close.argtypes = [ctypes.c_void_p]
        self.state = self.lua.luaL_newstate()
        self.addCleanup(self.lua.lua_close, self.state)
        self.lua.luaL_openlibs(self.state)
        module = Path(__file__).resolve().parents[3] / "lua/english_fuzzy.lua"
        # All Rime objects are mocked; no user dictionaries are opened or changed.
        self.run_lua("fuzzy = dofile(" + repr(str(module)) + ")")
        booster = module.with_name("english_booster.lua")
        self.run_lua("case_filter = dofile(" + repr(str(booster)) + ").case_filter")
        self.run_lua(r'''
            local vocabulary, current_code, output
            queries = 0
            disconnected = false
            Memory = function(engine, schema, namespace)
                assert(namespace == "fuzzy")
                return {
                    dict_lookup = function(self, code, predictive, limit)
                        assert(predictive == false)
                        queries = queries + 1
                        current_code = code
                        return vocabulary[code] ~= nil
                    end,
                    iter_dict = function(self)
                        local index = 0
                        return function()
                            index = index + 1
                            local text = vocabulary[current_code][index]
                            if text then return {text = text} end
                        end
                    end,
                    disconnect = function(self) disconnected = true end,
                }
            end
            DictEntry = function() return {} end
            Phrase = function(memory, kind, first, last, entry)
                return {toCandidate = function()
                    assert(kind == "spelling")
                    return {type = kind, text = entry.text, code = entry.custom_code, comment = "",
                            start = first, _end = last}
                end}
            end
            yield = function(candidate) output[#output + 1] = candidate end
            function run(input, words, normal, options)
                vocabulary, queries, output = words or {}, 0, {}
                options = options or {}
                local segment = {start = options.start or 0, _end = options._end or #input,
                    has_tag = function(self, tag) return tag == "abc" and not options.non_abc end}
                local context = {input = input,
                    get_option = function(self, name) return options.direct end,
                    composition = {back = function() return segment end}}
                local env = {engine = {context = context, schema = {}}}
                local translation = {iter = function()
                    local i = 0
                    return function() i = i + 1; return (normal or {})[i] end
                end}
                fuzzy.func(translation, env)
                return output, env
            end
        ''')

    def run_lua(self, source):
        status = self.lua.luaL_loadstring(self.state, source.encode())
        if status == 0:
            status = self.lua.lua_pcallk(self.state, 0, 0, 0, 0, None)
        if status != 0:
            self.fail(self.lua.lua_tolstring(self.state, -1, None).decode())

    def test_single_edits_and_correct_learning_codes(self):
        self.run_lua('''
            for typo, correct in pairs({wrod = "word", hellp = "hello",
                                       forcng = "forcing", colorr = "color"}) do
                local result, env = run(typo, {[correct] = {correct}})
                assert(#result == 1 and result[1].text == correct, typo)
                assert(result[1].code == correct .. " ")
                assert(result[1].start == 0 and result[1]._end == #typo)
                assert(result[1].quality == -1)
                fuzzy.fini(env)
                assert(env.lookup == nil and disconnected)
            end
            local result = run("COMUPTER", {computer = {"computer"}})
            assert(#result == 1 and result[1].text == "computer")
            assert(#run("rciive", {receive = {"receive"}}) == 0)
        ''')

    def test_normal_and_personal_candidates_are_untouched(self):
        self.run_lua('''
            for _, text in ipairs({"computer", "comupter", "comupterword"}) do
                local original = {text = text}
                local result, env = run("comupter", {computer = {"computer"}}, {original})
                assert(#result == 1 and result[1] == original)
                assert(queries == 0 and env.lookup == nil)
            end
        ''')

    def test_typo_marker_is_a_display_only_comment(self):
        self.run_lua('''
            Candidate = function(kind, first, last, text, comment)
                return {type = kind, start = first, _end = last, text = text, comment = comment}
            end
            ShadowCandidate = function(source, kind, text, comment)
                return Candidate(kind, source.start, source._end, text, comment)
            end
            local function display(input, sources)
                local output = {}
                yield = function(candidate) output[#output + 1] = candidate end
                local translation = {iter = function()
                    local i = 0
                    return function() i = i + 1; return sources[i] end
                end}
                case_filter(translation, {engine = {context = {input = input}}})
                return output
            end
            for input, correct in pairs({comupter = "computer", Comupter = "Computer",
                                         COMUPTER = "COMPUTER"}) do
                local sources = {Candidate("spelling", 0, #input, "computer", "")}
                local output = display(input, sources)
                assert(#output == 2 and output[1].text == input and output[1].comment == "*")
                assert(output[1].type == "literal" and output[2].text == correct)
                assert(output[2].comment == "")
            end
            for _, example in ipairs({{"comput", "computer", "completion"},
                                       {"force", "forcing", "inflection"},
                                       {"computer", "computer", "table"},
                                       {"comupter", "comupter", "user_table"}}) do
                local input, text, kind = table.unpack(example)
                local output = display(input, {Candidate(kind, 0, #input, text, "")})
                assert(output[1].text == input and output[1].comment == "")
            end
            assert(#display("zxqvnonword", {}) == 0)
        ''')

    def test_guards(self):
        self.run_lua('''
            for _, input in ipairs({"cat", "abcdefghijklmnopqrstuvwxyz", "foo-bar",
                                     "user@example.com", "1234", "中文"}) do
                assert(#run(input, {}) == 0 and queries == 0)
            end
            for _, options in ipairs({{direct = true}, {non_abc = true},
                                      {start = 1}, {_end = 6}}) do
                assert(#run("comupter", {}, {}, options) == 0 and queries == 0)
            end
        ''')

    def test_aliases_duplicates_and_four_suggestion_limit(self):
        self.run_lua('''
            local result = run("forcng", {forcing = {"forcing", "Forcing", "forcing"}})
            assert(#result == 1)
            assert(#run("junee", {june = {"July"}}) == 0)
            local words = {}
            for _, letter in ipairs({"a", "b", "c", "d", "o"}) do
                words["hell" .. letter] = {"hell" .. letter}
            end
            result = run("hellp", words)
            assert(#result == 4 and result[1].text == "hella" and result[4].text == "helld")
        ''')


if __name__ == "__main__":
    unittest.main()
