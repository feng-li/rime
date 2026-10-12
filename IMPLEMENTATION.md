# Implementation and configuration

Setup, dictionary processing, data provenance, and maintenance instructions for
this Rime configuration. See the [main README](README.md) for features and
everyday usage. Relative file paths and repository-local commands below refer to
the repository root.

## Contents

- [English completion and input behavior](#english-completion)
- [Candidate popup threshold](#candidate-popup-threshold)
- [Synonym suggestions](#synonym-suggestions)
- [WordNet cleanup](#wordnet-formalgeneral-writing-cleanup)
- [Merriam-Webster extraction](#extract-a-local-merriam-webster-mdx)
- [Choosing a local synonym dictionary](#choose-a-local-candidate-dictionary)
- [Academic-focused synonym profile](#academic-focused-synonym-profile)
- [Setup and frontend configuration](#enable-english-booster)
- [Personal vocabulary and imports](#personal-english-dictionary)
- [Regenerating verb data](#regenerate-the-bundled-verb-data)
- [Keeping learned data out of Git](#keep-configuration-separate-from-learned-data)

## English completion

English Booster uses the existing [English word list](en_dicts/en.dict.yaml) and
[extended English word list](en_dicts/en_ext.dict.yaml). Its schema and learning
database are separate from Pinyin's.

The candidate popup starts at four alphabetic letters by default; shorter input remains
inline without a popup. Once shown, the unchanged typed text is the default
candidate, followed by completion suggestions. Ordinary Space typing therefore
does not accept a guessed word:
typing `I` followed by Space produces `I `, and typing `comput` followed by Space
preserves `comput `. Use Tab or a candidate number to request a completion.

Capitalization is preserved for literal input; title-case and uppercase prefixes
also produce appropriately capitalized completion candidates. English Booster
uses ASCII punctuation and shows up to five candidates per page.

### Candidate popup threshold

The schema option `completion/min_length` controls when the English candidate
popup appears. Its default is `4`. To customize it, add the following entry to
the existing `patch:` mapping in `english_booster.custom.yaml`, then redeploy:

```yaml
patch:
  "completion/min_length": 4
```

Use `3` to restore the previous threshold, or a larger integer for a quieter
menu. The minimum is `1`; zero and negative values are treated as `1`. A missing
setting uses `4`. Keep other existing patch entries, such as synonym selection.

This is a popup threshold, not a restriction on typing or saving words. It
applies to completions, personal words, verb forms, synonyms, and spelling
suggestions; their individual dictionary lookup rules are unchanged. Short input
still commits naturally with Space or Return, and Ctrl+Enter can still save it.
Pinyin and plain English are unaffected.

### Verb forms

A bundled inflection dictionary offers related forms when you type a complete
verb base, including spelling changes and irregular verbs:

| Typed base | Additional candidates |
| --- | --- |
| `force` | `forced`, `forcing`, `forces` |
| `study` | `studied`, `studying`, `studies` |
| `stop` | `stopped`, `stopping`, `stops` |
| `run` | `ran`, `running`, `runs` |

The typed word remains first, so Space still commits `force ` rather than a
guessed form. Use Tab or a candidate number to choose a form; longer candidate
lists use the same five-item pages. Title-case and uppercase input work too.
The configured popup threshold also applies to verb forms: with the default
of four letters, bases such as `go`, `be`, and `run` do not open a candidate menu.
Set the threshold to `3` to show the listed forms for `run`.
Your learned completion preferences take priority over unselected verb forms.
Selecting a form updates the existing `english_booster.userdb/`, not a separate
learning database.

The data covers 4,043 existing verb bases and 12,422 base/form pairs, with 8,204
additional attested spellings for ordinary prefix completion. It comes from
[AGID 2016.01.19](https://wordlist.aspell.net/agid-readme/); uncertain entries,
unconfirmed verb classifications, and rare level-2 variants are excluded.
The verb lookup activates only at a complete listed base, not every short
prefix. Neither Hunspell nor Python is needed while typing.

This is a word-form lookup, not context-aware grammar correction. It does not
infer the intended meaning of ambiguous verbs or automatically conjugate a new
personal word saved with Ctrl+Enter. Such words retain ordinary completion until
they are included in the bundled inflection data.

### Synonym suggestions

Complete listed words can offer up to three offline thesaurus suggestions,
marked `≈` in the candidate menu. With the cleaned local WordNet data, `quick`
offers `fast` and `speedy`; `happy` offers `glad`. A local data override changes
these choices. Title-case and uppercase input produce matching capitalization.

Your typed word remains first. Space and Enter preserve it by default; a
candidate number selects the displayed synonym, or use Tab/navigation as with
ordinary completions. Learned completions and verb forms rank above synonyms;
ordinary static prefix completions rank below them. Synonyms use the configured
English popup threshold and the same five-item pages; the Shift cycle and
Chinese input are unchanged.

Selecting a synonym commits only its word, without the `≈` label. Synonym
selections do not update the personal dictionary or create replacement aliases:
choosing a synonym for `quick` will never teach Rime to replace `quick` with it.
Ctrl+Enter still saves the literal typed word, even with a synonym highlighted.

The cleaned WordNet table covers 8,592 complete words and 17,363 synonym pairs.
It is derived from [WordNet 3.0](https://wordnet.princeton.edu/), using same-synset,
lowercase alphabetic words from the main English vocabulary plus explicitly
reviewed formal terms. It picks one part of speech using whole-word usage counts,
screens usage labels, and follows source sense/frequency order unless a core word
has an explicit review policy. Screening occurs before the three-candidate cap.
Broader related-word and antonym links are not followed. The generator and
[license](others/english_synonyms/WordNet-LICENSE.txt) are included, but the two
local candidate tables in `en_dicts/` are Git-ignored (see below). Once a table is
installed, WordNet, Python, Hunspell, Qwen, and network access are not required
while typing. A fresh checkout without either table has no synonym suggestions;
ordinary English completion continues to work.

This is dictionary lookup, not context-aware prediction. Words with several
meanings may offer alternatives that do not fit your sentence. Not every word
has a synonym in this restricted table, and personal words saved with Ctrl+Enter
do not acquire synonyms automatically. Partial words and misspellings do not
trigger synonym lookup; their ordinary completion/correction behavior remains.

Set `synonyms/max_candidates` in `english_booster.schema.yaml` to `0` to disable,
or `1`/`2` for a smaller menu, then redeploy. The maximum remains three. To
rebuild the data from the pinned local WordNet 3.0 files:

```sh
python3 -B others/script/build_english_synonyms.py /usr/share/wordnet --patch | apply_patch
python3 -B -m unittest discover -s others/script/tests -p 'test_english_*.py'
```

The generator verifies source SHA256 hashes and produces reproducible Lua data.
Its `--patch` output writes the ignored `en_dicts/wordnet_synonyms.lua`, not a
module under `lua/`.
The Lua translator uses plain, non-learning candidates; it reads the selected
Lua data table once per path per process, starts no process, and makes no network
requests. Changes to a loaded table require redeployment.

#### WordNet formal/general-writing cleanup

The generator applies the same practical principles as the local Merriam-Webster
cleanup: neutral vocabulary, removal of explicitly marked informal/archaic uses,
and targeted review of core writing words. This is a **heuristic**, not a measured
academic-corpus classification or exhaustive semantic certification.

Its public [review policy](others/english_synonyms/wordnet_formal_policy.json) is
independently WordNet-derived; no private Merriam-Webster dictionary text or
synonym choices are imported. Reviewed alternatives must share an unmarked
WordNet synset with the input word in its selected part of speech. For example,
`important` offers `significant` and `crucial`, not `authoritative`; `support`
offers `corroborate`, `substantiate`, and `confirm`; the unrelated wine-flavor
alternative `robust` → `rich` is withheld.

The parser reads WordNet's [usage-domain pointers and lexical scope](https://wordnet.princeton.edu/documentation/wndb5wn)
and [usage pointer types](https://wordnet.princeton.edu/documentation/wninput5wn)
only to screen register, never to expand synonyms. Topic/region/formal/plural
domains are not blanket exclusions. When a coarse whole-synset tag has a gloss
explicitly identifying just one informal variant, only that variant is screened:
`plain` is not a reason to discard unmarked `plainly`/`evidently`, nor `whole` a
reason to discard `wholly`/`entirely`. Words found only in quoted examples do not
become usage labels. Compounds are excluded whole, not shortened into fragments.

The original 8,672-word/17,628-pair table remains reproducible with `--raw`.
Cleanup removes 381 original suggestions and introduces 116 unmarked,
source-attested alternatives after screening before the cap; it is not merely
deletion of the original top-three lists. The original table, removed/added pairs,
all rejected candidate-pool pairs, input hashes, policy, and license are saved in
`~/running/rime/wordnet-formal-20261011/` on this machine. Generated audit files
stay outside Git.

To regenerate with a fresh audit directory:

```sh
python3 -B others/script/build_english_synonyms.py /usr/share/wordnet \
  --audit-dir ~/running/rime/wordnet-formal-next --patch | apply_patch
```

To restore the original unfiltered WordNet table:

```sh
python3 -B others/script/build_english_synonyms.py /usr/share/wordnet --raw --patch | apply_patch
```

Redeploy after changing a table that is currently in use. This cleanup updates
the local WordNet fallback only; the active private Merriam-Webster override and its
exports are unchanged. Ordinary Space/Enter, `≈`, personal-word learning, and
Chinese input keep their existing behavior. WordNet's synonyms still differ
from Merriam-Webster's and require attention to sentence meaning and grammar.

#### Extract a local Merriam-Webster MDX

[extract_mw_thesaurus.py](others/script/extract_mw_thesaurus.py) extracts the
dedicated thesaurus section from the local **Merriam-Webster's Collegiate
Dictionary and Thesaurus, 2015.mdx**. It does not replace WordNet in Rime or
redeploy anything. The default input path is
`~/.emacs.d/dict/sdcv/Merriam-Webster's Collegiate Dictionary and Thesaurus, 2015.mdx`
(the directory is `dict`, not `dit`). You can also pass another MDX path as its
first argument.

Use Python 3.11 or newer with `mdict-utils` and `tqdm`. On this machine they are
already installed in `~/.virtualenvs/lsp/`:

```sh
~/.virtualenvs/lsp/bin/python -B \
  ~/.config/ibus/rime/others/script/extract_mw_thesaurus.py \
  --output-dir ~/running/rime/mw2015-thesaurus \
  --rime-lua
```

Choose a **new** output directory; existing directories are never overwritten.
Private dictionary exports must stay outside this repository. A progress bar
shows the scan, and output becomes visible only after successful extraction.
The output directory is private (`0700`), with files readable only by you (`0600`).

| Output | Contents |
| --- | --- |
| `thesaurus.jsonl` | Original entry keys, record indexes, sense definitions, parts of speech, and separately labeled synonyms, related words, near antonyms, antonyms, and phrases. |
| `synonyms.json` | Case-folded headword → all direct synonyms, deduplicated in source order; self-matches removed. |
| `aliases.json` | MDX redirects, kept separate rather than assigning base-word synonyms to derived forms. |
| `manifest.json` | Source path/SHA256, source and reader versions, extractor SHA256/options, and extraction counts. |
| `english_synonyms_data.lua` | Optional `--rime-lua` export: alphabetic words suitable for the existing Lua translator, retaining all eligible choices for later selection/ranking. Not installed automatically. |

Hyphens, multiword phrases, accents, and explicitly marked spelling variants
remain in the JSON. Usage annotations and sense superscripts are not candidate
words. Parenthesized particles, such as `snuff (out)`, stay attached to the
expression: the Lua export excludes the whole phrase instead of leaking the
bare word `snuff`. Only lists explicitly labeled **synonyms** populate the flat map; the
other categories are never merged into it. The grouped JSON retains meanings
and parts of speech; the flat map combines them and is not context-aware.

By default, dictionary-only Synonyms fields are excluded. Add
`--dictionary-fallback` to use those fields only when the entry has no dedicated
thesaurus section. Entries without explicit lists are skipped and counted in the
manifest. Redirects are not followed automatically, including inflected words.

The original local-file extraction was checked: 120,980 MDX records scanned, 22,249
entries exported, 39,638 sense groups, and 419,763 direct synonym pairs for 22,175
headwords. Fourteen dedicated sections contain no word lists. The optional Lua
table contains 20,054 alphabetic headwords. Extraction does not change source
files or live Rime data. These are private extracts from your local dictionary; do not commit
or redistribute them without permission.

#### Choose a local candidate dictionary

The two cleaned synonym tables live separately in the existing English
dictionary directory:

| Local file | Candidate source |
| --- | --- |
| `en_dicts/mw2015_synonyms.lua` | Merriam-Webster 2015, academic-focused profile; selected on this machine. |
| `en_dicts/wordnet_synonyms.lua` | WordNet 3.0, formal/general-writing profile; default fallback. |

Both paths are explicitly ignored by Git; neither table is committed. They
remain Lua lookup tables for `≈` synonym candidates, not ordinary completion
dictionaries imported by `english_booster.dict.yaml`. Raw exports and review
audits stay under `~/running/rime/`.

Choose the source in the local, Git-ignored `english_booster.custom.yaml`.
Merge into its existing `patch:` block rather than replacing other settings:

```yaml
patch:
  "synonyms/data_file": en_dicts/mw2015_synonyms.lua
```

To select WordNet explicitly, use `en_dicts/wordnet_synonyms.lua` instead, or
remove the patch line (or set it to `""`) to use the schema's default fallback.
Relative paths resolve from Rime's user directory, independently of the working
directory; absolute paths to external exports also remain supported.

Redeploy Rime after switching sources or updating a loaded table. If the selected
table cannot be read or is invalid, Rime logs a generic warning and tries
`synonyms/fallback_file`, which defaults to `en_dicts/wordnet_synonyms.lua`.
If both are missing, only synonym suggestions are disabled. The sources are
alternatives, not merged lists; keep their files separate. A fresh installation
must generate WordNet with the command above or install its own local export.
Do not force-add either ignored table or the private MDX to Git.

The Merriam-Webster export preserves dictionary order and combines senses and
parts of speech; it does **not** rank alternatives by everyday frequency or your
sentence. For example, `quick` currently offers `alacritous`, `alert`, and
`expeditious`, while `important` offers `big`, `consequential`, and `earthshaking`.
Those examples describe the raw export, not the academic-focused profile now
selected on this machine. They are the first three eligible synonyms, not
necessarily the best fit for your intended meaning. The `≈` label, literal-first
Space/Enter behavior, three-candidate limit, and personal-dictionary policy remain
unchanged.

#### Academic-focused synonym profile

[review_mw_synonyms.py](others/script/review_mw_synonyms.py) checks every raw Lua
row and candidate, then revisits the original MDX for usage labels and intact
single-word evidence. It generates a new private profile without overwriting the
MDX, the raw export, or the separate WordNet table.

The profile excludes candidates supported only by marked slang, informal,
dialectal, regional, archaic, obsolete, rare, poetic/literary, humorous, offensive,
or derogatory usages. It removes the bare-word remnants of parenthesized phrases.
An unmarked occurrence in another sense can retain the same word. For remaining
entries, the main English completion vocabulary is a practical common-word
allowlist, not an academic-corpus frequency measure.

A private `academic_review.json` additionally selects and orders alternatives
for 67 existing core writing headwords. These reviewed formal terms can extend
the allowlist: useful words such as `corroborate` should not disappear merely
because the basic completion dictionary lacks them. Every retained choice must
still be an original direct synonym with unmarked, intact source evidence.
Some ambiguous entries, including `this`, `simple`, and `solution`, are withheld
from synonym suggestions when the available alternatives are unsuitable for this
profile; ordinary completion and typing still work.

Examples of the first three suggestions:

| Typed word | Academic-focused alternatives |
| --- | --- |
| `quick` | `rapid`, `fast`, `swift` |
| `important` | `significant`, `substantial`, `major` |
| `show` | `demonstrate`, `reveal`, `display` |
| `assess` | `evaluate`, `appraise`, `rate` |
| `happy` | `pleased`, `satisfied`, `delighted` |

The checked profile retains 18,266 headwords and 172,635 pairs from 20,054 raw
headwords and 357,317 pairs. All 184,682 removals are logged in `removed.jsonl`
with the original Lua line, headword, candidate, and reasons. The output also
contains the cleaned `synonyms.json`, `english_synonyms_data.lua`, copied private
review policy, and `manifest.json` with input hashes, source provenance, counts,
and review limitations. The directory is `0700` and files are `0600`; none belong
in Git.

To reproduce or revise the profile, edit a copy of the private review policy and
choose a **new** output directory:

```sh
~/.virtualenvs/lsp/bin/python -B \
  ~/.config/ibus/rime/others/script/review_mw_synonyms.py \
  ~/running/rime/mw2015-thesaurus-20261010 \
  --policy ~/running/rime/mw2015-academic-20261011/academic_review.json \
  --output-dir ~/running/rime/mw2015-academic-next
```

Install the new Lua export as the ignored `en_dicts/mw2015_synonyms.lua` (back up
the previous table first), or point the local `synonyms/data_file` patch directly
to the new external file, then redeploy. To
restore the unfiltered Merriam-Webster table, point it back to
`~/running/rime/mw2015-thesaurus-20261010/english_synonyms_data.lua` using its
absolute path; use `""` to restore the local WordNet fallback.

This is an academic-oriented lexical screen, **not** manual semantic certification
of every pair. Only the core policy entries were reviewed manually; other entries
retain source order and may still mix meanings or parts of speech. Academic
alternatives are not universally interchangeable, particularly technical terms
such as statistical `significant` or `robust`; grammar and sentence context still
need your judgment. Suggestions never replace your word automatically.

Run the parser/export regressions with:

```sh
python3 -B -m unittest discover -s others/script/tests -p 'test_*.py'
```

### Spelling suggestions

When no normal dictionary or personal-word candidates exist, a small fuzzy
fallback offers up to four spelling suggestions: for example, `forcng` →
`forcing`, `comupter` → `computer`, and `recieve` → `receive`.
It handles one inserted, deleted, substituted, or adjacent-swapped letter in
alphabetic input of 4–24 characters. Normal completions are not mixed with
corrections, and the unchanged input always remains first. Space/Enter preserve
your spelling by default; use Tab, a candidate number, or navigation to choose
a correction. Selecting it learns the correct spelling, not a misspelled alias.

Adjacent-letter swaps and missing doubled letters are checked before other
edits, so `doted` offers `dotted` and `runing` offers `running` before the four
suggestion slots fill with substitutions. This priority rule applies to all
words, not a hardcoded exception list.

When corrections are available, the literal row displays a `*` hint in the
candidate menu, for example `comupter *`. This is display-only: the mark is never
inserted into your text or saved in the user dictionary. Recognized words,
ordinary prefixes, and saved personal words are not flagged; unknown words with
no one-edit correction are not flagged either.

This uses the bundled English dictionary, including the added verb spellings;
there is no Hunspell dependency or extra word list. It is not a full spellchecker:
multiple errors and corrections to unknown personal words are not supported.
Ctrl+Enter still explicitly saves your literal input, even when a correction is
offered.

### Input keys

| Key | Behavior in English Booster |
| --- | --- |
| Space | Confirm the highlighted candidate and add a space; the default candidate preserves what was typed. |
| Tab | Accept a completion without a trailing space; from the unchanged-text row, choose the next suggestion when available. |
| 1–5 | Confirm the matching candidate on the displayed page without inserting the digit. |
| Enter | Commit the literal input without accepting an unconfirmed completion. |
| Ctrl+Enter | Save the literal typed English word and commit it without a trailing space or newline. |
| Ctrl+n / Ctrl+p | Navigate the candidate list using Down / Up. |
| Ctrl+Shift+n / Ctrl+Shift+p | Move to the next / previous candidate page. |

Numbers without a matching displayed candidate remain normal text. Pure numeric
input is unchanged. To type an alphanumeric string such as `this1` literally,
type `this`, press Enter to commit it, then type `1`. Otherwise, when candidate 1
is displayed, `this` followed by `1` confirms that candidate. Ctrl, Alt, and Super
number shortcuts are passed to the application rather than selecting candidates.

### Shift cycle (four steps)

Tap either Shift key alone to cycle:

Pinyin → plain English → English Booster → plain English → Pinyin

Plain English appears twice: once with prediction disabled in the Pinyin schema,
and once with prediction disabled in the English Booster schema. From Booster,
the first Shift disables prediction; the next Shift returns to Pinyin. These are
still three input behaviors, with no additional schema or hidden cycle counter.

Shift used with letters or application shortcuts remains a normal modifier.
After switching modes, the processor rejects the Shift release back to the
frontend rather than consuming it. Both the physical press and release can
therefore pass through, avoiding a stuck Shift state in Wayland applications.
Switching with unfinished input retains already selected text and commits the
remaining typed characters, rather than accepting a guessed completion. Plain
English mode has no completion popup; English Booster is the predictive mode.

### Automatic plain English for commands

In either Pinyin or English Booster, type an exact command name from
[english_commands.yaml](english_commands.yaml), then press unmodified Space or
Enter. Rime commits the literal command and switches to the existing plain
English mode, with no prediction menu for the arguments or flags.

Space adds one space. Enter confirms the command without a newline; another
Enter, now in plain English, is passed to the application normally. The switch
does not submit a command or otherwise send an extra keypress. Plain English
remains active until you switch modes; tapping Shift returns to English Booster.
Automatic command switching continues to use the plain-English step immediately
before Booster, regardless of which predictive schema recognized the command.

Names are case-sensitive and matched against the entire composing input, not
prefixes or surrounding application text. `gi`, `emac`, and `Git` do not trigger
the default list. Ctrl+Enter still saves a word without switching, modified
Space/Enter are left alone, and a deliberately selected different candidate is
not replaced. Tab and numbered selections keep their existing behavior.

Edit the shared `command_mode/commands` list in `english_commands.yaml`, then
redeploy. Set it to `[]` to disable automatic switching. Use alphabetic command
names that can remain in the composition until Space/Enter. This is a simple
word-list rule, not terminal detection: a listed word also triggers in other
applications, so ordinary prose words such as `make`, `find`, and `cat` are
excluded by default.

### Emacs command-key passthrough

In both Pinyin and English Booster, `C-x`, `C-c`, and standalone Escape start a
temporary key-passthrough sequence. For example, `C-x b`, `C-c z`, and `ESC x`
reach the application as original keyboard events, without a prediction menu.
Configured nested prefixes such as `C-x r b`, `C-x 4 f`, and `C-x a i g` also
work. Normal input resumes after the command key; the schema and input mode do
not change. Holding or releasing Ctrl/Shift does not finish the sequence.

`C-g` cancels both pending IME input and the passthrough sequence, and reaches
Emacs directly. Escape discards unfinished composition before starting its
prefix. `C-x`/`C-c` retain already selected text and commit remaining literal
input first, using the same preservation policy as Shift cycling. Frontend
composition resets and schema changes clear pending prefix state.

This is a **Rime-wide rule**, not Emacs-window detection: it also applies in
other applications. Rime cannot inspect Emacs's active keymap or detect when a
custom command finishes. [emacs_keys.yaml](emacs_keys.yaml) therefore lists
prefixes, not every command. Add custom nested prefixes using Rime key names,
then redeploy. For example, add `Control+c p` if `C-c p` is your own prefix map;
its next key will also pass through. Common standard nested prefixes are bundled,
but arbitrary package-specific prefix trees are not inferred automatically.
Set `emacs_keys/prefixes` to `[]` to disable the rule, including the `C-g` reset.

## Enable English Booster

Use a Rime installation with the Lua plugin. This configuration has been checked
with IBus-Rime 1.6.0, librime 1.16.1, and `librime-plugin-lua` on Ubuntu. The Ubuntu
packages are:

```sh
sudo apt install ibus-rime librime-plugin-lua
```

For IBus-Rime, the user configuration directory is `~/.config/ibus/rime/`. Place
the repository's configuration there, or use an existing link to this checkout.
Preserve existing configuration and user dictionaries when changing that link.

The feature uses these source files:

| File | Purpose |
| --- | --- |
| [english_booster.schema.yaml](english_booster.schema.yaml) | Dedicated English completion schema and input keys. |
| [english_commands.yaml](english_commands.yaml) | Shared editable command names that enter plain English on Space/Enter. |
| [emacs_keys.yaml](emacs_keys.yaml) | Shared editable Emacs prefixes for temporary raw-key passthrough. |
| [english_booster.dict.yaml](english_booster.dict.yaml) | Imports the existing English dictionaries. |
| [english_booster.inflections.dict.yaml](english_booster.inflections.dict.yaml) | Wrapper for the bundled base/form table. |
| [english_booster_inflections.schema.yaml](english_booster_inflections.schema.yaml) | Build-only dependency that compiles the inflection table; not a fourth input mode. |
| [en_dicts/english_inflections.dict.yaml](en_dicts/english_inflections.dict.yaml) | Generated verb forms indexed by their complete base. |
| [en_dicts/english_inflection_words.dict.yaml](en_dicts/english_inflection_words.dict.yaml) | Additional attested spellings for ordinary completion. |
| [lua/english_booster.lua](lua/english_booster.lua) | Natural typing, capitalization, numbered selection, and explicit word learning. |
| [lua/english_inflections.lua](lua/english_inflections.lua) | Read-only verb lookup with safe learning through the existing English user dictionary. |
| [lua/english_synonyms.lua](lua/english_synonyms.lua) | Exact-word offline synonym candidates, without replacement learning. |
| `en_dicts/mw2015_synonyms.lua` | Local Merriam-Webster synonym candidate table; Git-ignored. |
| `en_dicts/wordnet_synonyms.lua` | Local WordNet synonym candidate table; Git-ignored and reproducible with the generator. |
| [others/script/build_english_synonyms.py](others/script/build_english_synonyms.py) | Reproducible table generator with pinned WordNet source hashes. |
| [others/script/extract_mw_thesaurus.py](others/script/extract_mw_thesaurus.py) | Private local MDX thesaurus export, preserving senses and relation categories; no automatic Rime installation. |
| [lua/english_fuzzy.lua](lua/english_fuzzy.lua) | Bounded one-edit spelling fallback, only when normal completion finds nothing. |
| [lua/input_mode_cycle.lua](lua/input_mode_cycle.lua) | Shared Shift cycle, exact-command mode switching, and Emacs-prefix passthrough. |
| `default.custom.yaml` | Adds English Booster to the schema list and disables the old binary Shift toggle. |
| `rime_ice.custom.yaml` | Enables the shared Shift processor in Pinyin. |
| `ibus_rime.custom.yaml` | Enables inline typing for the IBus frontend. |

The three `.custom.yaml` overrides may be absent from a fresh checkout because
the repository ignores local custom files by default. Create them from the
examples below if needed. If they already exist, merge these keys into the
existing `patch` mapping; do not replace unrelated settings or duplicate an
existing English Booster schema entry.

### Schema selection and Shift cycling

In `default.custom.yaml`:

```yaml
patch:
  "schema_list/@next":
    schema: english_booster
  "ascii_composer/switch_key/Shift_L": noop
  "ascii_composer/switch_key/Shift_R": noop
```

In `rime_ice.custom.yaml`:

```yaml
patch:
  "engine/processors/@before 0": lua_processor@*input_mode_cycle
  "command_mode":
    __include: english_commands:/command_mode
  "emacs_keys":
    __include: emacs_keys:/emacs_keys
```

These overrides do not edit the original `default.yaml` or
`rime_ice.schema.yaml`. The English schema already loads the shared Shift
processor and includes the same command and Emacs-prefix lists.

### Inline typing and candidate layout

In `ibus_rime.custom.yaml`:

```yaml
patch:
  "style/inline_preedit": true
```

This shows the typed characters in the application's text field, where inline
preedit is supported, leaving only candidates in the popup. It applies to both
English and Pinyin. Candidates remain horizontal for both schemas: IBus-Rime
1.6.0 reads orientation from a shared frontend setting, not a per-schema setting.
An English-only vertical layout is not implemented. See the
[IBus-Rime settings implementation](https://github.com/rime/ibus-rime/blob/1.6.0/rime_settings.c).

After configuring the files, choose **Deploy / 部署** in the IBus input-method
menu. Then press Ctrl + backtick to select **English Booster**, or use the Shift
cycle. Rime regenerates `build/` during deployment; edit source files and
overrides rather than generated files.

## Personal English dictionary

English Booster enables Rime's user dictionary:

```yaml
translator:
  user_dict: english_booster
  enable_user_dict: true
```

Confirming a dictionary-backed candidate records its usage. For example,
selecting `computer` for a prefix such as `comp` promotes it among future
completions. The unchanged typed-text row remains the default so learning does
not turn Space into automatic completion. Rime provides this through its
[selection memory](https://github.com/rime/librime/blob/1.16.1/src/rime/gear/memory.cc)
and [table translator](https://github.com/rime/librime/blob/1.16.1/src/rime/gear/table_translator.cc).

The learned data is stored locally in:

```text
~/.config/ibus/rime/english_booster.userdb/
```

This is a Rime-managed database, not a YAML word list. It persists across client
restarts and is separate from Pinyin's user database. Do not edit its internal
files or delete it when updating the schema. Pulling configuration changes from
Git does not transfer learned preferences to another machine. Use Rime's user
data synchronization or back up the database separately; stop the Rime frontend
before making a filesystem copy of a live database.

### Save unknown words explicitly (Ctrl+Enter)

Unknown words are saved explicitly, never just because they were typed. In
English Booster:

1. Type the complete new word, for example `mynewterm`.
2. Press **Ctrl+Enter** before Space or punctuation. Rime commits exactly the
   typed word and saves it, even if a different completion was highlighted.
   No space or newline is added.
3. Later, type a prefix such as `mynew` and use Tab or a candidate number to
   accept the saved word.

The word is written directly to `english_booster.userdb/`, so it is immediately
available and survives restarts without a dictionary edit or another deployment.
Its original spelling is retained, with lowercase, title-case, and uppercase
lookup forms for completion.

This shortcut saves alphabetic words (`A`-`Z` and `a`-`z`) while they are still
being composed. It does not read previously committed application text, and it
does not save emails, URLs, or punctuation-containing strings. Plain English
mode and Pinyin do not use this shortcut. Space and ordinary Enter still do
not add unknown words, avoiding automatic collection of drafts and typos.
Avoid using Ctrl+Enter on sensitive words you do not want stored locally.

### Import a personal word list

For predefined or bulk vocabulary, you can also use a source dictionary:

1. Create `en_dicts/english_personal.dict.yaml` with a dictionary header and
   tab-separated text and spelling entries:

   ```text
   ---
   name: english_personal
   version: "1"
   sort: by_weight
   ...
   myterm	myterm
   ```

   The separator between the two `myterm` fields must be a literal Tab.

2. Add `en_dicts/english_personal` to `import_tables` in
   `english_booster.dict.yaml`, keeping the existing imports:

   ```yaml
   import_tables:
     - en_dicts/english_personal
     - en_dicts/en_ext
     - en_dicts/en
     - en_dicts/english_inflection_words
   ```

3. Redeploy Rime, then select the new term as a candidate. Subsequent selections
   can personalize its ranking like other dictionary words.

The personal word-list file is not created by default. If it contains private
vocabulary, keep it out of Git and make sure it exists on each machine whose
schema imports it.

### Regenerate the bundled verb data

The generated dictionaries are included in Git; ordinary setup does not require
downloading data or running a generator. For maintenance, download the pinned
[AGID archive](https://sourceforge.net/projects/wordlist/files/AGID/2016.01.19/agid-2016.01.19.tar.gz/download),
extract `infl.txt`, then run from this repository:

```sh
python3 others/script/build_english_inflections.py /path/to/agid-2016.01.19/infl.txt \
  --output en_dicts/english_inflections.dict.yaml \
  --words-output en_dicts/english_inflection_words.dict.yaml
python3 -B -m unittest discover -s others/script/tests -p 'test_english_*.py'
```

The standard-library-only generator checks the source SHA256 and keeps only
confirmed alphabetic verbs whose bases appear in the original English word
lists. Redeploy Rime after regenerating the dictionaries. Required attribution,
source-format documentation, and license notices are preserved in
[AGID-README.txt](others/english_inflections/AGID-README.txt).

The offline tests also cover the fuzzy fallback using the installed Lua 5.4
runtime. They do not open or modify personal learning databases.

## Keep configuration separate from learned data

- Track the English schema, dictionary wrapper, Lua helpers, and any overrides you
want to share. 

- Keep `build/`, `sync/`, `*.userdb/`, `user.yaml`, and `installation.yaml` out of Git. They contain generated data, machine-specific state, or personal learning data.
