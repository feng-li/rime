-- Only loaded by the dedicated English Booster schema.
local function processor(key, env)
  local context = env.engine.context
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
  for candidate in translation:iter() do
    local text = candidate.text
    if upper then
      text = text:upper()
    elseif title then
      text = text:gsub("^%l", string.upper)
    end
    if literal_first then
      literal_first = false
      -- Keep a genuine exact match when available so it can still be learned.
      -- Otherwise offer the literal text before any predicted completion.
      if text ~= input then
        yield(Candidate("literal", candidate.start, candidate._end, input, ""))
      end
    end
    if text ~= candidate.text then
      yield(ShadowCandidate(candidate, candidate.type, text, candidate.comment))
    else
      yield(candidate)
    end
  end
end

return {processor = processor, case_filter = case_filter}
