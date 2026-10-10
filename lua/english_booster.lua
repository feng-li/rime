-- Only loaded by the dedicated English Booster schema.
local function save_word(input, env)
  if not env.memory then
    env.memory = Memory(env.engine, env.engine.schema)
  end
  local memory = env.memory
  if not memory:start_session() then
    return false
  end
  -- Table user-dictionary lookup uses the literal spelling, not speller algebra.
  -- Index each case form so newly saved words also complete from capitalized
  -- prefixes; retain the original text (including names and internal capitals).
  local codes = {
    input, input:lower(), input:lower():gsub("^%l", string.upper), input:upper(),
  }
  local seen = {}
  for _, code in ipairs(codes) do
    if not seen[code] then
      seen[code] = true
      local entry = DictEntry()
      entry.text = input
      entry.custom_code = code .. " " -- Required user-dictionary word boundary.
      if not memory:update_userdict(entry, 1, "") then
        memory:discard_session()
        return false
      end
    end
  end
  return memory:finish_session()
end

local function processor(key, env)
  local context = env.engine.context
  if not key:release() and key.keycode == 0xff0d and key:ctrl()
      and not key:shift() and not key:alt() and not key:super()
      and not context:get_option("ascii_mode") and context:is_composing()
      and context.input:match("^[A-Za-z]+$") then
    local input = context.input
    local ok, saved = pcall(save_word, input, env)
    if not ok or not saved then
      if env.memory then
        pcall(function() env.memory:discard_session() end)
      end
      -- Never log the word itself: personal vocabulary may be sensitive.
      log.warning("English Booster: could not save the personal word")
    end
    -- Explicit learning is about the typed word, not a highlighted completion.
    context:clear()
    env.engine:commit_text(input)
    return 1 -- kAccepted: no newline and no trailing space.
  end
  if not key:release() and (key:ctrl() or key:alt() or key:super())
      and key.keycode >= 0x30 and key.keycode <= 0x39 then
    return 0 -- kRejected: modified digits belong to application shortcuts.
  end
  if key:release() or key:ctrl() or key:alt() or key:super()
      or context:get_option("ascii_mode") or not context:is_composing() then
    return 2 -- kNoop: leave application shortcuts and direct input alone.
  end
  if key.keycode == 0x20 then
    -- Commit through the context first so Rime learns the selected candidate.
    context:confirm_current_selection()
    context:commit()
    env.engine:commit_text(" ")
    return 1 -- kAccepted
  end
  if key.keycode == 0xff09 and context:get_selected_candidate() then
    -- The unchanged input is the default. Tab explicitly asks for completion.
    if context:get_selected_candidate().text == context.input then
      context:select(1) -- False if there is no additional candidate.
    end
    context:confirm_current_selection()
    context:commit() -- Tab completes the word; Space remains the separator.
    return 1
  end
  if key.keycode >= 0x30 and key.keycode <= 0x39 then
    local row = (key.keycode - 0x31 + 10) % 10 -- 1 is row 0; 0 is row 9.
    local page_size = env.engine.schema.config:get_int("menu/page_size") or 5
    local segment = context.composition:back()
    if row >= 0 and row < page_size and segment then
      local page_start = math.floor(segment.selected_index / page_size) * page_size
      if segment:get_candidate_at(page_start + row) then
        return 2 -- Let the standard selector confirm the displayed candidate.
      end
    end
    -- An unlisted number must not be swallowed or select an off-page word.
    context:confirm_current_selection()
    context:commit()
    return 2 -- With the composition closed, the digit reaches the application.
  end
  return 2
end

local function case_filter(translation, env)
  local input = env.engine.context.input
  local upper = #input > 1 and input:match("^[A-Z]+$")
  local title = input:match("^[A-Z][a-z]*$")
  local literal_first = input:match("^[A-Za-z]+$")
  local pending = {}
  for candidate in translation:iter() do
    local text = candidate.text
    if upper then
      text = text:upper()
    elseif title then
      text = text:gsub("^%l", string.upper)
    end
    local converted = candidate
    if text ~= candidate.text then
      converted = ShadowCandidate(candidate, candidate.type, text, candidate.comment)
    end
    if literal_first then
      if text == input then
        -- Keep the genuine base word first even when inflections rank higher.
        -- Ordinary Space can then still learn a real dictionary entry.
        yield(converted)
        for _, saved in ipairs(pending) do yield(saved) end
        pending = {}
        literal_first = false
      elseif candidate.type == "completion" then
        -- Exact matches precede prefix completions. If none matched the input,
        -- retain its literal spelling before the buffered choices and guesses.
        yield(Candidate("literal", candidate.start, candidate._end, input, ""))
        for _, saved in ipairs(pending) do yield(saved) end
        pending = {}
        yield(converted)
        literal_first = false
      else
        pending[#pending + 1] = converted
      end
    else
      yield(converted)
    end
  end
  if literal_first and #pending > 0 then
    local first = pending[1]
    yield(Candidate("literal", first.start, first._end, input, ""))
    for _, saved in ipairs(pending) do yield(saved) end
  end
end

local function fini(env)
  if env.memory then
    env.memory:disconnect()
    env.memory = nil
    collectgarbage("collect")
  end
end

return {processor = {func = processor, fini = fini}, case_filter = case_filter}
