## Reading the fields in practice

See [Using the search](using-the-search.md) for a Nebula GS walkthrough and
the meaning of all six name statuses. A text key is the code used to look up
a name in the game's language table. An own definition field is a value
stored on that item which points to the key. A known key prefix is a fixed
piece added before a code to find its name. A shared subtype is a group of
related items with a common title; its name is marked `category`. An ID
namespace is a separate numbering system: `storeId`, `storeItemId`,
`atlasId`, `iid` and `vid` cannot be substituted for one another.

`<WinUser>` is a placeholder for the Windows user name used by a local
server, not literal text in the database name. Hosts may configure another
name. `[]` means each element of a list. `<>` stands for an observed numeric
slot; use the slot for your own record. A physical line is an actual line
in the stock file, including comments and blank lines.

`iid` references an item instance within an account, while `vid` references
a ship instance. Do not copy catalogue IDs into these fields. Atlas packed
words contain encoded values that have not been resolved: do not read them
as plain item IDs. Unobserved `autogenItems` fields are possible locations
only, not a confirmed description of their members or instructions to edit.

Account scope is a classification, not proof that granting an item works or
is safe. Where an item of a given kind can be stored in the database is
listed in `data/db_by_kind.csv` (see below); the `db_fields` column only
confirms that the item was seen in a sample database. Find an unnamed item by `defName`. For a shared storeItemId,
switch to all definitions and inspect every matching row; never choose the
first match automatically. Kind plus defName identifies a row.

Descriptions may be absent because no eligible text exists, it is longer
than 200 characters, or it is lore (including duplicate lore text). No
truncation occurs. `$value$` stands for a value the game fills from the
definition; the export does not calculate it. For example
`$projectile_speed_mul$%` is not a numerical stat in this data set.

## Diagnostic flag meanings

| Flag | Meaning for a host |
|---|---|
| `ambiguous_defName_across_kinds` | The code occurs in more than one kind; keep kind with it. |
| `cant_be_bought` | The stock definition marks it as not buyable; this does not establish grant safety. |
| `no_name` | The original registry lacked a name; later name lookup may have resolved one. |
| `no_store_entry` | No matching store entry was found; do not assume store availability. |
| `unresolved_storeItemId_expression` | The ID is an expression the static reader did not resolve. |
| `xml_only` | This entry was found only in XML, rather than a Lua definition. |

## Search files

The search page uses compact array rows in `site/data/items.js` (account)
and `items_all.js` (optional full set). Their fixed order is kind, defName,
name_en, name_ru, label_en, label_ru, name_status, storeItemId, storeId,
atlasId, account_scope. Detail scripts by kind hold the remaining columns,
keyed by defName within that kind. An on-demand shared-ID catalogue lists
kind and defName pairs from all definitions so warnings include internal
entries without loading the full search index. These files reproduce the
downloadable data with the same 24 columns. Location scripts by kind
(`site/data/locations-<kind>.js`) and the database table (`site/data/db.js`)
load on demand.

## File locations (`data/locations.csv`)

One row per place an item appears in the stock files: `kind`, `defName`,
`group`, `location` (standard install path and physical line), `role` (plain
words) and `referrer` (the item or table that points to it, if any).

| group | Meaning for an editor |
|---|---|
| `edit_here` | the item's source definition and its own fields under `data\gamedata` - change things here |
| `generated` | a copy in `cloud\data` written by `prepare_shared`; a hand edit there is overwritten the next time the server data is prepared |
| `server_rules` | a hand-maintained server file in `cloud\data` (for example `store_rules.xml`) |
| `inert` | a file no service reads (`defmod_rules*.xml`); editing it has no effect |
| `used_by` | another item or table that points to this item: the `role` says how, e.g. `required ship of`, `fitted by default on`, `in module preset`, `drops from loot table`, `produced by blueprint`, `contained in bundle`, `base definition of`, `crafting ingredient of` |

Before deleting or renaming an item, check its `used_by` rows: every one of
them points to the old name.

## Database locations by kind (`data/db_by_kind.csv`)

Where an item of each kind can be stored in the game database
(`cosmosim_<WinUser>`): `kind`, `database`, `collection`, `field_path`,
`value_written` (what is written there: the `defName`, a numeric id, or an
instance id), `evidence` (S seen in a sample database, D documented schema,
B field name in the server program, M mail attachment type, L observed
after a grant on a test server) and `mail` (how
to send it by mail, if possible). Appended `value_written_ru` and `mail_ru`
contain Russian versions of that prose; the site falls back to English if
a Russian value is empty. Field paths and mail type codes are unchanged. Rows marked unverified are leads, not
confirmed formats. Battle and statistics history databases (`games_*`,
`stats_*`, logs, leaderboards) are not covered in this version.

Three things that surprise people: a fitted module is stored on the ship by
its `iid`, not by its name (`vessels[].equipped[]`); ammunition uses a field
named `def`, not `defName`; craft resources are stored as keys of
`craftResources`, with the amount as the value.
