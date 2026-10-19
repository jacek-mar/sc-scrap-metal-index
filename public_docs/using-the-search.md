# Using the search

This unofficial Star Conflict reference covers Hub 1.99.0.167293 stock files.
It helps you identify an item and find its file or database field. It does
not connect to a game server, edit a database or promise that an item can be
granted. Community configuration packs may change what exists on your host.

## Find a ship: Nebula GS

1. Open `site/index.html`. Leave coverage at **Account items** and enter
   `Nebula GS`. Search accepts either language, labels or internal codes.
2. Choose the ship row with the label matching your intended variant.
   Open it with a click or Tab and Enter. Check kind `ship` and
   `defName` `Ship_Race1_S_T4_Glass`; names alone need not distinguish items.
3. Press **Copy defName**. If clipboard access is unavailable when opening
   from disk, a selected text box appears: press Ctrl+C (Command+C on macOS).
4. Read or copy `defined_in`:
   `star conflict\data\gamedata\def\ex\ship.lua:26711`. Under your Steam
   library, open `steamapps\common\star conflict\data\gamedata\def\ex\ship.lua`
   in a text editor and go to line 26711. The line number counts actual lines
   in the stock file, including comments and blank lines.
5. Read **Where it appears in the game files**. *Edit here* is the source
   definition you change. *Generated server copy* entries (in `cloud\data`)
   are rewritten by `prepare_shared`, so do not edit them by hand. *Used by*
   lists every item or table that points to this ship, with its role - for
   example presets that use it as their ship. Check these before you rename
   or remove an item.
6. Read **Where it can appear in the database**. For a ship it is
   `cosmosim_<WinUser>.accounts.vessels[].defName`, and every ship there
   also gets an instance id `vid` from the `counters` collection. In a
   path such as `cosmosim_<WinUser>.accounts.vessels[].defName`, `[]` means
   list members store the definition code in `defName`. Replace `<WinUser>`
   with the Windows user name used by your local server, or use the database
   name configured by your host. The brackets are notation, not part of the
   MongoDB field name. Inspect your own backup to confirm any item's presence.

## Search, filters and sharing

Text matches names, distinguishing labels and `defName` without regard to
case, including Cyrillic. A number matches an entire `storeItemId`, `storeId`
or `atlasId`, not part of a longer ID. Those three numbering systems are
separate: the same number in different columns need not mean the same item.
The kind and name-status filters narrow the same results. The EN/RU toggle
changes the interface and displayed labels; both languages remain searchable.

Only 200 results appear initially. **Show 200 more** extends the list; the
count always shows the total matches. At narrow widths scroll the table
horizontally. Tab reaches every control; arrow keys move between item
buttons; Enter opens details and Escape closes them. Copy the address with
its `#` part to preserve the query, filters, language and selected item.
A file address works on your own machine; share the hash after your hosted
site address for other people to open it.

Switch to **All definitions** to include internal and unknown-scope rows.
That larger index loads only when requested. Details load by item kind.
For ID `224`, inspect both `Ship_Race3_L_T5_Mole` and
`Ship_Race2_L_T5_Protozan`. Each warns that the ID is shared and names other
definitions with that value. Search all definitions before deciding which
row you need; use **kind + defName**, never just the first ID match.

## What the name statuses mean

| Status | How to read it |
|---|---|
| `exact` | The text table has a key directly matching the definition code. |
| `own_field` | The item's own definition points to a text key; the key is stored in one of its fields. |
| `prefixed` | A known naming pattern adds a prefix to the definition code to find its text key. |
| `category` | A shared subtype groups related items and supplies their common name. Read the label's tier, mark and ranks to tell variants apart. |
| `derived` | We constructed the name from related identifying text. It is our derivation, not a quoted game title for that item. |
| `none` | No name was resolved. Search by `defName` or IDs; the label falls back to the code. |

The same vocabulary accompanies descriptions. An empty description may
mean no suitable source exists, its text exceeds 200 characters, or it is
lore (including text duplicated as lore). Text is omitted rather than cut
off. In `Raises ... by $projectile_speed_mul$%.`, the `$...$` part is a raw
placeholder: the game fills it using the definition. This export does not
supply that value. An empty value is never an estimate of zero.

## Database and diagnostic caveats

`[]` means each element of a list. `<>` stands for an observed numeric slot
in a nested field; substitute the appropriate slot for your record. `iid`
is an item-instance reference within an account and `vid` a ship-instance
reference. Neither identifies a catalogue definition: do not paste a store
ID into either field. An `atlasId` belongs to another numbering system;
packed atlas words remain unresolved, so do not treat every number in them
as an item ID. A seed chip in `autogenItems[]` is an instance
`{iid, upgradeLevel, rollData, exp}` rolled by the server; it is not an edit
recipe.

`account` scope means classified as an account item, not permission or
proof of safety to grant. `npc_or_internal` identifies internal/NPC use;
`unknown` means the classification is not established. The database section
of an item shows where an item of its kind can be stored; a line "seen in a
sample database" is only an extra confirmation, and its absence means
nothing.

Flags are diagnostic codes from reading the definitions. A row can keep
`no_name` even when a name was found by another rule. The dictionary
lists every actual kind and flag. Non-account rows have less enriched labels
than account rows; always check their codes and status.

Item names and descriptions are © Gaijin Entertainment / Targem Games,
quoted as short identifying references. Unofficial community project, not
affiliated with or endorsed by Gaijin or Targem. Our work: CC0-1.0.
Authors: jacek-mar / Hystrix. Stock files, Hub 1.99.0.167293.

Research: [Unofficial Star Conflict Server - Under the Hood](https://github.com/jacek-mar/sc-server-under-the-hood).
