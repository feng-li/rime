# Rime with English Booster

Personal [Rime Ice](https://github.com/iDvel/rime-ice)-based configuration with
Pinyin, plain English input, and a dedicated English Booster schema. English
Booster predicts completions for the word being typed, offers verb forms and
spelling suggestions, remembers selected dictionary words, and lets you explicitly
save new vocabulary.

This is word completion with optional spelling suggestions, not contextual
next-word or sentence prediction. Unknown words are saved only when you explicitly
request it, not automatically during ordinary typing.

## Quick usage

- Select **English Booster** with Ctrl + backtick, or tap Shift to cycle through
  Pinyin, plain English, and English Booster.
- Type normally: Space preserves the typed word by default. Use Tab or a visible
  candidate number (1–5) when you want a completion.
- Type a complete verb base such as `force` to also see `forced`, `forcing`, and
  `forces`. The literal `force` remains first.
- When normal completion finds nothing, a typo such as `forcng` can offer
  `forcing`. Your typed spelling remains first; correction is never automatic.
- To remember a new alphabetic word, type it and press **Ctrl+Enter before Space
  or punctuation**. This commits and saves the literal word, without adding a
  space or newline. It is available for completion immediately and after restarts.

For example, type `mynewterm`, press Ctrl+Enter, then later type `mynew` and
press Tab to complete the saved word. Ordinary Space/Enter do not save unknown
words. See [Personal English dictionary](#personal-english-dictionary) for
storage, backups, and importing a word list.

## English completion

English Booster uses the existing [English word list](en_dicts/en.dict.yaml) and
[extended English word list](en_dicts/en_ext.dict.yaml). Its schema and learning
database are separate from Pinyin's.

The unchanged typed text is the default candidate, followed by completion
suggestions. Ordinary Space typing therefore does not accept a guessed word:
typing `I` followed by Space produces `I `, and typing `comput` followed by Space
preserves `comput `. Use Tab or a candidate number to request a completion.

Capitalization is preserved for literal input; title-case and uppercase prefixes
also produce appropriately capitalized completion candidates. English Booster
uses ASCII punctuation and shows up to five candidates per page.

### Verb forms

A bundled inflection dictionary offers related forms when you type a complete
verb base, including spelling changes and irregular verbs:

| Typed base | Additional candidates |
| --- | --- |
| `force` | `forced`, `forcing`, `forces` |
| `study` | `studied`, `studying`, `studies` |
| `stop` | `stopped`, `stopping`, `stops` |
| `run` | `ran`, `running`, `runs` |
| `go` | `went`, `gone`, `going`, `goes` |

The typed word remains first, so Space still commits `force ` rather than a
guessed form. Use Tab or a candidate number to choose a form; longer candidate
lists use the same five-item pages. Title-case and uppercase input work too.
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

### Spelling suggestions

When no normal dictionary or personal-word candidates exist, a small fuzzy
fallback offers up to four spelling suggestions: for example, `forcng` →
`forcing`, `comupter` → `computer`, and `recieve` → `receive`.
It handles one inserted, deleted, substituted, or adjacent-swapped letter in
alphabetic input of 4–24 characters. Normal completions are not mixed with
corrections, and the unchanged input always remains first. Space/Enter preserve
your spelling by default; use Tab, a candidate number, or navigation to choose
a correction. Selecting it learns the correct spelling, not a misspelled alias.

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

### Three input modes

Tap either Shift key alone to cycle:

Pinyin → plain English → English Booster → Pinyin

Shift used with letters or application shortcuts remains a normal modifier.
Switching with unfinished input retains already selected text and commits the
remaining typed characters, rather than accepting a guessed completion. Plain
English mode has no completion popup; English Booster is the predictive mode.

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
| [english_booster.dict.yaml](english_booster.dict.yaml) | Imports the existing English dictionaries. |
| [english_booster.inflections.dict.yaml](english_booster.inflections.dict.yaml) | Wrapper for the bundled base/form table. |
| [english_booster_inflections.schema.yaml](english_booster_inflections.schema.yaml) | Build-only dependency that compiles the inflection table; not a fourth input mode. |
| [en_dicts/english_inflections.dict.yaml](en_dicts/english_inflections.dict.yaml) | Generated verb forms indexed by their complete base. |
| [en_dicts/english_inflection_words.dict.yaml](en_dicts/english_inflection_words.dict.yaml) | Additional attested spellings for ordinary completion. |
| [lua/english_booster.lua](lua/english_booster.lua) | Natural typing, capitalization, numbered selection, and explicit word learning. |
| [lua/english_inflections.lua](lua/english_inflections.lua) | Read-only verb lookup with safe learning through the existing English user dictionary. |
| [lua/english_fuzzy.lua](lua/english_fuzzy.lua) | Bounded one-edit spelling fallback, only when normal completion finds nothing. |
| [lua/input_mode_cycle.lua](lua/input_mode_cycle.lua) | Shared three-way Shift cycle. |
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
```

These overrides do not edit the original `default.yaml` or
`rime_ice.schema.yaml`. The English schema already loads the shared Shift
processor.

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
