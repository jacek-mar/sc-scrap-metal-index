import argparse
from pathlib import Path
from .pipeline import run


def main():
    parser = argparse.ArgumentParser(description='Static account-item names from the two client string tables')
    parser.add_argument('command', choices=('build', 'validate'))
    parser.add_argument('--registry', required=True, type=Path)
    parser.add_argument('--strings', required=True, type=Path)
    parser.add_argument('--gamedir', required=True, type=Path)
    parser.add_argument('--wiki', type=Path)
    args = parser.parse_args()
    try:
        return run(args)
    except (OSError, ValueError, KeyError) as exc:
        # Input paths may contain personal directory names; do not echo them.
        print('Input/output error: ' + type(exc).__name__)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
