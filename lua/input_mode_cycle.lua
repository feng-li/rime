-- Tap either Shift: Pinyin -> plain English -> Booster -> plain English -> Pinyin.
-- A configured shortcut toggles Booster and the previous schema/ascii state.
-- A Shift used with any other key is only a modifier, never a mode switch.
-- Exact command names + Space/Enter enter the same plain-English mode.
-- Configured Emacs prefixes and their command key bypass all IME processors.
local cycle = {}

local function key_id(key)
  -- X11 already puts the shifted printable symbol in keycode (e.g. Shift+@).
  -- Ignore Shift only for printable ASCII; retain it for Return, arrows, etc.
  local shift = key:shift() and (key.keycode < 0x21 or key.keycode > 0x7e)
  return tostring(key.keycode) .. (key:ctrl() and ":C" or "")
      .. (key:alt() and ":A" or "") .. (key:super() and ":S" or "")
      .. (shift and ":H" or "")
end

function cycle.init(env)
  env.pending_shift = nil
  env.pending_booster = nil
  env.booster_key = nil
  env.pending_booster_chord = nil
  local shortcut = env.engine.schema.config:get_string("input_modes/booster_key")
  env.booster_chord = shortcut == "Control+Shift"
  if shortcut and shortcut ~= "" and not env.booster_chord then
    local ok, event = pcall(KeyEvent, shortcut)
    if ok and event and event.keycode ~= 0 and not event:release() then
      env.booster_key = key_id(event)
    end
  end
  env.pending_prefix = nil
  env.prefixes = {}
  local prefixes = env.engine.schema.config:get_list("emacs_keys/prefixes")
  if prefixes then
    for i = 0, prefixes.size - 1 do
      local value = prefixes:get_value_at(i)
      local ids, valid = {}, true
      for token in (value and value.value or ""):gmatch("%S+") do
        local ok, event = pcall(KeyEvent, token)
        if not ok or not event or event.keycode == 0 or event:release() then
          valid = false; break
        end
        ids[#ids + 1] = key_id(event)
      end
      if valid then
        local node = env.prefixes
        for _, id in ipairs(ids) do
          node[id] = node[id] or {}
          node = node[id]
        end
      end
    end
  end
  -- A frontend reset (including focus changes that reset composition) must
  -- not leave a stale prefix waiting to swallow the next typed character.
  local notifier = env.engine.context.update_notifier
  if notifier then
    env.prefix_connection = notifier:connect(function()
      env.pending_prefix, env.pending_booster, env.pending_booster_chord = nil, nil, nil
    end)
  end
  env.commands = {}
  local commands = env.engine.schema.config:get_list("command_mode/commands")
  if commands then
    for i = 0, commands.size - 1 do
      local value = commands:get_value_at(i)
      if value and value.value ~= "" then env.commands[value.value] = true end
    end
  end
end

function cycle.fini(env)
  if env.prefix_connection then env.prefix_connection:disconnect() end
end

local function emacs_key_pass(key, env)
  local engine = env.engine
  local schema_id = engine.schema.schema_id
  if (schema_id ~= "rime_ice" and schema_id ~= "english_booster")
      or not next(env.prefixes) then return 2 end
  if key:release() then return env.pending_prefix and 0 or 2 end
  if key.keycode >= 0xffe1 and key.keycode <= 0xffee then
    if env.pending_prefix then
      env.pending_shift = nil
      return 0 -- Modifier presses/releases do not complete a prefix.
    end
    return 2
  end
  local id = key_id(key)
  local context = engine.context
  if id == "103:C" then -- C-g cancels; it is not a prefix waiting for a letter.
    env.pending_prefix, env.pending_shift = nil, nil
    context:clear()
    return 0
  end
  if env.pending_prefix then
    -- Do NOT re-arm from the root: C-x C-x and C-x C-c are complete commands.
    env.pending_prefix = env.pending_prefix[id]
    env.pending_shift = nil
    return 0
  end
  local prefix = env.prefixes[id]
  if not prefix then return 2 end
  env.pending_shift = nil
  if key.keycode == 0xff1b then
    context:clear() -- Escape cancels unfinished IME input before reaching Emacs.
  elseif context:is_composing() then
    -- Preserve selected text + literal unfinished input, as with Shift cycling.
    context:clear_non_confirmed_composition()
    context:commit()
  end
  env.pending_prefix = prefix
  return 0 -- kRejected sends the ORIGINAL key event, not committed text.
end

local function command_mode(key, env)
  if (key.keycode ~= 0x20 and key.keycode ~= 0xff0d)
      or key:release() or key:ctrl() or key:alt() or key:super() or key:shift() then return 2 end
  local engine = env.engine
  local context = engine.context
  local schema_id = engine.schema.schema_id
  if (schema_id ~= "rime_ice" and schema_id ~= "english_booster")
      or context:get_option("ascii_mode") or not context:is_composing()
      or not env.commands[context.input] then return 2 end
  local segment = context.composition:back()
  if not segment or segment.start ~= 0 or segment._end ~= #context.input then return 2 end
  local selected = context:get_selected_candidate()
  if segment.selected_index > 0 and selected and selected.text ~= context.input then
    return 2 -- A deliberately selected completion or Chinese candidate wins.
  end
  local input = context.input
  context:clear()
  engine:commit_text(input .. (key.keycode == 0x20 and " " or ""))
  if schema_id == "english_booster" then
    engine:apply_schema(Schema("rime_ice"))
  end
  engine.context:set_property("booster_previous_mode", "")
  engine.context:set_option("ascii_mode", true)
  return 1 -- Consume the boundary; Enter confirms without sending a newline.
end

local function toggle_booster(env)
  local engine = env.engine
  local context = engine.context
  local schema_id = engine.schema.schema_id
  local was_ascii = context:get_option("ascii_mode")
  local target, ascii = "english_booster", false
  if schema_id == "english_booster" and not was_ascii then
    local saved = context:get_property("booster_previous_mode") or ""
    local name, flag = saved:match("^([^:]+):([01])$")
    if name == "rime_ice" or (name == "english_booster" and flag == "1") then
      target, ascii = name, flag == "1"
    else
      target = "rime_ice" -- Booster selected without this shortcut has no return state.
    end
    context:set_property("booster_previous_mode", "")
  else
    -- Context properties survive schema changes; Lua processor environments do not.
    context:set_property("booster_previous_mode", schema_id .. (was_ascii and ":1" or ":0"))
  end
  if context:is_composing() then
    context:clear_non_confirmed_composition()
    context:commit()
  end
  if target ~= schema_id then engine:apply_schema(Schema(target)) end
  engine.context:set_option("ascii_mode", ascii)
end

local function booster_shortcut(key, env)
  local schema_id = env.engine.schema.schema_id
  if schema_id ~= "rime_ice" and schema_id ~= "english_booster" then return 2 end
  if env.booster_chord then
    local code = key.keycode
    local shift = code == 0xffe1 or code == 0xffe2
    local ctrl = code == 0xffe3 or code == 0xffe4
    if (not shift and not ctrl) or key:alt() or key:super() then
      env.pending_booster_chord = nil -- A third key makes this an application shortcut.
      return 2
    end
    if key:release() then
      if not env.pending_booster_chord then return 2 end
      env.pending_booster_chord, env.pending_shift = nil, nil
      toggle_booster(env)
      -- Both physical modifier presses AND releases must reach the frontend.
      return 0
    end
    if (shift and key:ctrl()) or (ctrl and key:shift()) then
      env.pending_booster_chord, env.pending_shift = true, nil
      return 0
    end
    return 2
  end
  if key:release() then
    if env.pending_booster ~= key.keycode then return 2 end
    env.pending_booster = nil
    toggle_booster(env)
    return 1
  end
  if not env.booster_key or key_id(key) ~= env.booster_key then return 2 end
  env.pending_shift = nil
  env.pending_booster = key.keycode
  -- Switch on release so holding the key cannot cycle through repeated presses.
  return 1
end

function cycle.func(key, env)
  local passed = emacs_key_pass(key, env)
  if passed ~= 2 then
    env.pending_booster, env.pending_booster_chord = nil, nil
    return passed
  end
  local shortcut = booster_shortcut(key, env)
  if shortcut ~= 2 then return shortcut end
  local code = key.keycode
  if code ~= 0xffe1 and code ~= 0xffe2 then -- Shift_L / Shift_R
    env.pending_shift = nil
    return command_mode(key, env)
  end
  if key:ctrl() or key:alt() or key:super() then
    env.pending_shift = nil
    return 2
  end
  if not key:release() then
    if env.pending_shift then
      env.pending_shift = nil -- Repeated presses or both Shifts are not a tap.
    else
      env.pending_shift = code
    end
    return 2 -- Let the physical Shift press reach the application.
  end

  local tap = env.pending_shift == code
  env.pending_shift = nil
  if not tap then
    return 2
  end

  local engine = env.engine
  local context = engine.context
  local schema_id = engine.schema.schema_id
  if schema_id ~= "rime_ice" and schema_id ~= "english_booster" then
    return 2
  end
  local was_ascii = context:get_option("ascii_mode")
  if context:is_composing() then
    -- Same commit-code policy as the previous Shift toggle: preserve selected
    -- text and literal unfinished input, without accepting a guessed word.
    context:clear_non_confirmed_composition()
    context:commit()
  end

  context:set_property("booster_previous_mode", "")
  if not was_ascii then
    -- Each predictive schema has its own plain-English step before leaving it.
    context:set_option("ascii_mode", true)
  else
    engine:apply_schema(Schema(schema_id == "english_booster" and "rime_ice" or "english_booster"))
    engine.context:set_option("ascii_mode", false)
  end
  -- The press passed through, so the release must reach the frontend too.
  -- Consuming only the release can leave Shift held in Wayland clients.
  -- kRejected stops other Rime processors without swallowing the physical key.
  return 0
end

return cycle
