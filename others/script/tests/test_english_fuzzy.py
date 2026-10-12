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
        cycle = module.with_name("input_mode_cycle.lua")
        self.run_lua("mode_cycle = dofile(" + repr(str(cycle)) + ")")
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

    def test_command_names_enter_plain_english_only_at_unmodified_boundaries(self):
        self.run_lua('''
            Schema = function(name) return {schema_id = name} end
            local function key(code, modifiers)
                modifiers = modifiers or {}
                local result = {keycode = code}
                for _, name in ipairs({"release", "ctrl", "alt", "super", "shift"}) do
                    result[name] = function() return modifiers[name] end
                end
                return result
            end
            local function make_env(schema, input, options)
                options = options or {}
                local names = {"git", "emacs", "latexmk", "rg", ""}
                local list = {size = #names,
                    get_value_at = function(self, i) return {value = names[i + 1]} end}
                local segment = {start = options.start or 0, _end = options._end or #input,
                    selected_index = options.selected_index or 0}
                local context = {input = input,
                    composition = {back = function() return segment end},
                    get_option = function(self) return self.ascii_mode or options.ascii or false end,
                    is_composing = function(self) return self.input ~= "" and not options.idle end,
                    get_selected_candidate = function() return {text = options.selected_text or input} end,
                    clear = function(self) self.input = "" end,
                    set_option = function(self, name, value) self[name] = value end}
                local engine = {context = context, commits = {}, applications = 0,
                    schema = {schema_id = schema, config = {get_list = function(self, path)
                        if path == "emacs_keys/prefixes" then return nil end
                        assert(path == "command_mode/commands")
                        if not options.disabled then return list end
                    end}}}
                engine.commit_text = function(self, text) self.commits[#self.commits + 1] = text end
                engine.apply_schema = function(self, next_schema)
                    self.schema = next_schema; self.applications = self.applications + 1
                end
                local env = {engine = engine}
                mode_cycle.init(env)
                assert(env.commands[""] == nil)
                return env
            end
            for _, schema in ipairs({"rime_ice", "english_booster"}) do
                for _, command in ipairs({"git", "emacs", "latexmk", "rg"}) do
                    for _, boundary in ipairs({0x20, 0xff0d}) do
                        local env = make_env(schema, command)
                        assert(mode_cycle.func(key(boundary), env) == 1)
                        local engine = env.engine
                        assert(#engine.commits == 1)
                        assert(engine.commits[1] == command .. (boundary == 0x20 and " " or ""))
                        assert(engine.context.input == "" and engine.context.ascii_mode == true)
                        assert(engine.schema.schema_id == "rime_ice")
                        assert(engine.applications == (schema == "english_booster" and 1 or 0))
                        mode_cycle.func(key(0xffe1), env)
                        assert(mode_cycle.func(key(0xffe1, {release = true, shift = true}), env) == 0)
                        assert(engine.schema.schema_id == "english_booster" and not engine.context.ascii_mode)
                    end
                end
            end
            local function untouched(env, event)
                local before = env.engine.context.input
                assert(mode_cycle.func(event, env) == 2)
                assert(#env.engine.commits == 0 and env.engine.context.input == before)
                assert(env.engine.context.ascii_mode == nil and env.engine.applications == 0)
            end
            for _, word in ipairs({"gi", "emac", "Git", "GIT", "gitword", "hello"}) do
                untouched(make_env("english_booster", word), key(0x20))
            end
            for _, modifiers in ipairs({{release = true}, {ctrl = true}, {alt = true},
                                         {super = true}, {shift = true}}) do
                for _, boundary in ipairs({0x20, 0xff0d}) do
                    untouched(make_env("english_booster", "git"), key(boundary, modifiers))
                end
            end
            for _, options in ipairs({{ascii = true}, {idle = true}, {start = 1}, {_end = 2},
                                       {disabled = true}, {selected_index = 1, selected_text = "GitHub"}}) do
                untouched(make_env("english_booster", "git", options), key(0x20))
            end
            untouched(make_env("other_schema", "git"), key(0x20))
            untouched(make_env("english_booster", "git"), key(0xff09))
        ''')

    def prefix_mocks(self):
        self.run_lua('''
            Schema = function(name) return {schema_id = name} end
            function event(code, modifiers)
                modifiers = modifiers or {}
                local result = {keycode = code}
                for _, name in ipairs({"release", "ctrl", "alt", "super", "shift"}) do
                    result[name] = function() return modifiers[name] end
                end
                return result
            end
            KeyEvent = function(token)
                local modifiers = {}
                for name, flag in pairs({Control = "ctrl", Alt = "alt", Shift = "shift"}) do
                    if token:find(name .. "+", 1, true) then modifiers[flag] = true end
                end
                local name = token:match("([^+]+)$")
                local code = ({Escape = 0xff1b, Return = 0xff0d, at = 64})[name]
                if not code and #name == 1 then code = string.byte(name) end
                assert(code, "Invalid key name")
                return event(code, modifiers)
            end
            function prefix_env(schema, input, ascii, prefixes)
                prefixes = prefixes or {"Control+x r", "Control+c", "Escape Escape",
                    "Control+x a i", "Control+x 4", "Control+x Return", "Control+x at"}
                local list = {size = #prefixes,
                    get_value_at = function(self, i) return {value = prefixes[i + 1]} end}
                local listener
                local context = {input = input or "", ascii_mode = ascii or false,
                    get_option = function(self) return self.ascii_mode end,
                    is_composing = function(self) return self.input ~= "" end,
                    clear = function(self) self.input = ""; if listener then listener() end end,
                    clear_non_confirmed_composition = function(self) self.preserved = true end,
                    set_option = function(self, name, value) self[name] = value end,
                    update_notifier = {connect = function(self, callback)
                        listener = callback
                        return {disconnect = function() listener = nil end}
                    end}}
                local engine = {context = context, commits = {},
                    schema = {schema_id = schema or "english_booster", config = {
                        get_list = function(self, path)
                            if path == "emacs_keys/prefixes" then return list end
                        end}}}
                engine.apply_schema = function(self, next_schema) self.schema = next_schema end
                context.commit = function(self)
                    engine.commits[#engine.commits + 1] = self.input
                    self:clear()
                end
                local env = {engine = engine}
                mode_cycle.init(env)
                return env
            end
        ''')

    def test_emacs_prefixes_send_raw_events_and_resume_normal_input(self):
        self.prefix_mocks()
        self.run_lua('''
            local ctrl = {ctrl = true}
            for _, schema in ipairs({"rime_ice", "english_booster"}) do
                for _, ascii in ipairs({false, true}) do
                    for _, sequence in ipairs({
                        {event(120, ctrl), event(98)}, -- C-x b
                        {event(99, ctrl), event(122)}, -- C-c z
                        {event(0xff1b), event(120)}, -- ESC x
                        {event(120, ctrl), event(114), event(98)}, -- C-x r b
                        {event(120, ctrl), event(97), event(105), event(103)}, -- C-x a i g
                        {event(120, ctrl), event(52), event(102)}, -- C-x 4 f
                        {event(120, ctrl), event(0xff0d), event(102)},
                        {event(120, ctrl), event(64, {shift = true}), event(98)},
                        {event(120, ctrl), event(120, ctrl)}, -- Do not re-arm C-x C-x.
                        {event(120, ctrl), event(99, ctrl)}, -- Or C-x C-c.
                        {event(0xff1b), event(0xff1b), event(0xff1b)},
                    }) do
                        local env = prefix_env(schema, "", ascii)
                        for _, key in ipairs(sequence) do
                            assert(mode_cycle.func(key, env) == 0, "Must reject original event")
                            assert(#env.engine.commits == 0)
                        end
                        assert(env.pending_prefix == nil)
                        assert(mode_cycle.func(event(104), env) == 2, "Resume normal IME processing")
                        assert(env.engine.schema.schema_id == schema)
                        assert(env.engine.context.ascii_mode == ascii)
                    end
                end
            end
        ''')

    def test_emacs_prefix_modifiers_releases_cancel_and_composition_policy(self):
        self.prefix_mocks()
        self.run_lua('''
            local env = prefix_env("english_booster", "comput")
            assert(mode_cycle.func(event(120, {ctrl = true}), env) == 0)
            assert(env.engine.context.preserved and env.engine.commits[1] == "comput")
            local pending = env.pending_prefix
            for _, key in ipairs({event(120, {ctrl = true, release = true}),
                event(0xffe3, {release = true}), event(0xffe1),
                event(0xffe4), event(0xffe9), event(0xffeb)}) do
                assert(mode_cycle.func(key, env) == 0)
                assert(env.pending_prefix == pending, "Modifiers must not advance prefix")
            end
            assert(mode_cycle.func(event(66, {shift = true}), env) == 0)
            assert(mode_cycle.func(event(0xffe1, {release = true, shift = true}), env) == 2)
            assert(env.engine.schema.schema_id == "english_booster")
            assert(not env.engine.context.ascii_mode, "Shift in command must not cycle")
            assert(mode_cycle.func(event(0xffe1), env) == 2)
            assert(mode_cycle.func(event(0xffe1, {release = true, shift = true}), env) == 0)
            assert(env.engine.schema.schema_id == "english_booster"
                   and env.engine.context.ascii_mode, "Standalone Shift enters plain English")
            for _, code in ipairs({103, 0xff1b}) do
                env = prefix_env("rime_ice", "nihao")
                assert(mode_cycle.func(event(code, {ctrl = code == 103}), env) == 0)
                assert(env.engine.context.input == "" and #env.engine.commits == 0)
                if code == 0xff1b then assert(env.pending_prefix) end
                assert(mode_cycle.func(event(103, {ctrl = true}), env) == 0)
                assert(env.pending_prefix == nil)
                assert(mode_cycle.func(event(98), env) == 2, "C-g must not arm a prefix")
            end
            env = prefix_env()
            assert(mode_cycle.func(event(120, {ctrl = true}), env) == 0)
            env.engine.context:clear()
            assert(env.pending_prefix == nil, "Frontend reset clears stale prefix")
            mode_cycle.fini(env)
        ''')

    def test_emacs_prefix_configuration_and_modifier_guards(self):
        self.prefix_mocks()
        self.run_lua('''
            for _, modifiers in ipairs({{ctrl = true, alt = true}, {ctrl = true, super = true},
                                         {ctrl = true, release = true}}) do
                local env = prefix_env()
                assert(mode_cycle.func(event(120, modifiers), env) == 2)
                assert(env.pending_prefix == nil)
            end
            local env = prefix_env("english_booster", "draft", false, {})
            assert(mode_cycle.func(event(120, {ctrl = true}), env) == 2)
            assert(mode_cycle.func(event(103, {ctrl = true}), env) == 2)
            assert(env.engine.context.input == "draft")
            env = prefix_env("other_schema")
            assert(mode_cycle.func(event(120, {ctrl = true}), env) == 2)
            env = prefix_env(nil, "", false, {"Control+c p", "not-a-key", "Release+x"})
            for _, key in ipairs({event(99, {ctrl = true}), event(112), event(102)}) do
                assert(mode_cycle.func(key, env) == 0, "Custom nested prefixes are configurable")
            end
            assert(mode_cycle.func(event(104), env) == 2)
        ''')

    def test_four_step_shift_cycle_from_every_starting_state(self):
        self.prefix_mocks()
        self.run_lua('''
            local states = {{"rime_ice", false}, {"rime_ice", true},
                            {"english_booster", false}, {"english_booster", true}}
            for start, state in ipairs(states) do
                local env = prefix_env(state[1], "", state[2])
                for step = 1, 40 do
                    local code = step % 2 == 0 and 0xffe1 or 0xffe2
                    assert(mode_cycle.func(event(code), env) == 2)
                    assert(mode_cycle.func(event(code, {release = true, shift = true}), env) == 0)
                    local expected = states[(start + step - 1) % 4 + 1]
                    assert(env.engine.schema.schema_id == expected[1])
                    assert(env.engine.context.ascii_mode == expected[2])
                    assert(#env.engine.commits == 0)
                    -- Extra releases do not advance the cycle.
                    assert(mode_cycle.func(event(code, {release = true}), env) == 2)
                    assert(env.engine.schema.schema_id == expected[1])
                    assert(env.engine.context.ascii_mode == expected[2])
                end
            end
        ''')

    def test_shift_enters_plain_english_preserving_unfinished_input(self):
        self.prefix_mocks()
        self.run_lua('''
            for _, pair in ipairs({{"rime_ice", "nihao"}, {"english_booster", "comput"}}) do
                local env = prefix_env(pair[1], pair[2])
                mode_cycle.func(event(0xffe1), env)
                assert(mode_cycle.func(event(0xffe1, {release = true, shift = true}), env) == 0)
                assert(env.engine.context.preserved and env.engine.commits[1] == pair[2])
                assert(env.engine.schema.schema_id == pair[1] and env.engine.context.ascii_mode)
                mode_cycle.func(event(0xffe2), env)
                assert(mode_cycle.func(event(0xffe2, {release = true, shift = true}), env) == 0)
                assert(env.engine.schema.schema_id == (pair[1] == "rime_ice" and "english_booster" or "rime_ice"))
                assert(not env.engine.context.ascii_mode and #env.engine.commits == 1)
            end
        ''')

    def test_shift_taps_keep_frontend_press_and_release_balanced(self):
        self.prefix_mocks()
        self.run_lua('''
            local states = {{"rime_ice", false}, {"rime_ice", true},
                            {"english_booster", false}, {"english_booster", true}}
            for _, code in ipairs({0xffe1, 0xffe2}) do
                for _, state in ipairs(states) do
                    local env = prefix_env(state[1], "", state[2])
                    local frontend_shift = false
                    local function deliver(release)
                        local result = mode_cycle.func(event(code,
                            {release = release, shift = release}), env)
                        -- Accepted events are not delivered to the frontend;
                        -- rejected/noop events can preserve the physical pair.
                        if result ~= 1 then frontend_shift = not release end
                        return result
                    end
                    for tap = 1, 40 do
                        assert(deliver(false) == 2 and frontend_shift)
                        assert(deliver(true) == 0, "Shift keyup must bypass downstream Rime processors")
                        assert(not frontend_shift, "Do not leave the frontend holding Shift")
                        assert(mode_cycle.func(event(44), env) == 2)
                        local comma = frontend_shift and "<" or ","
                        assert(comma == ",", "Unmodified punctuation must remain unshifted")
                    end
                    assert(env.engine.schema.schema_id == state[1])
                    assert(env.engine.context.ascii_mode == state[2])
                end
            end
        ''')

    def test_shift_modifier_chords_still_pass_through_without_cycling(self):
        self.prefix_mocks()
        self.run_lua('''
            for _, schema in ipairs({"rime_ice", "english_booster"}) do
                for _, code in ipairs({0xffe1, 0xffe2}) do
                    for _, chord in ipairs({{0xffe3, "ctrl"}, {0xffe9, "alt"}, {0xffeb, "super"}}) do
                        local env = prefix_env(schema)
                        assert(mode_cycle.func(event(code), env) == 2)
                        assert(mode_cycle.func(event(chord[1], {shift = true}), env) == 2)
                        local modifiers = {release = true, shift = true, [chord[2]] = true}
                        assert(mode_cycle.func(event(code, modifiers), env) == 2)
                        assert(env.pending_shift == nil)
                        assert(env.engine.schema.schema_id == schema)
                        assert(not env.engine.context.ascii_mode)
                    end
                end
            end
        ''')

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

    def test_missing_doubled_letters_precede_substitutions(self):
        self.run_lua('''
            local words = {}
            for _, word in ipairs({"dotted", "coted", "noted", "toted", "voted",
                                   "running", "tuning", "ruling", "pruning", "ruining"}) do
                words[word] = {word}
            end
            for input, correct in pairs({doted = "dotted", Doted = "dotted",
                                         DOTED = "dotted", runing = "running"}) do
                local result = run(input, words)
                assert(#result == 4 and result[1].text == correct, input)
                assert(result[1].code == correct .. " ")
                local count = 0
                for _, candidate in ipairs(result) do
                    if candidate.text == correct then count = count + 1 end
                end
                assert(count == 1, "Priority lookup must not duplicate later insertion matches")
            end
            local result = run("abde", {adbe = {"adbe"}, abbde = {"abbde"}})
            assert(result[1].text == "adbe", "Adjacent swaps retain first priority")
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

    def test_candidate_popup_starts_at_three_letters(self):
        self.run_lua('''
            for input, expected in pairs({I = 0, a = 0, ab = 0, AB = 0, Co = 0,
                                          go = 0, run = 1, Run = 1, RUN = 1}) do
                local output = {}
                local candidate = {type = "table", text = input, comment = ""}
                yield = function(value) output[#output + 1] = value end
                local translation = {iter = function()
                    local pending = true
                    return function()
                        if pending then pending = false; return candidate end
                    end
                end}
                case_filter(translation, {engine = {context = {input = input}}})
                assert(#output == expected, input)
                if expected > 0 then assert(output[1] == candidate) end
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
