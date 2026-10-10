-- Tap either Shift: Pinyin -> plain English -> English Booster -> Pinyin.
-- A Shift used with any other key is only a modifier, never a mode switch.
local cycle = {}

function cycle.init(env)
  env.pending_shift = nil
end

function cycle.func(key, env)
  local code = key.keycode
  if code ~= 0xffe1 and code ~= 0xffe2 then -- Shift_L / Shift_R
    env.pending_shift = nil
    return 2 -- kNoop
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

  if schema_id == "english_booster" then
    engine:apply_schema(Schema("rime_ice"))
    context:set_option("ascii_mode", false)
  elseif was_ascii then
    engine:apply_schema(Schema("english_booster"))
    context:set_option("ascii_mode", false)
  else
    context:set_option("ascii_mode", true)
  end
  return 1 -- kAccepted: do not let the old two-way toggle run as well.
end

return cycle
