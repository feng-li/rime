-- One-edit spelling fallback; never replace normal dictionary suggestions.
local filter = {}
local alphabet = "abcdefghijklmnopqrstuvwxyz"

local function edits(word, visit)
  local seen = {[word] = true}
  local function try(code)
    if not seen[code] then
      seen[code] = true
      return visit(code)
    end
  end
  -- Prefer swapped or wrong letters before missing or extra letters.
  for i = 1, #word - 1 do
    if try(word:sub(1, i - 1) .. word:sub(i + 1, i + 1)
        .. word:sub(i, i) .. word:sub(i + 2)) then return end
  end
  for i = 1, #word do
    for j = 1, #alphabet do
      if try(word:sub(1, i - 1) .. alphabet:sub(j, j) .. word:sub(i + 1)) then return end
    end
  end
  for i = 1, #word + 1 do
    for j = 1, #alphabet do
      if try(word:sub(1, i - 1) .. alphabet:sub(j, j) .. word:sub(i)) then return end
    end
  end
  for i = 1, #word do
    if try(word:sub(1, i - 1) .. word:sub(i + 1)) then return end
  end
end

function filter.func(translation, env)
  local found = false
  for candidate in translation:iter() do
    found = true
    yield(candidate)
  end
  if found then return end -- Includes normal completions and personal words.
  local context = env.engine.context
  local input = context.input
  local segment = context.composition:back()
  if context:get_option("ascii_mode") or not segment or not segment:has_tag("abc")
      or segment.start ~= 0 or segment._end ~= #input
      or #input < 4 or #input > 24 or not input:match("^[A-Za-z]+$") then
    return
  end
  if not env.lookup then
    env.lookup = Memory(env.engine, env.engine.schema, "fuzzy")
  end
  local count, seen = 0, {}
  edits(input:lower(), function(code)
    if env.lookup:dict_lookup(code, false, 0) then
      for source in env.lookup:iter_dict() do
        -- Ignore abbreviation aliases, punctuation, and duplicate case forms.
        if source.text:lower() == code and not seen[code] then
          seen[code] = true
          local entry = DictEntry()
          entry.text = source.text
          -- Selection learns the correct spelling, never a typo alias.
          entry.custom_code = code .. " "
          local phrase = Phrase(env.lookup, "spelling", segment.start, segment._end, entry)
          local candidate = phrase:toCandidate()
          candidate.quality = -1
          yield(candidate)
          count = count + 1
          if count == 4 then return true end
        end
      end
    end
  end)
end

function filter.fini(env)
  if env.lookup then
    env.lookup:disconnect()
    env.lookup = nil
    collectgarbage("collect")
  end
end

return filter
