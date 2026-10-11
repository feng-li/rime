#!/usr/bin/env python3
"""Extract the local Merriam-Webster Collegiate Dictionary/Thesaurus 2015 MDX.

Exports private JSON data outside the repository. Does not modify the MDX,
replace Rime's synonym module, or deploy an input method. Dependencies for MDX
reading: mdict-utils and tqdm. HTML parsing uses only the standard library.
"""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import html
from html.parser import HTMLParser
import importlib.metadata
import json
import os
from pathlib import Path
import re
import sys
import tempfile

DEFAULT_MDX = Path.home() / ".emacs.d/dict/sdcv/Merriam-Webster's Collegiate Dictionary and Thesaurus, 2015.mdx"
THESAURUS = re.compile(r"<div\b[^>]*\bclass\s*=\s*([\"'])[^\"']*\bm3s\b[^\"']*\1", re.I)
DICTIONARY_SYNONYMS = re.compile(r"<dt\b[^>]*\bclass\s*=\s*([\"'])[^\"']*\bltp\b[^\"']*\1", re.I)
LABELS = {"tec": "synonyms", "a3d": "related_words", "ycv": "near_antonyms",
          "poy": "antonyms", "foa": "phrases"}
VOID = set("area base br col embed hr img input link meta param source track wbr".split())


class Node:
    __slots__ = ("tag", "attrs", "parent", "children")

    def __init__(self, tag, attrs=(), parent=None):
        self.tag, self.attrs, self.parent = tag, dict(attrs), parent
        self.children = []

    def has_class(self, name):
        return name in self.attrs.get("class", "").split()

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()


class EntryHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, text):
        self.stack[-1].children.append(text)


def plain_text(node, skip=None):
    if isinstance(node, str):
        return node
    if node is skip or node.tag in {"script", "style", "sup"} or node.has_class("bld"):
        return ""  # Dictionary sense superscripts and usage notes are not words.
    return "".join(plain_text(child, skip) for child in node.children)


def normalized(text):
    return " ".join(text.split()).strip()


def first_class(node, name):
    return next((item for item in node.walk() if item.has_class(name)), None)


def ancestor(node, name):
    node = node.parent
    while node:
        if node.has_class(name):
            return node
        node = node.parent
    return None


def unique(values):
    seen, result = set(), []
    for value in values:
        if value.casefold() not in seen:
            seen.add(value.casefold())
            result.append(value)
    return result


def split_terms(text):
    """Split list punctuation, not commas inside parentheses or usage markers."""
    parts, start, depth, annotation = [], 0, 0, False
    for index, char in enumerate(text):
        if char == '\x1e':
            annotation = True
        elif char == '\x1f':
            annotation = False
        elif not annotation:
            if char == '(':
                depth += 1
            elif char == ')':
                depth = max(0, depth - 1)
            elif char in ',;' and depth == 0:
                parts.append(text[start:index])
                start = index + 1
    return parts + [text[start:]]


def word_list(text):
    """Remove annotations, retaining explicitly marked also/or spelling variants."""
    # Ordinary parentheses contain usage notes; also/or parentheses name
    # alternatives. Split the alternatives into their own candidate words.
    def parenthesis(match):
        content = normalized(match.group(1))
        if re.match(r"^(?:also|or)\b", content, re.I):
            content = re.sub(r"^(?:also|or)\s+", "", content, flags=re.I)
            variants = re.split(r"\s+(?:also|or)\s+|[,;]", content, flags=re.I)
            return ", " + ", ".join(variants)
        if re.match(r"^(?:chiefly|especially|often|usually|sometimes|archaic|obsolete|"
                    r"slang|informal|formal|dialectal|rare|literary|poetic)\b", content, re.I):
            return ""
        # Particles such as "snuff (out)" are part of the expression. Keeping
        # them makes the alphabetic Lua export omit the whole phrase instead
        # of inventing the unrelated single-word synonym "snuff".
        return match.group(0)
    text = re.sub(r"\(([^()]*)\)", parenthesis, text)
    # Unrecognized brackets also stay intact rather than leaking fragments.
    values = split_terms(text)
    clean = []
    for value in values:
        value = normalized(value).lstrip("*|")
        if value and any(char.isalpha() for char in value):
            clean.append(value)
    return unique(clean)


def annotated_terms(node, skip=None):
    """Retain usage labels separately for an optional conservative review."""
    def render(item):
        if isinstance(item, str):
            return item
        if item is skip or item.tag in {"script", "style", "sup"}:
            return ""
        if item.has_class("bld"):
            text = normalized(''.join(plain_text(child) for child in item.children))
            return '\x1e' + text + '\x1f'
        return ''.join(render(child) for child in item.children)
    terms = []
    for part in split_terms(render(node)):
        labels = re.findall('\x1e(.*?)\x1f', part, flags=re.S)
        text = re.sub('\x1e.*?\x1f', '', part, flags=re.S)
        for word in word_list(text):
            terms.append({"text": word, "labels": labels})
    return terms


