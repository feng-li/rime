#!/usr/bin/env python3
"""Build a bundled Rime verb-form table from a local AGID infl.txt file.

Only confirmed, alphabetic verbs from the supplied English dictionaries and
attested level 0/1 forms are included. There are no guessed suffix
rules, network calls, Hunspell bindings, or non-standard Python dependencies.
"""

import argparse
import hashlib
from pathlib import Path
import re
import sys

AGID_VERSION = "2016.01.19"
AGID_SHA256 = "df0c8f6edd4193d823abfad9e4ff6f42b4526211516649e1c73d4533aef749fa"
AGID_URL = "https://sourceforge.net/projects/wordlist/files/AGID/2016.01.19/agid-2016.01.19.tar.gz/download"
VERB = re.compile(r"^([a-z]+) V: (.*)$")
FORM = re.compile(r"^([a-z]+)([~<!?]*)(?:\s+(\d+(?:\.\d+)?))?(?:\s+\{[^}]+\})?$")


def dictionary_words(paths):
    words = set()
    for path in paths:
        in_entries = False
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip() == "...":
                in_entries = True
                continue
            if not in_entries or not line or line.startswith("#"):
                continue
            columns = line.split("\t")
            text = columns[0]
            code = columns[1] if len(columns) > 1 else text
            # Ignore abbreviations/aliases and properly capitalized names.
            if text == code and re.fullmatch(r"[a-z]+", text):
                words.add(text)
    return words


def verb_forms(lines, vocabulary):
    result = {}
    for line in lines:
        match = VERB.fullmatch(line.strip())
        if not match:
            continue
        base, groups = match.groups()
        if base not in vocabulary:
            continue
        forms = result.setdefault(base, [])
        for group in groups.split(" | "):
            for item in group.split(", "):
                match = FORM.fullmatch(item.strip())
                if not match:
                    continue
                word, tags, variant = match.groups()
                if tags or (variant and float(variant) >= 2):
                    continue
                if word != base and word not in forms:
                    forms.append(word)
    return {base: forms for base, forms in sorted(result.items()) if forms}


def render(forms, source_hash):
    count = sum(map(len, forms.values()))
    header = [
        "# Rime dictionary: verb forms looked up by the complete base word.",
        f"# Generated from AGID {AGID_VERSION}: {AGID_URL}",
        f"# infl.txt SHA256: {source_hash}",
        "# Copyright 2000-2016 by Kevin Atkinson; see others/english_inflections/AGID-README.txt.",
        "# Includes underlying WordNet and UK Advanced Cryptics Dictionary notices.",
        "# Regenerate with others/script/build_english_inflections.py; do not hand-edit.",
        f"# Confirmed verbs: {len(forms)}; base/form pairs: {count}.",
        "---",
        "name: english_inflections",
        'version: "2026-10-10.1"',
        "sort: by_weight",
        "use_preset_vocabulary: false",
        "...",
    ]
    rows = [f"{word}\t{base}\t0.001" for base, words in forms.items() for word in words]
    return "\n".join(header + rows) + "\n"


def render_words(forms, vocabulary, source_hash):
    words = sorted({word for values in forms.values() for word in values} - vocabulary)
    # Derivatives missing from the original word lists need ordinary spelling
    # entries too, so prefix completion works independently of base-form lookup.
    header = render({}, source_hash).split("\n...\n", 1)[0]
    header = header.replace("verb forms looked up by the complete base word.", "attested verb forms missing from the original word lists.")
    header = header.replace("Confirmed verbs: 0; base/form pairs: 0.", f"Additional word spellings: {len(words)}.")
    header = header.replace("name: english_inflections", "name: english_inflection_words")
    return header + "\n...\n" + "".join(f"{word}\t{word}\n" for word in words)


def main():
    repo = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("infl", type=Path, help="AGID 2016.01.19 infl.txt")
    parser.add_argument("--dictionary", type=Path, action="append", dest="dictionaries",
                        help="English .dict.yaml input; repeat for multiple files")
    parser.add_argument("--output", type=Path, help="Generated .dict.yaml; default: stdout")
    parser.add_argument("--words-output", type=Path, help="Also write new forms as ordinary spelling entries")
    args = parser.parse_args()
    raw = args.infl.read_bytes()
    source_hash = hashlib.sha256(raw).hexdigest()
    if source_hash != AGID_SHA256:
        parser.error("AGID input does not match the pinned 2016.01.19 infl.txt SHA256")
    paths = args.dictionaries or [repo / "en_dicts/en.dict.yaml", repo / "en_dicts/en_ext.dict.yaml"]
    vocabulary = dictionary_words(paths)
    forms = verb_forms(raw.decode("utf-8").splitlines(), vocabulary)
    if not forms:
        parser.error("no matching verb forms; check the dictionary inputs")
    generated = render(forms, source_hash)
    if args.output:
        args.output.write_text(generated, encoding="utf-8")
    else:
        sys.stdout.write(generated)
    if args.words_output:
        args.words_output.write_text(render_words(forms, vocabulary, source_hash), encoding="utf-8")
    print(f"Generated {len(forms)} verbs and {sum(map(len, forms.values()))} form pairs.", file=sys.stderr)


if __name__ == "__main__":
    main()
