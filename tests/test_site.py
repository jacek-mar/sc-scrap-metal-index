import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sc_smi_export.site import generate, read_script, check_data, INDEX_COLUMNS
from sc_smi_export.site import script
from sc_smi_export.publication import scan


class SiteDataTests(unittest.TestCase):
    def test_split_roundtrip_unicode_and_scope(self):
        row = dict(zip(INDEX_COLUMNS, ['ship', 'A', 'Alpha', 'Альфа', 'Alpha I', 'Альфа I', 'exact', 0, '', 12, 'account']))
        row.update(short_desc_en='Value $x$', defined_in='star conflict\\data\\a.lua:1', flags=[], storeItemId_shared=True)
        other = dict(row, defName='B', account_scope='unknown')
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            (dist / 'data').mkdir()
            for stem, rows in [('items', [row]), ('items_all', [row, other])]:
                (dist / 'data' / (stem + '.json')).write_text(json.dumps(rows), encoding='utf-8')
            generate(dist)
            self.assertEqual(check_data(dist), [])
            self.assertEqual(len(read_script(dist / 'site/data/items_all.js')), 2)
            with patch('sc_smi_export.site.LIMIT', 1):
                self.assertIn('account search index exceeds 4 MB', check_data(dist))
            generate(dist)
            self.assertEqual(check_data(dist), [])

    def test_reject_executable_assignment(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'data.js'
            path.write_text('window.SMI_INDEX = []; alert(1);\n')
            with self.assertRaises(ValueError):
                read_script(path)


class SitePublicationTests(unittest.TestCase):
    def test_site_source_contamination(self):
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            site = dist/'site'; site.mkdir()
            for filename, content in [
                ('app.js', 'fetch("https://example.invalid/data")'),
                ('app.js', 'element.innerHTML = value;'),
                ('style.css', 'a {background: url(//example.invalid/x)}'),
                ('index.html', '<script src="//example.invalid/x"></script>'),
                ('index.html', '<button onclick="run()">Go</button>'),
                ('index.html', '<p>test_user_9</p>'),
                ('index.html', '<p>Secret lore.</p>'),
                ('index.html', '<p>No CSP</p>'),
            ]:
                for old in site.iterdir(): old.unlink()
                (site/filename).write_text(content, encoding='utf-8')
                self.assertTrue(scan(dist, {'en': {'A_desc_lore': ('Secret lore.', 1)}}), content)

    def test_decoded_script_values_and_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp); path = dist/'site/data/details-ship.js'
            for value in ['Secret lore.', 'cosmosim_node', 'C:\\Users\\Example\\data', 'x'*201]:
                script(path, 'window.SMI_DETAILS_ship', {'A': {'short_desc_en': value}})
                self.assertTrue(scan(dist, {'en': {'A_desc_lore': ('Secret lore.', 1)}}))
            script(path, 'window.SMI_DETAILS_ship', {'A': {'short_desc_en': 'Raw $speed$%', 'defined_in': 'star conflict\\data\\a.lua:1'}})
            self.assertEqual(scan(dist, {}), [])
            script(dist/'site/data/items.js', 'window.SMI_INDEX', [['ship', 'A', 'x'*201, '', '', '', 'none', '', '', '', 'account']])
            self.assertTrue(scan(dist, {}))
