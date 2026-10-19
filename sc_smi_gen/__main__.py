"""CC0-1.0. Rebuild the SC Scrap Metal Index from your own Star Conflict install.

    python -m sc_smi_gen [--gamedir DIR] [--out DIR] [--no-sample]

Reads the install only (no network, no game code is run). Steps: find the
install, unpack the two string tables from data/strings.pak, run the item
registry (013), the item names (016) and the export with the search site
(017). The result is <out>/dist; intermediate files are in <out>/work.
"""
import argparse
import os
import shutil
import sys
import io
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from types import SimpleNamespace

from . import steam
from .tpak import PakError, extract_strings

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = Path(__file__).resolve().parent / 'sample'
REQUIRED = ('data/strings.pak', 'data/gamedata/def/ex/ship.lua', 'cloud/data/store.xml')


class GenError(Exception):
    pass


@contextmanager
def inside(folder):
    folder.mkdir(parents=True, exist_ok=True)
    previous = Path.cwd()
    os.chdir(folder)
    try:
        yield
    finally:
        os.chdir(previous)


def say(text):
    print(text, flush=True)


def find_gamedir(given):
    if given:
        gamedir = Path(given)
    else:
        found = steam.find_install()
        if not found:
            raise GenError('Star Conflict was not found in your Steam libraries. Pass the folder: --gamedir "<path to star conflict>"')
        gamedir = found
        say(f'Found the game: {gamedir}')
    missing = [p for p in REQUIRED if not (gamedir / p).is_file()]
    if missing:
        raise GenError('This folder does not look like a Star Conflict install (missing ' + ', '.join(missing) +
                       '). Pass the folder that contains "data" and "cloud".')
    return gamedir.resolve()


def empty_db(folder):
    (folder / 'atlas_ids').mkdir(parents=True, exist_ok=True)
    (folder / 'atlas_ids' / 'ids.json').write_text('', encoding='utf-8')
    return folder


def run(args):
    gamedir = find_gamedir(args.gamedir)
    out = Path(args.out).resolve()
    if out == gamedir or gamedir in out.parents:
        raise GenError('Choose an output folder outside the game folder.')
    work = out / 'work'
    if work.exists():
        shutil.rmtree(work)
    os.environ['READER'] = str(ROOT)  # the registry imports the bundled reader from here
    sys.path.insert(0, str(ROOT))

    say('1/4 Unpacking the string tables from data/strings.pak')
    strings = work / 'strings'
    try:
        extract_strings(gamedir / 'data/strings.pak', strings)
    except PakError as error:
        raise GenError(f'Cannot read data/strings.pak: {error}. Verify the game files in Steam and try again.')

    db = empty_db(work / 'no-sample') if args.no_sample else SAMPLE
    say('2/4 Reading item definitions (this takes a few minutes)')
    from sc_item_registry.registry import build as registry_build
    with inside(work / '013'):
        checks = registry_build(SimpleNamespace(gamedir=gamedir, strings=strings, db=db, wiki=None))
    differs = [name for name, ok in checks.items() if not ok]

    say('3/4 Resolving item names')
    from sc_item_names.pipeline import run as names_run
    with inside(work / '016'), redirect_stdout(io.StringIO()):  # its review diagnostics are for maintainers
        names_run(SimpleNamespace(command='build', registry=work / '013' / 'results', strings=strings,
                                  gamedir=gamedir, wiki=None))

    say('4/4 Writing the data files and the search site')
    from sc_smi_export.export import build as export_build
    with inside(out):
        if (out / 'dist').exists():
            shutil.rmtree(out / 'dist')
        accounts, all_rows, _ = export_build(SimpleNamespace(r013=str(work / '013'), r016=str(work / '016'),
                                                             strings=str(strings), gamedir=str(gamedir)))
    say(f'Done: {len(accounts)} account items, {len(all_rows)} definitions.')
    say(f'Open {out / "dist" / "site" / "index.html"} in your browser.')
    if differs and not args.no_sample:
        say('Note: your files differ from the reference build (Hub 1.99.0.167293) in: ' + '; '.join(differs) +
            '. The result describes your install; compare with the published data before relying on it.')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python -m sc_smi_gen', description=__doc__.split('\n\n')[0])
    parser.add_argument('--gamedir', help='Star Conflict folder (the one with "data" and "cloud"); found in Steam if omitted')
    parser.add_argument('--out', default='smi-build', help='output folder (default: smi-build)')
    parser.add_argument('--no-sample', action='store_true',
                        help='do not use the bundled sample-database facts (atlas ids, sample presence); atlasId stays empty')
    args = parser.parse_args(argv)
    try:
        return run(args)
    except GenError as error:
        print('Error: ' + str(error), file=sys.stderr)
        return 1
    except OSError as error:
        print(f'Error: cannot read or write a file ({error.strerror or type(error).__name__}).', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
