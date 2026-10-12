# Rime with English Booster

Personal [Rime Ice](https://github.com/iDvel/rime-ice)-based configuration with
Chinese Pinyin, plain English, and a dedicated English Booster mode.

## Features

- Natural English typing: your typed word stays first, with suggestions appearing
  at four letters by default (configurable). Capitalization is preserved;
  each candidate page has five items.
- Word completion, including vocabulary you have explicitly saved.
- Verb forms: `force` offers `forced`, `forcing`, and `forces`.
- Up to three synonym suggestions, marked `≈`, for complete listed words.
- Spelling suggestions for simple typos, such as `forcng` → `forcing`;
  a `*` marks the literal spelling when corrections are available.
- Personal vocabulary: Ctrl+Enter saves a new alphabetic word for future completion.
- Automatic plain English after listed commands such as `git`, `emacs`, or
  `latexmk`, followed by Space or Enter.
- Emacs key passthrough for prefixes such as C-x, C-c, and Escape; C-g cancels input.
- Inline typing with a candidate-only popup in supported IBus applications.

These are dictionary-based suggestions, not contextual next-word prediction.
Synonym tables are optional local data: WordNet is the default source;
Merriam-Webster 2015 can be selected instead.

## Switching modes

Select English Booster with Ctrl + backtick, or tap Shift alone to cycle:

Pinyin → plain English → English Booster → plain English → Pinyin

Plain English has no prediction popup. Shift used with other keys remains a modifier.

## Input keys

| Key | Behavior while composing in English Booster |
| --- | --- |
| Space | Commit the highlighted candidate and add a space; the default keeps your typed word. |
| Tab | Accept a suggestion without a space; from the literal row, choose the next candidate. |
| 1–5 | Accept the corresponding candidate on the displayed page. |
| Return | Commit the typed text, even when another candidate is highlighted; no space or newline. |
| Ctrl+Enter | Save and commit the literal typed word, not a highlighted suggestion. |
| Ctrl+n / Ctrl+p | Move down / up through candidates. |
| Ctrl+Shift+n / Ctrl+Shift+p | Move to the next / previous candidate page. |

Unknown words are not saved automatically. Synonym selections do not teach
replacement aliases; learned English vocabulary remains separate from Pinyin.

## Detailed documentation

See [Implementation and configuration](IMPLEMENTATION.md) for installation,
schema settings, dictionary sources and cleanup, personal-data storage, and maintenance.
