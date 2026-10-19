# SC Scrap Metal Index — v0.3

[Русский](ru/README.md)

Unofficial Star Conflict item reference for community hosts and modders.
Hub 1.99.0.167293, **stock files**. Configuration packs can change your files;
those changes are not reflected here.

Open [the search page](site/index.html), or double-click `site/index.html`
after downloading the complete folder. No internet or server is needed.
Keep the folder structure intact. To serve a local copy instead, run
`python -m http.server 8000 --directory dist` from the folder containing
`dist`, then open `http://localhost:8000/site/`. For static hosting, copy this
whole folder and use `site/index.html` as the entry point. No compilation or
installation is required. See [the search guide](docs/using-the-search.md).

For example, search **Nebula GS**, choose the ship label matching your item,
then open its details and copy `Ship_Race1_S_T4_Glass`. Its `defined_in` is
`star conflict\data\gamedata\def\ex\ship.lua:26711`: open that file under your
Steam library and go to line 26711. The detail view also lists every other
place the ship appears - generated server copies you should not edit, and
the items and tables that point to it - and where a ship is stored in the
database (`cosmosim_<WinUser>.accounts.vessels[].defName`). These locations help you inspect your own files and a database backup; they
do not establish that granting the item will work.

Use **kind + defName** as identity. A `storeItemId` can refer to many items;
never take the first match. Names marked `category` are shared titles and
`derived` names are our derivations. Unknown account scope stays unknown.
Database locations are listed per kind (`data/db_by_kind.csv`): where an
item of that kind can be stored and what value is written there. They are
not permission to grant an item. Battle and statistics history is not
covered yet.

Downloads: [account CSV](data/items.csv), [account JSON](data/items.json),
[all-definition CSV](data/items_all.csv), [all-definition JSON](data/items_all.json),
[database fields](data/db_fields.csv), [schema](data/schema.json),
[counts and hashes](data/manifest.json). The [data dictionary](docs/data-dictionary.md)
explains all 24 columns. CSV list cells contain JSON; empty values mean
unavailable, not zero. To rebuild everything from your own install, or to
host the site, read [rebuild and host](docs/rebuild-and-host.md).

Item names and descriptions are © Gaijin Entertainment / Targem Games,
quoted as short identifying references. Unofficial community project, not
affiliated with or endorsed by Gaijin or Targem. Our code, documentation and
compilation: CC0-1.0. Authors: **jacek-mar / Hystrix**. Read [the notices](NOTICE.md).

Research: [Unofficial Star Conflict Server - Under the Hood](https://github.com/jacek-mar/sc-server-under-the-hood).
Project: [SC Scrap Metal Index](https://github.com/jacek-mar/sc-scrap-metal-index).
