"""Revision 1 (v0.2): location groups, roles, race names, database by kind - synthetic data only."""
import unittest

from sc_smi_export.locations import DB_COLUMNS, classify, db_by_kind, locations, race_names


def ref(location, field):
    return dict(source='file', location=location, field=field)


class ClassifyTests(unittest.TestCase):
    def test_definition_is_edit_here(self):
        c = classify('Ship_A', ref('data/gamedata/def/ex/ship.lua:10', 'definition'))
        self.assertEqual((c['group'], c['location'], c['role']), ('edit_here', 'star conflict\\data\\gamedata\\def\\ex\\ship.lua:10', 'definition'))

    def test_own_field_is_edit_here(self):
        c = classify('Ship_A', ref('data/gamedata/def/ex/ship.lua:12', 'Def.Ship_A.ship_name'))
        self.assertEqual((c['group'], c['role'], c['referrer']), ('edit_here', 'own field ship_name', ''))

    def test_generated_server_copy(self):
        c = classify('Ship_A', ref('cloud/data/store.xml:5', 'defName'))
        self.assertEqual((c['group'], c['role']), ('generated', 'server copy'))

    def test_server_rules_and_inert(self):
        self.assertEqual(classify('X', ref('cloud/data/store_rules.xml:1', 'defName'))['group'], 'server_rules')
        self.assertEqual(classify('X', ref('cloud/data/defmod_rules_new.xml:1', 'defName'))['group'], 'inert')

    def test_used_by_roles(self):
        cases = [
            ('Def.Weapon_B.required_ship', 'required ship of', 'Weapon_B'),
            ('Def.Ship_P.default_modules[3]', 'fitted by default on', 'Ship_P'),
            ('Def.BP_X.craft_result', 'produced by blueprint', 'BP_X'),
            ('ModulePresets.Preset_1.modules[2]', 'in module preset', 'Preset_1'),
            ('LootTable.RareT1', 'drops from loot table', 'RareT1'),
            ('Def.Bundle_Gift', 'contained in bundle', 'Bundle_Gift'),
            ('Def.Preset_X.inherit', 'base definition of', 'Preset_X'),
        ]
        for field, role, referrer in cases:
            c = classify('Ship_A', ref('data/gamedata/def/ex/a.lua:3', field))
            self.assertEqual((c['group'], c['role'], c['referrer']), ('used_by', role, referrer), field)

    def test_unknown_member_falls_back(self):
        c = classify('A', ref('data/gamedata/def/ex/a.lua:3', 'Def.B.some_new_field'))
        self.assertEqual((c['group'], c['role']), ('used_by', 'referenced by'))

    def test_locations_dedupe_prefers_definition(self):
        registry = {('custom_element', 'D'): dict(references=[
            ref('cloud/data/vessel_custom_elements.xml:7', 'definition'),
            ref('cloud/data/vessel_custom_elements.xml:7', 'name'),
            dict(source='db', location='cosmosim_node/accounts', field='x')])}
        rows = locations(registry)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['role'], 'definition in server data')


class RaceAndDatabaseTests(unittest.TestCase):
    def test_race_names_from_tables(self):
        tables = {'en': {'race_EMPIRE': ('Empire', 1)}, 'ru': {'race_EMPIRE': ('Империя', 1)}}
        self.assertEqual(race_names('ai.Race.EMPIRE', tables), ('Empire', 'Империя'))
        self.assertEqual(race_names('', tables), ('', ''))
        # Missing key: the raw code stays visible rather than an invented name.
        self.assertEqual(race_names('ai.Race.OTHER', tables), ('ai.Race.OTHER', 'ai.Race.OTHER'))

    def test_db_by_kind_contract(self):
        rows = db_by_kind()
        self.assertTrue(all(list(r) == DB_COLUMNS for r in rows))
        ship = [r for r in rows if r['kind'] == 'ship']
        self.assertEqual(ship[0]['field_path'], 'vessels[].defName')
        self.assertTrue(all(r['database'] in ('cosmosim_<WinUser>', '') for r in rows))
        self.assertTrue(any(r['field_path'] == 'vessels[].munition[].def' for r in rows))


if __name__ == '__main__':
    unittest.main()