def parse_entry(key, record, dictionary_fallback=False, with_usage=False):
    body = record.split("\x00", 1)[0]
    start = THESAURUS.search(body)
    if not start and (not dictionary_fallback or not DICTIONARY_SYNONYMS.search(body)):
        return []
    parser = EntryHTML()
    parser.feed(body[start.start():] if start else body)
    parser.close()
    roots = [node for node in parser.root.walk() if node.has_class("m3s")]
    groups = []
    if roots:
        for root in roots:
            headword, part = key, ""
            owners = {}
            for node in root.walk():
                if node.has_class("iye"):
                    headword = normalized(plain_text(node)) or key
                if node.has_class("eyx"):
                    part = normalized(plain_text(node))
                category = next((value for cls, value in LABELS.items() if node.has_class(cls)), None)
                if not category or not node.parent:
                    continue
                # The class AND heading must agree; ignore unrelated markup.
                if normalized(plain_text(node)).casefold().rstrip(":") != category.replace("_", " "):
                    raise ValueError(f"Unexpected thesaurus label in entry {key!r}")
                owner = ancestor(node, "xsx") or ancestor(node, "muj") or node.parent
                group_key = (id(owner), headword, part)
                if group_key not in owners:
                    sense = ancestor(node, "muj")
                    number = first_class(sense, "n6n") if sense else None
                    definition = first_class(owner, "ltr")
                    group = {"headword": headword, "part_of_speech": part,
                             "sense": normalized(plain_text(number)) if number else "",
                             "definition": normalized(plain_text(definition)) if definition else "",
                             "source_section": "thesaurus"}
                    owners[group_key] = group
                    groups.append(group)
                words = word_list(plain_text(node.parent, skip=node))
                group = owners[group_key]
                group[category] = unique(group.get(category, []) + words)
                if with_usage and category == "synonyms":
                    group.setdefault("synonym_terms", []).extend(annotated_terms(node.parent, skip=node))
    elif dictionary_fallback:
        headword, part = key, ""
        for node in parser.root.walk():
            if node.has_class("iye"):
                headword = normalized(plain_text(node)) or key
            if node.has_class("eyx"):
                part = normalized(plain_text(node))
            if node.tag != "dl":
                continue
            label = next((child for child in node.children
                          if isinstance(child, Node) and child.tag == "dt" and child.has_class("ltp")), None)
            if not label or normalized(plain_text(label)).casefold().rstrip(":") != "synonyms":
                continue
            definitions = [child for child in node.children if isinstance(child, Node) and child.tag == "dd"]
            words = unique([word for child in definitions for word in word_list(plain_text(child))])
            if words:
                groups.append({"headword": headword, "part_of_speech": part,
                               "sense": "", "definition": "", "source_section": "dictionary_synonyms",
                               "synonyms": words})
    return [group for group in groups if any(group.get(category) for category in LABELS.values())]


def add_synonyms(table, groups):
    for group in groups:
        key = group["headword"].casefold()
        words = [word for word in group.get("synonyms", []) if word.casefold() != key]
        if words:
            table[key] = unique(table.get(key, []) + words)


def lua_data(table, source_hash):
    # Keep all eligible synonyms here; the Rime translator applies its own cap.
    rows = {}
    for word, synonyms in sorted(table.items()):
        if len(word) >= 3 and re.fullmatch("[a-z]+", word):
            choices = unique([item.lower() for item in synonyms if re.fullmatch("[A-Za-z]+", item)
                              and item.lower() != word])
            if choices:
                rows[word] = choices
    lines = ["-- Private local Merriam-Webster MDX export. Do not redistribute without permission.",
             f"-- MDX SHA256: {source_hash}",
             "-- Not installed automatically. Source order retained; not contextual prediction.", "return {"]
    for word, choices in rows.items():
        lines.append(f"  [{json.dumps(word)}] = {{{', '.join(json.dumps(item) for item in choices)}}},")
    return "\n".join(lines + ["}", ""]), len(rows)


