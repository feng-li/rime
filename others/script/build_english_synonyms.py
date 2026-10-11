#!/usr/bin/env python3
"""Build a small offline Lua thesaurus from pinned local WordNet 3.0 files.

Only intact single-word synonyms from WordNet's selected part of speech are
included. Default: formal/general-writing vocabulary and usage screening, with
source-attested core-word review. --raw reproduces the original unfiltered table.
Usage pointers are read only to reject marked senses, never to add synonyms.
No generated forms, Merriam-Webster data, or network calls.
"""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from build_english_inflections import dictionary_words

PARTS = ("noun", "verb", "adj", "adv")
POS_NAMES = {"1": "noun", "2": "verb", "3": "adj", "4": "adv", "5": "adj"}
UNSUITABLE_DOMAINS = {"slang", "colloquialism", "archaism", "archaicism", "dialect",
                      "regionalism", "obscenity", "vulgarism", "ethnic_slur", "disparagement"}
USAGE_LABEL = re.compile(
    r"\b(?:archaic|obsolete|dated|slang|informal(?:ly)?|colloquial(?:ly)?|dialect(?:al)?|"
    r"regional|nonstandard|rare|poetic|literary|facetious|humorous|vulgar|offensive|"
    r"disparaging|derogatory)\b|old[- ]fashioned", re.I)
USAGE_PREFIX = re.compile(
    r"^(?:an? |the )?(?:archaic|obsolete|dated|slang|informal|colloquial|dialectal|"
    r"regional|nonstandard|rare|poetic|literary|facetious|humorous|vulgar|offensive|"
    r"disparaging|derogatory|old[- ]fashioned)(?:\s+(?:terms?|words?|expressions?|"
    r"names?|forms?|usage|for)\b|\s*[:,;-])", re.I)
SHA256 = {
    "index.adj": "c9865d7b4d1f805bdef82ccdcea5282436e23083e6f6f1b33e716327c4eda810",
    "index.adv": "6f5465ed5758fe9c8a2f7ec17b1300f3aa875756c70ff7cba162f7e71bcf88ea",
    "index.noun": "a490d99d93d017bf4822fe2f0ffa51fd73911ce271dc7535fade21f8814b5a04",
    "index.verb": "e2ac24816c3a8289dcb72aaa9cf8db81fdf25ec34d792bfc96ac5b7a20c8b4ae",
    "data.adj": "c89120dfc1f046ddff4a631bf9b7e9fa1a36b5e86565a23bf82dbe14f30b88a7",
    "data.adv": "444a63bf3955080ab7524f5079cfc07ff9bc682cb98bdb1db73b0fb9829f1139",
    "data.noun": "fea17d2f9656611334eac790e5d69e47645fa180c4aa481fb4cd9b3520754ca2",
    "data.verb": "adcf43e35b581e8036d8b5a52d63d9cd3d3b4870b2720d3c03c799df44777bc2",
    "cntlist.rev": "a198580b8f705fa02797bba8b13e5cbe4a9f9f40cb1697e774c7fc6a5865b035",
}


def index_entries(lines, vocabulary):
    result = {}
    for line in lines:
        if not line or line[0].isspace():
            continue
        fields = line.split()
        if fields[0] not in vocabulary:
            continue
        count, pointers = int(fields[2]), int(fields[3])
        offsets = fields[6 + pointers:]
        if len(offsets) != count:
            raise ValueError("Invalid WordNet index entry")
        result[fields[0]] = offsets
    return result


def synset_words(lines):
    result = {}
    for line in lines:
        if not line or line[0].isspace():
            continue
        fields = line.split("|", 1)[0].split()
        count = int(fields[3], 16)
        # Strip WordNet's adjective syntax markers, not part of the spelling.
        words = [re.sub(r"\((?:a|p|ip)\)$", "", fields[4 + 2 * i])
                 for i in range(count)]
        result[fields[0]] = words
    return result


def word_frequencies(lines):
    totals = defaultdict(int)
    for line in lines:
        key, _, count = line.split()
        word, suffix = key.split("%", 1)
        part = POS_NAMES[suffix[0]]
        count = int(count)
        totals[word, part] += count
    return totals


