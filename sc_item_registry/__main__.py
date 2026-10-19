import argparse
from pathlib import Path
from .registry import build


def main():
    parser = argparse.ArgumentParser(description='Read-only static item registry')
    parser.add_argument('command', choices=['build', 'validate'])
    for flag in ('gamedir', 'strings', 'db'): parser.add_argument('--' + flag, type=Path, required=True)
    parser.add_argument('--wiki', type=Path)
    args = parser.parse_args()
    for key in ('gamedir', 'strings', 'db'):
        if not getattr(args, key).is_dir(): parser.error(key + ' must be a readable directory')
    for root in [args.gamedir, args.strings, args.db, args.wiki]:
        if root and Path.cwd().resolve().is_relative_to(root.resolve()): parser.error('Run from the task repository, outside input directories')
    checks = build(args)
    for name, passed in checks.items(): print(('PASS ' if passed else 'FAIL ') + name)
    return int(args.command == 'validate' and not all(checks.values()))


if __name__ == '__main__': raise SystemExit(main())
