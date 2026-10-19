import json
import tempfile
import unittest
from pathlib import Path

from sc_smi_export.localization import interface_errors, document_errors, tables
from sc_smi_export.publication import scan
from sc_smi_export.export import MEANINGS, MEANINGS_RU
from sc_smi_export.locations import db_by_kind, DB_COLUMNS


class LocalizationTests(unittest.TestCase):
    def test_authored_table_and_field_coverage(self):
        self.assertEqual(interface_errors(Path('site')), [])
        self.assertEqual(MEANINGS.keys(), MEANINGS_RU.keys())
        for row in db_by_kind():
            self.assertEqual(list(row), DB_COLUMNS)
            self.assertTrue(row['value_written_ru'])
            if row['mail']:
                self.assertTrue(row['mail_ru'])

    def test_synthetic_translation_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            (site/'index.html').write_text('<p data-i18n="hello">Hello</p>')
            for ru in [{}, {'hello': ''}, {'hello': 'Привет {other}'}]:
                (site/'i18n.js').write_text('const en = '+json.dumps({'hello': 'Hello {name}'})+
                                          '; const ru = '+json.dumps(ru)+';', encoding='utf-8')
                self.assertTrue(interface_errors(site))

    def test_russian_document_link_and_legal_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            for name in ['ru/README.md', 'docs/ru/using-the-search.md',
                         'docs/ru/data-dictionary.md', 'ru/NOTICE.md', 'NOTICE.md']:
                p = dist/name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('# Notice\n\nLegal sentence.', encoding='utf-8')
            self.assertEqual(document_errors(dist), [])
            (dist/'ru/README.md').write_text('[bad](../../outside.md)')
            (dist/'ru/NOTICE.md').write_text('Translation only')
            self.assertEqual(len(document_errors(dist)), 2)

    def test_public_docs_ru_style_contamination(self):
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            path = dist/'docs/ru/using-the-search.md'
            path.parent.mkdir(parents=True)
            path.write_text('# Руководство\n\nПример: test_user_9', encoding='utf-8')
            self.assertTrue(any('sample account' in e for e in scan(dist, {})))
