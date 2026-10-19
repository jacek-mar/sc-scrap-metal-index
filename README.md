# SC Scrap Metal Index

**Unofficial item reference for Star Conflict server hosts and modders.**
Find any item of the game, copy its internal name, see where it is defined
and what uses it, and where a server database stores it - in English and
Russian. [Русская версия](dist/ru/README.md)

### ▶ [Open the search](https://jacek-mar.github.io/sc-scrap-metal-index/)

Built from the stock files of the final release (Hub 1.99.0.167293).
Unofficial community project, not affiliated with or endorsed by Gaijin
Entertainment or Targem Games.

## What you can do with it

| You want to… | Use |
|---|---|
| look up an item by its English or Russian name, internal name (`defName`) or id | the [search page](https://jacek-mar.github.io/sc-scrap-metal-index/) |
| find the file and line where an item is defined, and which files only hold generated copies you should not edit | item details → *Where it appears in the game files* |
| see what refers to an item (presets, loot tables, blueprints, quests…) before you rename or remove it | item details → *Used by* |
| know where an item can be stored in a server database, and which mail attachment type sends it | item details → *Where it can appear in the database* |
| work with the data in a spreadsheet or a script | [CSV and JSON downloads](#data-files) |
| check the data against **your own** install, or rebuild it after you changed game files | [`build-index.bat`](#rebuild-from-your-own-install) |
| run the search offline or on your own website | [host your own copy](#host-your-own-copy) |

Example: search **Nebula GS**, open the ship, press *Copy* next to
`Ship_Race1_S_T4_Glass`; its source is
`star conflict\data\gamedata\def\ex\ship.lua:26711`. The guide
[Using the search](dist/docs/using-the-search.md) walks through it.

## Use it offline

Download this repository (green **Code** button → *Download ZIP*), unzip it
and double-click `dist\site\index.html`. No internet, server or
installation is needed; keep the `dist` folder together.

## Data files

All in [`dist/data/`](dist/data/):

| File | Content |
|---|---|
| `items.csv`, `items.json` | the 14,973 items that can belong to a player account, 24 columns |
| `items_all.csv`, `items_all.json` | all 19,364 definitions, including NPC and internal ones |
| `locations.csv`, `.json` | every place an item appears in the game files, grouped (edit here / generated copy / server rule / used by) |
| `db_by_kind.csv`, `.json` | where an item of each kind can be stored in the database, with the mail attachment type |
| `db_fields.csv` | database fields that hold item references |
| `schema.json`, `manifest.json` | column definitions; counts and SHA-256 hashes |

Every column is explained in the [data dictionary](dist/docs/data-dictionary.md)
([по-русски](dist/docs/ru/data-dictionary.md)).

**Read before you use the data:**

* Identify an item by **kind + `defName`**. `storeItemId` is not unique -
  some values are shared by thousands of definitions.
* A name marked `category` is a shared family name, `derived` is our own
  construction; `exact` is the game's own text for that item.
* Where an item *can* be stored is not permission to grant it. Back up the
  database first and take new instance ids from the `counters` collection.
* The data describes the stock files. Community configuration packs change
  files; rebuild the index from your install to see your own state.

## Rebuild from your own install

The repository contains the generator that produced the data. It reads your
Star Conflict install (it never changes it, runs no game code and uses no
network) and writes a complete copy of `dist`.

1. Install [Python 3.10 or newer](https://www.python.org/downloads/) (tick
   *Add python.exe to PATH*). No other packages are needed.
2. Double-click **`build-index.bat`** - it finds the game in your Steam
   libraries - or run
   `build-index.bat --gamedir "<folder with data and cloud>"`.
3. After about 5 minutes open `smi-build\dist\site\index.html`.
4. Optional: `python -m sc_smi_gen.compare dist smi-build\dist` tells you
   whether your install matches the published data.

Details, options and an error table:
[Rebuild and host](dist/docs/rebuild-and-host.md).

## Host your own copy

`dist` is a static website. Copy it to any web space, or serve it locally
with `python -m http.server 8000 --directory dist` and open
`http://localhost:8000/site/`. On GitHub Pages, publishing this repository
from the `main` branch root is enough (the root `index.html` forwards to the
search). Keep the notices and the "Unofficial" wording; do not sell access
to the site or the data.

## Repository layout

| Path | Content |
|---|---|
| `dist/` | the published result: search site, data files, documents (EN/RU) |
| `build-index.bat`, `sc_smi_gen/` | one-command generator; `sc_smi_gen/tpak.py` reads only the two string tables from `data/strings.pak` |
| `sc_gamedata_reader/`, `sc_item_registry/`, `sc_item_names/`, `sc_smi_export/` | reading game data files, the item registry, display names, data files and site |
| `site/`, `public_docs/` | sources of the search page and the documents |
| `tests/` | `python -m unittest discover -s tests` and `node --test tests/search.test.cjs` (no game files needed) |

No game files, assets or executables are included. The data quotes item
names and short descriptions only; story (lore) texts are left out.

## Licence and notices

Our code, documentation and compilation: **CC0-1.0** ([LICENSE](LICENSE)).
Item names and descriptions are © Gaijin Entertainment / Targem Games,
quoted as short identifying references - see [NOTICE.md](NOTICE.md).

Authors: **jacek-mar / Hystrix**.
Background research: [Unofficial Star Conflict Server - Under the Hood](https://github.com/jacek-mar/sc-server-under-the-hood).
