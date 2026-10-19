"""Read-only scan of the current tracked tree (including staged new files)."""
import re
import subprocess
from pathlib import Path

PATTERNS = [
    r'[A-Za-z]:[\\/](?:Users|Program Files)',
    r'192\.0\.2\.\d+', r'test_user_\d+',
    r'mongodb(?:\+srv)?://', r'-----BEGIN [A-Z ]*PRIVATE KEY-----',
    r'\b(?:sk|ghp)[-_][A-Za-z0-9]{20,}',
    r'\bAKIA[A-Z0-9]{16}\b',
    r'"\$oid"\s*:\s*"[a-f0-9]{24}"',
]


def main():
    listing = subprocess.run(['git', 'ls-files', '-z'], check=True, capture_output=True).stdout
    hits = []
    paths = [Path(p.decode('utf-8')) for p in listing.split(b'\0') if p]
    for path in paths:
        text = path.read_text(encoding='utf-8')
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in PATTERNS):
            hits.append(path.as_posix())
    print(f'Tracked-data scan: {len(paths)} files; {len(hits)} flagged files.')
    for path in hits:
        print(path)
    return bool(hits)


if __name__ == '__main__':
    raise SystemExit(main())
