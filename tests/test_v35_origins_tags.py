import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from zarchive.storage import Archive, DEFAULT_TAGS, ORIGIN_KINDS

class OriginAndTagsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.archive = Archive(self.root/'archive')
        self.source = self.root/'my-save.dat'
        self.source.write_bytes(b'one locally saved character')
        self.record = self.archive.import_pc_save(self.source, 'Example Game')
    def tearDown(self):
        self.archive.close()
        self.temp.cleanup()
    def test_origin_roundtrip_and_search(self):
        self.archive.set_origin(self.record['id'], kind='Community upload', name='AnUploader', url='https://example.org/save', notes='From forum')
        result = self.archive.list_saves('AnUploader')[0]
        self.assertEqual(result['origin_kind'], 'Community upload')
        self.assertEqual(result['origin_notes'], 'From forum')
        self.assertEqual(len(self.archive.list_saves('example.org')), 1)
    def test_invalid_url_and_type_not_saved(self):
        for kind,url in [('My own save', 'file:///etc/passwd'), ('Wrong origin',''), ('Website / download','https://user:pw@example.org')]:
            with self.assertRaises(ValueError):
                self.archive.set_origin(self.record['id'],kind=kind,url=url)
        self.assertEqual(self.archive.list_saves()[0]['origin_kind'], '')
    def test_unknown_save_rejected(self):
        with self.assertRaises(ValueError):
            self.archive.set_origin('missing', kind='Unknown')
    def test_backup_manifest_includes_origin(self):
        self.archive.set_origin(self.record['id'],kind='Friend / shared privately',name='Friend')
        target = self.root/'backup.zip'
        self.archive.backup_zip(self.record['id'],target)
        with zipfile.ZipFile(target) as z:
            manifest=json.loads(z.read('manifest.json'))
        self.assertEqual(manifest['origin']['origin_name'],'Friend')
    def test_existing_archive_migration(self):
        self.archive.close()
        db = self.root/'archive'/'archive.sqlite3'
        with sqlite3.connect(db) as conn:
            # Simulate a pre-v3.5 DB by rebuilding the single table without new columns.
            cols = [r[1] for r in conn.execute('PRAGMA table_info(saves)')]
            old = [c for c in cols if not c.startswith('origin_')]
            conn.execute('CREATE TABLE saves_old AS SELECT '+','.join(old)+' FROM saves')
            conn.execute('DROP TABLE saves')
            conn.execute('ALTER TABLE saves_old RENAME TO saves')
        self.archive=Archive(self.root/'archive')
        self.assertEqual(self.archive.list_saves()[0]['origin_name'],'')
        self.assertEqual(self.archive.list_saves()[0]['file_hash'],self.record['file_hash'])
    def test_starter_tags_keep_categories(self):
        from zarchive.storage import CATEGORIES
        self.assertEqual(CATEGORIES,('Legit','Modded','Unsorted'))
        self.assertIn('Max Money',DEFAULT_TAGS)
        self.assertIn('100% Complete',DEFAULT_TAGS)
        self.assertIn('Website / download',ORIGIN_KINDS)
