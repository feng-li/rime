-- Offline, exact-word synonyms. No Memory/Phrase objects: selecting a synonym
-- must never teach the primary user dictionary an input -> replacement alias.
local translator = {}
local tables = {}

local function valid_words(words)
  if type(words) ~= "table" or next(words) == nil then return false end
  for code, choices in pairs(words) do
    if type(code) ~= "string" or #code < 3 or not code:match("^[a-z]+$")
        or type(choices) ~= "table" or #choices == 0 then
      return false
    end
    local count = 0
    for index, text in pairs(choices) do
      if type(index) ~= "number" or index < 1 or index % 1 ~= 0
          or type(text) ~= "string" or not text:match("^[a-z]+$") then
        return false
      end
      count = count + 1
    end
    if count ~= #choices then return false end -- Reject sparse/non-array lists.
  end
  return true
end

local function load_table(path)
  if not path or path == "" then return nil end
  if path:sub(1, 1) ~= "/" then
    path = rime_api.get_user_data_dir() .. "/" .. path
  end
  if tables[path] then return tables[path] end
  local ok, words = pcall(function()
    -- Exported data are table literals, not programs. The empty environment
    -- prevents access to Rime, files, subprocesses, or application globals.
    return assert(loadfile(path, "t", {}))()
  end)
  if ok and valid_words(words) then
    tables[path] = words -- Load once per resolved path, not on every Shift cycle.
    return words
  end
  return nil
end

local function load_words(config)
  local selected = config:get_string("synonyms/data_file")
  if selected and selected ~= "" then
    local words = load_table(selected)
    if words then return words end
    -- Do not expose private paths or dictionary content in diagnostics.
    log.warning("English Booster: selected synonym data unavailable or invalid; trying fallback")
  end
  local fallback = config:get_string("synonyms/fallback_file") or "en_dicts/wordnet_synonyms.lua"
  local words = load_table(fallback)
  if words then return words end
  -- A clean checkout has no local data tables; ordinary typing must still work.
  log.warning("English Booster: no usable synonym data; synonym suggestions disabled")
  return {}
end

function translator.init(env)
  local config = env.engine.schema.config
  env.limit = math.max(0, math.min(3, config:get_int("synonyms/max_candidates") or 3))
  env.quality = config:get_double("synonyms/initial_quality") or -0.85
  env.words = env.limit == 0 and {} or load_words(config)
end

function translator.func(input, segment, env)
  local context = env.engine.context
  if env.limit == 0 or context:get_option("ascii_mode")
      or not segment:has_tag("abc") or segment.start ~= 0
      or segment._end ~= #input or context.input ~= input
      or #input < 3 or not input:match("^[A-Za-z]+$") then
    return
  end
  local suggestions = env.words[input:lower()]
  if not suggestions then return end -- No prefix, stemming, or fuzzy lookup.
  for index = 1, math.min(env.limit, #suggestions) do
    local candidate = Candidate("synonym", segment.start, segment._end,
                                suggestions[index], "≈")
    -- Preserve the configured table's order without outranking verb forms.
    candidate.quality = env.quality - (index - 1) * 0.0001
    yield(candidate)
  end
end

return translator
