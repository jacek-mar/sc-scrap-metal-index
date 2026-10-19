import argparse
import sys
from .export import build


def main():
    parser = argparse.ArgumentParser(description='Unofficial static item data export')
    parser.add_argument('command', choices=['build', 'validate'])
    for arg in ['r013', 'r016', 'strings', 'gamedir']:
        parser.add_argument('--'+arg, required=True)
    args = parser.parse_args()
    try:
        accounts, all_rows, tables = build(args)
        if args.command == 'validate':
            from .validate import validate
            errors = validate(args, accounts, all_rows, tables)
            print(f'Validation: {len(errors)} failures')
            for error in errors:
                print(error)
            return bool(errors)
        print(f'Built {len(accounts)} account / {len(all_rows)} total rows')
        return 0
    except (ValueError, KeyError, OSError, TypeError) as exc:
        print(f'Export failed: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
