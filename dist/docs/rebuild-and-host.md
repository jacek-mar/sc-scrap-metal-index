# Rebuild the index from your own install, and host it

The published data was built from the stock files of the final release
(Hub 1.99.0.167293). If you want to check it, or your copy differs, the
generator rebuilds the same files from **your own** Star Conflict install.
It reads the install only: it does not change game files, does not run game
code and does not use the internet.

## 1. What you need

* Windows (the generator also runs on Linux with Python; only the Steam
  lookup differs - pass `--gamedir` there).
* **Python 3.10 or newer** from [python.org](https://www.python.org/downloads/)
  (tested with 3.12). Nothing else: no packages to install.
* A Star Conflict install, for example from Steam. About 4-5 minutes and
  roughly 300 MB of free disk space for the build folder.
* The project folder (the source repository, not only `dist/`): it contains
  `build-index.bat` and the `sc_smi_*` folders.

## 2. Build

Double-click **`build-index.bat`** in the project folder, or run it in a
command prompt:

```bat
build-index.bat
build-index.bat --gamedir "<your Steam library>\steamapps\common\star conflict"
build-index.bat --out "<output folder>"
```

Without `--gamedir` it looks for the game in your Steam libraries
(`libraryfolders.vdf`). Pass the folder that contains `data` and `cloud`
if the game is elsewhere. The equivalent Python command is
`python -m sc_smi_gen [--gamedir ...] [--out ...]`.

It prints four steps:

1. unpacks **only** `strings/english/string.txt` and
   `strings/russian/string.txt` from `data/strings.pak` (the reader cannot
   extract anything else);
2. reads the item definitions (`data/gamedata`, `cloud/data`) - the slow step;
3. resolves item names;
4. writes the data files and the search site.

The result is `smi-build\dist` (or `<out>\dist`): open
`dist\site\index.html`. Intermediate files are in `smi-build\work`; delete
the whole `smi-build` folder when you no longer need it. It contains game
text from your install - do not publish `work`.

### Sample database facts

Two values cannot be read from game files: the **atlas ids** (`atlasId`,
assigned by the server in its database) and "seen in a sample database"
marks. The generator uses a small bundled snapshot of our sanitised test
database for them (item references only - no accounts, names or
addresses), so the result matches the published data. With `--no-sample`
these values stay empty (in the reference build the account item count
stays the same). This default may change after user feedback: tell us whether you
expect a rebuild to match the published data or to use only your own files.

### Check against the published data

```bat
python -m sc_smi_gen.compare dist smi-build\dist
```

`Identical (... files; generation date ignored)` means your install produced
exactly the published files. Any `differs:` line means your files differ
from the stock release (for example a community configuration pack) - the
rebuilt index then describes **your** files. If your files differ from the
reference build, the generator also prints which reference checks did not
match.

### When something goes wrong

| Message | What to do |
|---|---|
| `Star Conflict was not found in your Steam libraries` | pass `--gamedir "<folder with data and cloud>"` |
| `This folder does not look like a Star Conflict install` | you passed a parent or child folder; choose the one containing `data` and `cloud` |
| `Cannot read data/strings.pak` | verify the game files in Steam (Properties -> Installed files -> Verify) |
| `py` / `python` is not recognised | install Python and tick "Add python.exe to PATH" |
| `Choose an output folder outside the game folder` | use `--out` with a folder elsewhere |

## 3. Host the search site

The `dist` folder is a complete static site: no server code, no database,
no build step. Keep its structure (`site/`, `data/`, `docs/`, `NOTICE.md`)
together - the page loads its data from `site/data/` and links to `../docs/`.

| Where | How |
|---|---|
| Your own disk | double-click `dist\site\index.html`. Copy buttons fall back to a text box when the browser blocks the clipboard for local files |
| Local network / quick test | `python -m http.server 8000 --bind 127.0.0.1 --directory dist`, then `http://localhost:8000/site/`. Use `--bind 0.0.0.0` only on a trusted network |
| GitHub Pages | put the **contents** of `dist` in a repository (or a `docs/` folder), enable Pages, open `https://<user>.github.io/<repo>/site/` |
| Any static host (Netlify, a web server, an S3-style bucket) | upload the contents of `dist` unchanged; the entry point is `site/index.html` |

Notes for hosts:

* The page sets a strict Content Security Policy (local scripts only, no
  network requests). Do not add trackers or external scripts.
* Compression (gzip/brotli) on the host makes the data files much smaller;
  the site works without it.
* **Keep the notices**: the footer, `NOTICE.md` and the "Unofficial" wording.
  Item names and descriptions are © Gaijin Entertainment / Targem Games and
  are quoted as short identifying references; do not sell access to the
  site or the data, and do not present it as official.

## 4. What is inside the package

| Folder | Content |
|---|---|
| `sc_smi_gen` | the generator: strings-only TPAK reader (`tpak.py`), Steam lookup, the bundled sample snapshot, `compare` |
| `sc_gamedata_reader` | static reader for the game's data files (never executes them) |
| `sc_item_registry` | item definitions, ids, references, account scope |
| `sc_item_names` | display names and distinguishing labels from the string tables |
| `sc_smi_export` | data files, documents and the search site |

No game files, assets or text are included in the package; everything
game-related is read from your install at build time. All code: CC0-1.0.