def extract(source, output_dir, dictionary_fallback=False, rime_lua=False, progress=True):
    try:
        from mdict_utils.base.readmdict import MDX
        from tqdm import tqdm
    except ImportError as error:
        raise RuntimeError("Use a Python environment with mdict-utils and tqdm installed.") from error
    source, output_dir = source.expanduser().resolve(), output_dir.expanduser().resolve()
    if output_dir.exists():
        raise ValueError("Output directory already exists; choose a new one (no overwriting).")
    repo = Path(__file__).resolve().parents[2]
    if output_dir.is_relative_to(repo):
        raise ValueError("Keep private extracted dictionary data outside the Rime repository.")
    before = source.stat()
    with source.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    mdx = MDX(str(source))
    output_dir.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    stats, aliases, synonyms = Counter(), {}, {}
    with tempfile.TemporaryDirectory(prefix=".mw-thesaurus-", dir=output_dir.parent) as temporary:
        staging = Path(temporary)
        with (staging / "thesaurus.jsonl").open("x", encoding="utf-8") as stream:
            for index, (raw_key, raw_record) in enumerate(tqdm(
                    mdx.items(), total=len(mdx), desc="Extract thesaurus", unit="entry",
                    mininterval=1, disable=not progress)):
                key, record = raw_key.decode("utf-8"), raw_record.decode("utf-8")
                stats["records_read"] += 1
                if record.lstrip().startswith("@@@LINK="):
                    target = record.lstrip()[len("@@@LINK="):].split("\x00", 1)[0].strip()
                    aliases[key] = unique(aliases.get(key, []) + [target])
                    stats["redirect_records"] += 1
                    continue
                dedicated = bool(THESAURUS.search(record))
                if dedicated:
                    stats["dedicated_thesaurus_records"] += 1
                groups = parse_entry(key, record, dictionary_fallback)
                if not groups:
                    stats["records_without_extracted_groups"] += 1
                    if dedicated:
                        stats["thesaurus_records_without_lists"] += 1
                    continue
                stream.write(json.dumps({"entry_key": key, "record_index": index, "groups": groups},
                                        ensure_ascii=False) + "\n")
                stats["exported_entries"] += 1
                stats["groups"] += len(groups)
                if not dedicated:
                    stats["dictionary_fallback_entries"] += 1
                for group in groups:
                    for category in LABELS.values():
                        stats[category + "_terms"] += len(group.get(category, []))
                add_synonyms(synonyms, groups)
        if stats["records_read"] != len(mdx):
            raise ValueError("MDX reader did not yield every record; refusing an incomplete export.")
        if not stats["dedicated_thesaurus_records"] or not synonyms:
            raise ValueError("No recognized 2015 Merriam-Webster thesaurus layout found.")
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("MDX changed during extraction; refusing mixed-source output.")
        stats["synonym_headwords"] = len(synonyms)
        stats["synonym_pairs"] = sum(map(len, synonyms.values()))
        for name, values in [("synonyms.json", synonyms), ("aliases.json", aliases)]:
            with (staging / name).open("x", encoding="utf-8") as stream:
                json.dump(dict(sorted(values.items())), stream, ensure_ascii=False, indent=2)
                stream.write("\n")
        if rime_lua:
            data, count = lua_data(synonyms, digest)
            (staging / "english_synonyms_data.lua").write_text(data, encoding="utf-8")
            stats["rime_lua_headwords"] = count
        manifest = {"format_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                    "source": {"path": str(source), "bytes": before.st_size, "sha256": digest,
                               "title": html.unescape(mdx.header.get(b"Title", b"").decode("utf-8")),
                               "encoding": mdx.header.get(b"Encoding", b"").decode("utf-8"),
                               "mdx_entries": len(mdx)},
                    "extractor": {"script": Path(__file__).name,
                                  "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                                  "mdict_utils_version": importlib.metadata.version("mdict-utils"),
                                  "dictionary_fallback": dictionary_fallback, "rime_lua": rime_lua},
                    "counts": dict(stats),
                    "notes": ["Synonyms retain source sense/order; related words and antonyms stay separate.",
                              "Redirects are exported separately, not promoted to synonym headwords.",
                              "Private local dictionary export; not installed or redistributed automatically."]}
        (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                               encoding="utf-8")
        for path in staging.iterdir():
            path.chmod(0o600)
        if output_dir.exists():
            raise ValueError("Output directory appeared during extraction; refusing to overwrite it.")
        os.rename(staging, output_dir)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mdx", nargs="?", type=Path, default=DEFAULT_MDX)
    parser.add_argument("--output-dir", type=Path, required=True, help="New private directory outside the repo")
    parser.add_argument("--dictionary-fallback", action="store_true", help="Also use explicitly labeled dictionary Synonyms fields when no thesaurus section exists")
    parser.add_argument("--rime-lua", action="store_true", help="Export an alphabetic Lua table; do not install it")
    parser.add_argument("--no-progress", action="store_true")
    args = parser.parse_args()
    try:
        result = extract(args.mdx, args.output_dir, args.dictionary_fallback, args.rime_lua, not args.no_progress)
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"Extraction failed: {error}\n")
    print(json.dumps({"output_dir": str(args.output_dir.expanduser().resolve()), "counts": result["counts"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
