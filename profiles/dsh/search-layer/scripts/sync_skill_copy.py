#!/usr/bin/env python3
"""Compare or explicitly install the reviewed DSH search skill files. No pruning."""

import argparse
import hashlib
import os
import shutil
import tempfile
from pathlib import Path


# A positive release manifest, shared with the packaging check. A new file needs review
# before it travels. No arbitrary JSON, environment files, bytecode, or symlinks.
MANIFEST = tuple(sorted({
    'SKILL.md',
    *('references/' + name for name in ('authority-domains.json', 'dsh-adaptation.md',
        'grok-eval-cases.json', 'grok-provider-contract.md', 'intent-guide.md', 'research-light-regression-samples.md')),
    *('scripts/' + name + '.py' for name in ('chain_tracker', 'evaluate_grok', 'fetch_thread',
        'relevance_gate', 'runtime_config', 'search', 'sync_skill_copy', 'providers/__init__', 'providers/grok',
        'tests/test_dsh_search', 'tests/test_grok_provider')),
    *('scripts/tests/fixtures/' + name for name in ('action-sources.json', 'legacy-output-text.json',
        'missing-citations.json', 'nested-message.json', 'responses-stream.sse', 'top-level-output-text.json',
        'x-search-sources.json')),
}))


def validate_root(root):
    path = Path(os.path.abspath(root))
    if path.resolve() != path or path.name != 'search-layer' or path.exists() and not path.is_dir():
        raise ValueError('use a real search-layer directory, not a symlink')
    return path


def entry(root, relative):
    path = root / relative
    if path.resolve() != path or (path.exists() and not path.is_file()):
        raise ValueError(f'non-regular release entry: {relative}')
    return path


def compare(source, target):
    source, target = validate_root(source), validate_root(target)
    if source == target or source in target.parents or target in source.parents:
        raise ValueError('source and target must be separate skill trees')
    changes = []
    for relative in MANIFEST:
        src, dst = entry(source, relative), entry(target, relative)
        if not src.is_file():
            raise ValueError(f'incomplete release: {relative}')
        if not dst.exists():
            changes.append(('missing', relative))
        elif hashlib.sha256(src.read_bytes()).digest() != hashlib.sha256(dst.read_bytes()).digest():
            changes.append(('changed', relative))
    return changes


def synchronize(source, target):
    source, target = validate_root(source), validate_root(target)
    for _, relative in compare(source, target):
        src, dst = entry(source, relative), entry(target, relative)
        dst.parent.mkdir(parents=True, exist_ok=True)
        # Publish whole files; never overwrite through a link or delete target-only files.
        with tempfile.TemporaryDirectory(dir=dst.parent, prefix='.copy-') as work:
            tmp = Path(work) / 'entry'
            shutil.copyfile(src, tmp)
            tmp.chmod(0o644)
            tmp.replace(dst)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', required=True, type=Path)
    ap.add_argument('--target', required=True, type=Path)
    action = ap.add_mutually_exclusive_group()
    action.add_argument('--check', action='store_true', help='compare only (default)')
    action.add_argument('--apply', action='store_true', help='install only the reviewed release manifest')
    args = ap.parse_args()
    try:
        if args.apply:
            synchronize(args.source, args.target)
        changes = compare(args.source, args.target)
    except (OSError, ValueError) as exc:
        ap.exit(2, f'{exc}\n')
    for status, relative in changes:
        print(f'{status}:{relative}')
    if not changes:
        print(f'sync=ok files={len(MANIFEST)}')
    return int(bool(changes))


if __name__ == '__main__':
    raise SystemExit(main())
