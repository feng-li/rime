#!/usr/bin/env python3
"""Screen every private MW synonym row for a general academic-writing profile.

Rechecks the original MDX for intact single-word evidence and usage labels.
Preserves the raw export and emits a fresh private table, full removal audit and
provenance manifest outside this repository. No runtime dependencies for Rime;
the one-time review uses mdict-utils and tqdm. This is not contextual prediction
or an exhaustive manual semantic review of every dictionary sense.
"""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import tempfile

from build_english_inflections import dictionary_words
from extract_mw_thesaurus import parse_entry, THESAURUS

WORD = re.compile(r"[a-z]+")
UNSUITABLE_USAGE = re.compile(
    r"\b(?:archaic|obsolete|dated|slang|informal|colloquial|dialect(?:al)?|regional|"
    r"nonstandard|rare|poetic|literary|facetious|humorous|vulgar|offensive|"
    r"disparaging|derogatory)\b|old[- ]fashioned", re.I)
SENSE_USAGE = re.compile(
    r"^(?:archaic|obsolete|dated|slang|informal|colloquial|dialect(?:al)?|regional|"
    r"nonstandard|rare|poetic|literary|facetious|humorous|vulgar|offensive|"
    r"disparaging|derogatory|old[- ]fashioned)\b", re.I)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_lua_table(path):
    """Validate every data line without executing any Lua code."""
    rows, lines, opened, closed = {}, {}, False, False
    for lineno, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip() or line.startswith('--'):
            continue
        if line == 'return {' and not opened:
            opened = True
            continue
        if line == '}' and opened and not closed:
            closed = True
            continue
        match = re.fullmatch(r'  \[("[a-z]+")\] = \{(.*)\},', line)
        if not opened or closed or not match:
            raise ValueError(f'Unexpected Lua data syntax at line {lineno}')
        word = json.loads(match[1])
        values = json.loads('[' + match[2] + ']')
        if word in rows or len(word) < 3 or not values or len(values) != len(set(values)):
            raise ValueError(f'Duplicate/invalid data row at line {lineno}')
        if any(not isinstance(v, str) or not WORD.fullmatch(v) or v == word for v in values):
            raise ValueError(f'Invalid synonym at line {lineno}')
        rows[word], lines[word] = values, lineno
    if not rows or not opened or not closed:
        raise ValueError('Incomplete/empty Lua data table')
    return rows, lines


def group_usage(group):
    return bool(UNSUITABLE_USAGE.search(group['part_of_speech']) or
                SENSE_USAGE.search(group['definition']))


def filter_table(raw, lines, eligible, source_rejections, vocabulary, policy):
    entries = policy.get('entries')
    if not isinstance(entries, dict):
        raise ValueError('Review policy must contain an entries object')
    for word, choices in entries.items():
        if not WORD.fullmatch(word) or not isinstance(choices, list) or len(choices) != len(set(choices)):
            raise ValueError(f'Invalid reviewed entry: {word}')
        for text in choices:
            if not isinstance(text, str) or text not in raw.get(word, []):
                raise ValueError(f'Reviewed choice is not an original direct synonym: {word}/{text}')
            if (word, text) not in eligible:
                raise ValueError(f'Reviewed choice has no unmarked intact evidence: {word}/{text}')
    # Explicitly reviewed formal terms may be absent from the common word list.
    reviewed_words = {text for choices in entries.values() for text in choices}
    allowed_words = vocabulary | reviewed_words
    cleaned, removals, counts = {}, [], Counter()
    for word, choices in raw.items():
        accepted = []
        for text in choices:
            pair = word, text
            if pair not in eligible:
                reasons = sorted(source_rejections.get(pair, {'no_intact_single_word_evidence'}))
            elif word in entries and text not in entries[word]:
                reasons = ['manual_academic_sense_review']
            elif text not in allowed_words:
                reasons = ['outside_common_or_reviewed_academic_vocabulary']
            else:
                accepted.append(text)
                continue
            removals.append({'line': lines[word], 'headword': word, 'synonym': text, 'reasons': reasons})
            counts.update(reasons)
        if word in entries:
            accepted.sort(key=entries[word].index)
        if accepted:
            cleaned[word] = accepted
    return cleaned, removals, dict(counts)


def render(table, mdx_hash, raw_hash):
    lines = ['-- Private Merriam-Webster academic-writing profile; do not redistribute.',
             f'-- MDX SHA256: {mdx_hash}', f'-- Raw Lua SHA256: {raw_hash}',
             '-- Every row screened; core policy entries manually reviewed. Not contextual prediction.',
             'return {']
    for word, values in sorted(table.items()):
        lines.append(f'  [{json.dumps(word)}] = {{{", ".join(json.dumps(v) for v in values)}}},')
    return '\n'.join(lines + ['}', ''])