def synset_metadata(lines):
    result = {}
    for line in lines:
        if not line or line[0].isspace():
            continue
        body, gloss = line.split("|", 1)
        fields = body.split()
        count = int(fields[3], 16)
        start = 4 + 2 * count
        pointer_count = int(fields[start])
        pointers = [tuple(fields[start + 1 + 4 * i:start + 5 + 4 * i])
                    for i in range(pointer_count)]
        if any(len(pointer) != 4 for pointer in pointers):
            raise ValueError("Invalid WordNet pointer record")
        words = [re.sub(r"\((?:a|p|ip)\)$", "", fields[4 + 2 * i]) for i in range(count)]
        # Usage words occurring in quoted examples are not register labels.
        definition = re.split(r';\s*["`]', gloss.strip(), maxsplit=1)[0]
        result[fields[0]] = {"words": words, "definition": definition, "pointers": pointers}
    return result


def usage_rejections(metadata, noun_metadata):
    """Map None (whole synset) or a lemma to explicit register evidence."""
    reasons = defaultdict(set)
    definition = metadata["definition"]
    initial = re.match(r"^\(([^()]*)\)", definition)
    if (initial and USAGE_LABEL.search(initial[1])) or USAGE_PREFIX.search(definition):
        reasons[None].add("marked_usage_in_definition")
    # E.g. `tough' is occasionally used colloquially for `bad': mark tough,
    # not the other unmarked words sharing this synset.
    for match in re.finditer(r"[`']([A-Za-z]+)'\s+(?:is|are)\b([^`']*)", definition):
        if match[1].lower() in {w.lower() for w in metadata["words"]} and USAGE_LABEL.search(match[2]):
            reasons[match[1].lower()].add("marked_lexical_usage_in_definition")
    for symbol, offset, part, scope in metadata["pointers"]:
        if symbol != ";u" or part != "n":
            continue  # No synonym expansion through any semantic pointer.
        domain = noun_metadata[offset]["words"]
        target_index = int(scope[2:], 16)
        labels = domain if target_index == 0 else [domain[target_index - 1]]
        if not UNSUITABLE_DOMAINS.intersection(labels):
            continue  # Topic/region/formal/plural labels are not slang.
        source_index = int(scope[:2], 16)
        if source_index == 0 and any(word is not None for word in reasons):
            # WordNet sometimes attaches a coarse domain to the whole synset
            # but explicitly names only one informal variant in its gloss,
            # e.g. plain/plainly or whole/wholly. Prefer that narrower evidence.
            for lemma in list(reasons):
                if lemma is not None:
                    reasons[lemma].add("marked_usage_domain")
            continue
        word = None if source_index == 0 else metadata["words"][source_index - 1].lower()
        reasons[word].add("marked_usage_domain")
    return reasons


def synonym_table(indexes, synsets, totals, vocabulary, limit=3):
    senses = defaultdict(list)
    for priority, part in enumerate(PARTS):
        for word, offsets in indexes[part].items():
            for rank, offset in enumerate(offsets, 1):
                senses[word].append((-totals.get((word, part), 0),
                                     priority, rank, part, offset))
    result = {}
    for word, entries in sorted(senses.items()):
        if len(word) < 3:
            continue
        entries.sort()
        # Pick one part of speech using whole-word frequencies, then retain
        # that part's recorded index order. Do not assume cntlist.rev's sense
        # numbers align with this installation's indexes.
        part = entries[0][3]
        suggestions = []
        for _, _, _, sense_part, offset in entries:
            if sense_part != part:
                continue
            candidates = [text for text in synsets[part][offset]
                          if text in vocabulary and text != word]
            # Common alternatives first; stable source order breaks ties.
            candidates.sort(key=lambda text: -totals.get((text, part), 0))
            for text in candidates:
                if text not in suggestions:
                    suggestions.append(text)
                if limit is not None and len(suggestions) == limit:
                    break
            if limit is not None and len(suggestions) == limit:
                break
        if suggestions:
            result[word] = suggestions
    return result


