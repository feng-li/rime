-- Read-only inflection lookup; the main English translator handles learning.
local translator = {}

function translator.init(env)
  env.lookup = Memory(env.engine, env.engine.schema, "inflections")
  env.quality = env.engine.schema.config:get_double("inflections/initial_quality") or -0.75
end

function translator.func(input, segment, env)
  if not segment:has_tag("abc") or not input:match("^[A-Za-z]+$") then
    return
  end
  local code = input:lower()
  if not env.lookup:dict_lookup(code, false, 0) then
    return -- Only a complete, listed verb base triggers additional candidates.
  end
  for source in env.lookup:iter_dict() do
    local entry = DictEntry()
    entry.text = source.text
    -- Never pass another table's numeric syllable IDs to the main user dict.
    -- Explicit spelling lets it safely remember this base/form relationship.
    entry.custom_code = code .. " "
    local phrase = Phrase(env.lookup, "inflection", segment.start, segment._end, entry)
    local candidate = phrase:toCandidate()
    -- Below learned prefix completions (quality >= -0.5), but above ordinary
    -- static prefix completions (approximately -1). Personal choices still win.
    candidate.quality = env.quality
    yield(candidate)
  end
end

function translator.fini(env)
  if env.lookup then
    env.lookup:disconnect()
    env.lookup = nil
    collectgarbage("collect")
  end
end

return translator
