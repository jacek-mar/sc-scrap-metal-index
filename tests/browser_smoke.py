"""Optional offline Chromium smoke check, stdlib only. Not a browser driver.

Run: python tests/browser_smoke.py --browser <BROWSER_EXE>
Profiles and DOM dumps stay in ignored out/. No installation or download.
"""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlencode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    out = root / 'out/browser-smoke'
    out.mkdir(parents=True, exist_ok=True)
    cases = [
        ('account', {}, ['14973 results · showing 200', 'data/items.js'], ['src="data/items_all.js"']),
        ('nebula', {'q': 'Nebula GS', 'itemKind': 'ship', 'item': 'Ship_Race1_S_T4_Glass'},
         ['Ship_Race1_S_T4_Glass', 'ship.lua:26711', '<dialog id="detail"', 'open=""'], ['Loading local details…']),
        ('shared', {'q': '224', 'itemKind': 'ship', 'item': 'Ship_Race3_L_T5_Mole'},
         ['This id is shared:', 'Ship_Race2_L_T5_Protozan'], ['Loading local details…']),
        ('russian', {'q': 'Кошмар Иерихона', 'lang': 'ru'},
         ['Jericho_dream', 'prefixed', 'Результатов: 1 · показано 1'], []),
        ('all', {'all': '1'}, ['19364 results · showing 200', 'src="data/items_all.js"'], []),
        ('ru-interface', {'lang': 'ru', 'q': 'Nebula GS', 'itemKind': 'ship', 'item': 'Ship_Race1_S_T4_Glass'},
         ['<html lang="ru">', 'Результатов:', '>Язык</span>', '<h3>Идентификация</h3>',
          '../docs/ru/using-the-search.md', 'каждый корабль также получает vessels[].vid'],
         ['Loading local details…', '<h3>Identity</h3>']),
    ]
    checks = {}
    for name, state, expected, absent in cases:
        # The cleanup target is a newly created profile strictly inside out/.
        # Crashpad may release a Windows profile file after Chrome exits.
        # Leave such files for the explicitly scoped post-run cleanup.
        with tempfile.TemporaryDirectory(prefix='profile-', dir=out, ignore_cleanup_errors=True) as tmp:
            assert Path(tmp).resolve().is_relative_to(out.resolve())
            url = (root/'dist/site/index.html').as_uri() + '#' + urlencode(state)
            result = subprocess.run([
                args.browser, '--headless', '--disable-gpu', '--no-first-run',
                '--disable-background-networking', '--disable-component-update',
                '--disable-sync', '--disable-default-apps', '--metrics-recording-only',
                '--user-data-dir=' + tmp, '--dump-dom', '--virtual-time-budget=6000', url,
            ], capture_output=True, timeout=60)
            dom = result.stdout.decode('utf-8', errors='replace')
            (out/(name+'.html')).write_text(dom, encoding='utf-8')
            (out/(name+'.log')).write_bytes(result.stderr)
            checks[name] = result.returncode == 0 and all(s in dom for s in expected) and all(s not in dom for s in absent)
    (out/'checks.json').write_text(json.dumps(checks, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(checks))
    return 0 if all(checks.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