def formal_table(indexes, synsets, metadata, totals, common_vocabulary, policy):
    entries = policy.get("entries")
    if not isinstance(entries, dict):
        raise ValueError("Review policy must contain an entries mapping")
    for word, choices in entries.items():
        if not re.fullmatch(r"[a-z]{3,}", word) or not isinstance(choices, list) or any(
                not isinstance(v, str) or not re.fullmatch(r"[a-z]+", v) or v == word for v in choices):
            raise ValueError(f"Invalid reviewed entry: {word}")
        if len(choices) != len(set(choices)):
            raise ValueError(f"Duplicate reviewed choice: {word}")
    allowed = common_vocabulary | {v for choices in entries.values() for v in choices}
    pools = synonym_table(indexes, synsets, totals, allowed, limit=None)
    blocked = {part: {offset: usage_rejections(record, metadata["noun"])
                      for offset, record in records.items()} for part, records in metadata.items()}
    result, audit = {}, []
    for word, choices in pools.items():
        part = min((-totals.get((word, p), 0), i, p)
                   for i, p in enumerate(PARTS) if word in indexes[p])[2]
        eligible, rejected = set(), defaultdict(set)
        for offset in indexes[part][word]:
            reasons = blocked[part][offset]
            for text in synsets[part][offset]:
                evidence = reasons.get(None, set()) | reasons.get(word, set()) | reasons.get(text.lower(), set())
                if evidence:
                    rejected[text].update(evidence)
                else:
                    eligible.add(text)
        if word in entries:
            for text in entries[word]:
                if text not in choices or text not in eligible:
                    raise ValueError(f"Reviewed choice lacks unmarked same-synset evidence: {word}/{text}")
        kept = []
        for text in choices:
            if text not in eligible:
                reasons = sorted(rejected[text])
            elif word in entries and text not in entries[word]:
                reasons = ["core_formal_sense_review"]
            else:
                kept.append(text)
                continue
            audit.append({"headword": word, "synonym": text, "reasons": reasons})
        if word in entries:
            kept.sort(key=entries[word].index)
        if kept:
            result[word] = kept[:3]  # Screen before the cap, never refill with a marked sense.
    return result, audit


def render(table, license_text, profile=None, policy_hash=None):
    lines = [
        "-- Offline English synonyms derived from WordNet 3.0.",
        "-- Source: https://wordnet.princeton.edu/download/current-version",
        "-- Regenerate with others/script/build_english_synonyms.py; do not hand-edit.",
        f"-- Complete words: {len(table)}; synonym pairs: {sum(map(len, table.values()))}.",
    ]
    if profile:
        lines += [f"-- Cleanup profile: {profile}; heuristic formal/general writing, not academic-corpus classification.",
                  f"-- Review policy SHA256: {policy_hash}",
                  "-- Same-synset evidence and usage labels checked before the three-candidate cap."]
    lines += [f"-- {name} SHA256: {digest}" for name, digest in sorted(SHA256.items())]
    lines += ["-- " + line for line in license_text.splitlines()]
    lines.append("return {")
    for word, synonyms in table.items():
        choices = ", ".join('"' + text + '"' for text in synonyms)
        lines.append('  ["' + word + '"] = {' + choices + '},')
    return "\n".join(lines + ["}", ""])