def review(raw_dir, output_dir, policy_path, dictionaries, progress=True):
    from mdict_utils.base.readmdict import MDX
    from tqdm import tqdm

    raw_dir, output_dir, policy_path = [p.expanduser().resolve() for p in (raw_dir, output_dir, policy_path)]
    repo = Path(__file__).resolve().parents[2]
    if output_dir.exists() or output_dir.is_relative_to(repo):
        raise ValueError('Choose a new private output directory outside the Rime repository')
    manifest_path, lua_path = raw_dir / 'manifest.json', raw_dir / 'english_synonyms_data.lua'
    source_manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    source = Path(source_manifest['source']['path']).expanduser().resolve()
    before = source.stat()
    source_hash = digest(source)
    if source_hash != source_manifest['source']['sha256']:
        raise ValueError('MDX hash differs from the raw export manifest')
    raw, line_numbers = read_lua_table(lua_path)
    raw_hash = digest(lua_path)
    policy = json.loads(policy_path.read_text(encoding='utf-8'))
    vocabulary = dictionary_words(dictionaries)
    if not vocabulary:
        raise ValueError('Common-word vocabulary is empty')
    eligible, source_rejections, stats = set(), defaultdict(set), Counter()
    mdx = MDX(str(source))
    for raw_key, raw_record in tqdm(mdx.items(), total=len(mdx), desc='Review original thesaurus',
                                    unit='entry', mininterval=1, disable=not progress):
        stats['mdx_records_checked'] += 1
        record = raw_record.decode('utf-8')
        if not THESAURUS.search(record):
            continue
        for group in parse_entry(raw_key.decode('utf-8'), record, with_usage=True):
            word = group['headword'].casefold()
            if word not in raw:
                continue
            stats['sense_groups_checked'] += 1
            for term in group.get('synonym_terms', []):
                text = term['text'].lower()
                if not WORD.fullmatch(text):
                    base = re.match(r'^([a-z]+)\s*[\[(]', text)
                    if base and base[1] in raw[word]:
                        source_rejections[word, base[1]].add('parenthesized_or_bracketed_expression')
                    continue
                if text not in raw[word]:
                    continue
                pair = word, text
                if group_usage(group):
                    source_rejections[pair].add('marked_nonacademic_sense')
                elif any(UNSUITABLE_USAGE.search(label) for label in term['labels']):
                    source_rejections[pair].add('marked_nonacademic_usage')
                else:
                    eligible.add(pair)
    after = source.stat()
    if stats['mdx_records_checked'] != len(mdx) or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('Incomplete review or MDX changed during review')
    cleaned, removed, reasons = filter_table(raw, line_numbers, eligible, source_rejections, vocabulary, policy)
    if not cleaned:
        raise ValueError('No suitable synonyms remain; refusing an empty profile')
    stats.update({'raw_headwords': len(raw), 'raw_pairs': sum(map(len, raw.values())),
                  'retained_headwords': len(cleaned), 'retained_pairs': sum(map(len, cleaned.values())),
                  'removed_pairs': len(removed), 'removed_headwords': len(raw) - len(cleaned),
                  'common_vocabulary_words': len(vocabulary),
                  'manually_reviewed_existing_headwords': len(raw.keys() & policy['entries'].keys()),
                  'reviewed_extra_academic_words': len({w for v in policy['entries'].values() for w in v} - vocabulary)})
    result = {'format_version': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
              'profile': policy.get('profile', 'academic'), 'counts': dict(stats), 'removal_reasons': reasons,
              'source': source_manifest['source'],
              'inputs': {'raw_manifest_sha256': digest(manifest_path), 'raw_lua_sha256': raw_hash,
                         'review_policy_sha256': digest(policy_path),
                         'vocabularies': [{'path': str(p.resolve()), 'sha256': digest(p)} for p in dictionaries]},
              'reviewer': {'script_sha256': digest(Path(__file__)),
                           'parser_sha256': digest(repo / 'others/script/extract_mw_thesaurus.py'),
                           'mdict_utils_version': importlib.metadata.version('mdict-utils')},
              'notes': ['Every raw Lua row and candidate checked; retained choices are a subset of the original direct synonyms.',
                        'Marked slang/informal/dialectal/archaic/obsolete/rare/poetic and offensive terms excluded.',
                        'An unmarked intact occurrence can retain a word that also has marked or phrasal occurrences.',
                        'Core policy headwords reviewed manually; all other entries screened by rules, not semantically certified.',
                        'Common-vocabulary membership is a heuristic, not a measured academic-corpus frequency.',
                        'Source sense order remains for non-policy entries; ambiguous meanings and grammar require user judgment.',
                        'Original MDX, raw export and live Rime are not modified by this script.']}
    output_dir.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix='.mw-academic-', dir=output_dir.parent) as temporary:
        staging = Path(temporary)
        (staging / 'english_synonyms_data.lua').write_text(render(cleaned, source_hash, raw_hash), encoding='utf-8')
        for name, value in [('synonyms.json', cleaned), ('academic_review.json', policy), ('manifest.json', result)]:
            (staging / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        with (staging / 'removed.jsonl').open('x', encoding='utf-8') as stream:
            for item in removed:
                stream.write(json.dumps(item, ensure_ascii=False) + '\n')
        for path in staging.iterdir():
            path.chmod(0o600)
        if output_dir.exists():
            raise ValueError('Output directory appeared; refusing to overwrite')
        os.rename(staging, output_dir)
    return result


def main():
    repo = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('raw_dir', type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--policy', required=True, type=Path, help='Private JSON entries mapping headwords to reviewed synonym lists')
    parser.add_argument('--dictionary', action='append', type=Path, dest='dictionaries')
    parser.add_argument('--no-progress', action='store_true')
    args = parser.parse_args()
    dictionaries = args.dictionaries or [repo / 'en_dicts/en.dict.yaml', repo / 'en_dicts/english_inflection_words.dict.yaml']
    try:
        result = review(args.raw_dir, args.output_dir, args.policy, dictionaries, not args.no_progress)
    except (OSError, ValueError, ImportError, RuntimeError) as error:
        parser.exit(1, f'Review failed: {error}\n')
    print(json.dumps({'output_dir': str(args.output_dir.expanduser().resolve()),
                      'counts': result['counts'], 'removal_reasons': result['removal_reasons']}, indent=2))


if __name__ == '__main__':
    main()
