"""CC0-1.0. Compare two dist folders byte for byte; manifest generated_at is ignored.

Usage: python -m sc_smi_gen.compare <reference dist> <new dist>   (exit 0 = identical)
"""
import json
import sys
from pathlib import Path


def files(root):
    return {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}


def same(a, b, name):
    if name == 'data/manifest.json':
        x, y = (json.loads(p.read_text(encoding='utf-8')) for p in (a, b))
        x.pop('generated_at', None); y.pop('generated_at', None)
        return x == y
    return a.read_bytes() == b.read_bytes()


def compare(ref, new):
    ref, new = Path(ref), Path(new)
    left, right = files(ref), files(new)
    problems = [f'only in reference: {n}' for n in sorted(left - right)]
    problems += [f'only in new: {n}' for n in sorted(right - left)]
    problems += [f'differs: {n}' for n in sorted(left & right) if not same(ref / n, new / n, n)]
    return problems


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    problems = compare(*sys.argv[1:])
    print('\n'.join(problems) or f'Identical ({len(files(Path(sys.argv[1])))} files; generation date ignored).')
    raise SystemExit(1 if problems else 0)