def write_audit(path, raw, cleaned, audit, dictionaries, policy_path, policy, license_text):
    repo = Path(__file__).resolve().parents[2]
    path = path.expanduser().resolve()
    if path.exists() or path.is_relative_to(repo):
        raise ValueError("Choose a new audit directory outside the Rime repository")
    before = {(word, text) for word, choices in raw.items() for text in choices}
    after = {(word, text) for word, choices in cleaned.items() for text in choices}
    reasons = {(r["headword"], r["synonym"]): r["reasons"] for r in audit}
    removed = [{"headword": w, "synonym": t, "reasons": reasons.get((w, t),
                ["outside_common_or_reviewed_vocabulary_or_final_cap"])} for w, t in sorted(before - after)]
    added = [{"headword": w, "synonym": t, "reason": "unmarked_same_synset_after_screening_or_review"}
             for w, t in sorted(after - before)]
    manifest = {"profile": policy["profile"], "counts": {"original_headwords": len(raw),
                "original_pairs": len(before), "cleaned_headwords": len(cleaned), "cleaned_pairs": len(after),
                "removed_original_pairs": len(removed), "added_source_attested_pairs": len(added),
                "screened_pool_rejections": len(audit)},
                "removal_reasons": dict(Counter(r for row in removed for r in row["reasons"])),
                "inputs": {"wordnet_sha256": SHA256, "review_policy_sha256": hashlib.sha256(policy_path.read_bytes()).hexdigest(),
                    "dictionaries": [{"path": str(p.resolve()), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in dictionaries]},
                "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "notes": ["Cleanup uses a common-word allowlist and explicit register evidence, not academic-corpus frequency.",
                          "Core policy is independently WordNet-derived; no private Merriam-Webster data are copied.",
                          "Filtering precedes the candidate cap, so better unmarked source-attested choices can replace excluded ones.",
                          "Only same-synset alternatives in the previously selected part of speech are allowed."]}
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".wordnet-cleanup-", dir=path.parent) as temporary:
        staging = Path(temporary)
        (staging / "wordnet_original.lua").write_text(render(raw, license_text), encoding="utf-8")
        (staging / "WordNet-LICENSE.txt").write_text(license_text, encoding="utf-8")
        (staging / "review_policy.json").write_bytes(policy_path.read_bytes())
        for name, value in [("manifest.json", manifest), ("removed.json", removed),
                            ("added.json", added), ("pool_rejections.json", audit)]:
            (staging / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        for file in staging.iterdir():
            file.chmod(0o600)
        if path.exists():
            raise ValueError("Audit directory appeared; refusing to overwrite")
        os.rename(staging, path)
    return manifest


def main():
    repo = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wordnet", type=Path, help="WordNet 3.0 database directory")
    parser.add_argument("--dictionary", type=Path, action="append", dest="dictionaries")
    parser.add_argument("--patch", action="store_true", help="Print an apply_patch patch instead of Lua")
    parser.add_argument("--raw", action="store_true", help="Reproduce the original unfiltered WordNet table")
    parser.add_argument("--policy", type=Path, default=repo / "others/english_synonyms/wordnet_formal_policy.json")
    parser.add_argument("--audit-dir", type=Path, help="Write original table, removal/addition audit and manifest to a new directory outside the repo")
    args = parser.parse_args()
    sources = {}
    for name, expected in SHA256.items():
        raw = (args.wordnet / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            parser.error(f"{name} does not match pinned WordNet 3.0 SHA256")
        sources[name] = raw.decode("ascii").splitlines()
    dictionaries = args.dictionaries or [
        repo / "en_dicts/en.dict.yaml", repo / "en_dicts/en_ext.dict.yaml",
        repo / "en_dicts/english_inflection_words.dict.yaml",
    ]
    vocabulary = dictionary_words(dictionaries)
    indexes = {part: index_entries(sources["index." + part], vocabulary) for part in PARTS}
    synsets = {part: synset_words(sources["data." + part]) for part in PARTS}
    totals = word_frequencies(sources["cntlist.rev"])
    raw_table = synonym_table(indexes, synsets, totals, vocabulary)
    policy = None
    if args.raw:
        if args.audit_dir:
            parser.error("--audit-dir requires the default cleanup profile, not --raw")
        table = raw_table
    else:
        try:
            policy = json.loads(args.policy.read_text(encoding="utf-8"))
            common = dictionary_words([repo / "en_dicts/en.dict.yaml", repo / "en_dicts/english_inflection_words.dict.yaml"])
            if args.dictionaries:
                common &= vocabulary
            metadata = {part: synset_metadata(sources["data." + part]) for part in PARTS}
            table, audit = formal_table(indexes, synsets, metadata, totals, common, policy)
        except (OSError, ValueError, KeyError) as error:
            parser.error(str(error))
    if not table:
        parser.error("No matching synonyms; check the dictionary inputs")
    license_text = (repo / "others/english_synonyms/WordNet-LICENSE.txt").read_text(encoding="utf-8")
    if args.audit_dir:
        try:
            report = write_audit(args.audit_dir, raw_table, table, audit, dictionaries,
                                 args.policy, policy, license_text)
        except (OSError, ValueError) as error:
            parser.error(str(error))
        print(json.dumps(report["counts"]), file=sys.stderr)
    generated = render(table, license_text, policy["profile"] if policy else None,
                       hashlib.sha256(args.policy.read_bytes()).hexdigest() if policy else None)
    if args.patch:
        path = repo / "en_dicts/wordnet_synonyms.lua"
        print("*** Begin Patch")
        if path.exists():
            print(f"*** Update File: {path}\n@@")
            for line in path.read_text(encoding="utf-8").splitlines():
                print("-" + line)
        else:
            print(f"*** Add File: {path}")
        for line in generated.splitlines():
            print("+" + line)
        print("*** End Patch")
    else:
        sys.stdout.write(generated)
    print(f"Generated {len(table)} words and {sum(map(len, table.values()))} synonym pairs.", file=sys.stderr)


if __name__ == "__main__":
    main()
