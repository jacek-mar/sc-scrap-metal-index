"""Command line entry point. CC0-1.0."""
import argparse
from collections import Counter
import json
import sys
from pathlib import Path
from . import FORMAT_VERSION, parse_file


def inside(path, parent):
    return path == parent or parent in path.parents


def export_main(argv=None):
    parser = argparse.ArgumentParser(description='Read Lua data statically; never execute it.')
    parser.add_argument('input', nargs='?', type=Path)
    parser.add_argument('--gamedir', type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args(argv)
    if (args.input is None) == (args.gamedir is None):
        parser.error('Specify either an input file/directory or --gamedir')
    root = (args.gamedir or args.input).resolve()
    output = args.out.resolve()
    if not root.exists():
        parser.error('Input does not exist')
    if args.gamedir:
        trees = [root / 'data/gamedata']
        platform = root / 'cloud/data/default_platform_config.lua'
        if not trees[0].is_dir() or not platform.is_file():
            parser.error('Game directory must contain gamedata and platform configuration')
        files = list(trees[0].rglob('*.lua')) + [platform]
    else:
        trees = [root] if root.is_dir() else [root.parent]
        files = list(root.rglob('*.lua')) if root.is_dir() else [root]
    if any(inside(output, tree.resolve()) for tree in trees) or (args.gamedir and inside(output, root)):
        parser.error('Output must be outside the input tree')
    base = root if root.is_dir() else root.parent
    jobs = []
    for path in sorted(files):
        if not inside(path.resolve(), base):
            parser.error('Input symlink escapes the selected input tree')
        relative = path.relative_to(base)
        destination = output / relative.with_suffix('.json')
        if not inside(destination.resolve(), output):
            parser.error('Output symlink escapes --out')
        if destination.exists() and destination.stat().st_nlink > 1:
            parser.error('Refusing to overwrite a hard-linked output')
        jobs.append((path, relative.as_posix(), destination))
    counts = Counter(files=0, assignments=0, warnings=0)
    categories = Counter()
    try:
        for path, label, destination in jobs:
            result = parse_file(path)
            result['file'] = label
            for warning in result['warnings']:
                warning['file'] = label
                categories[warning['code']] += 1
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2) + '\n', encoding='utf-8')
            counts.update(files=1, assignments=len(result['assignments']), warnings=len(result['warnings']))
    except OSError:
        parser.exit(2, 'Cannot write output\n')
    print(json.dumps(dict(counts, format_version=FORMAT_VERSION,
                          warning_categories=dict(categories)), sort_keys=True))
    return 1 if categories.get('input') else 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == 'validate':
        from .validation import main as validate_main
        return validate_main(argv[1:])
    if argv and argv[0] == 'compare':
        from .comparison import main as compare_main
        return compare_main(argv[1:])
    return export_main(argv)


if __name__ == '__main__':
    raise SystemExit(main())
