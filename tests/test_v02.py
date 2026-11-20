import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from zarchive.storage import Archive

class TestsV02(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        self.base=Path(self.t.name);self.db=Archive(self.base/'archive');self.addCleanup(self.db.close)
        self.folder=self.base/'game saves';self.folder.mkdir();(self.folder/'slot1.sav').write_bytes(b'game data')
    def test_import_pc_folder_and_preserve(self):
        r=self.db.import_pc_save(self.folder,'My PC Game')
        self.assertEqual(r['platform'],'PC')
        self.assertEqual((self.folder/'slot1.sav').read_bytes(),b'game data')
        self.assertEqual(len(self.db.games(platform='PC')),1)
    def test_import_pc_file(self):
        r=self.db.import_pc_save(self.folder/'slot1.sav','My PC Game')
        self.assertTrue((self.db.root/r['stored_path']/'slot1.sav').exists())
    def test_duplicate(self):
        self.db.import_pc_save(self.folder,'My PC Game')
        with self.assertRaisesRegex(ValueError,'Identical'):
            self.db.import_pc_save(self.folder,'My PC Game')
    def test_tags_and_filter(self):
        r=self.db.import_pc_save(self.folder,'My PC Game')
        self.db.set_tags(r['id'],['Max Money','Custom Tag','max money'])
        self.assertEqual(self.db.list_saves(tag='Max Money')[0]['tags'],['Max Money','Custom Tag'])
        self.assertEqual(self.db.list_saves(tag='Unrelated'),[])
        self.assertIn('Custom Tag',self.db.list_tags())
    def test_zip_integrity(self):
        r=self.db.import_pc_save(self.folder,'My PC Game')
        self.db.set_tags(r['id'],['All Unlocks'])
        target=self.base/'exports'/'save.zip';self.db.backup_zip(r['id'],target)
        with zipfile.ZipFile(target) as z:
            self.assertIsNone(z.testzip())
            self.assertEqual(z.read('save/slot1.sav'),b'game data')
            self.assertEqual(json.loads(z.read('manifest.json'))['tags'],['All Unlocks'])
        with self.assertRaises(FileExistsError):self.db.backup_zip(r['id'],target)
    def test_tampering_refused(self):
        r=self.db.import_pc_save(self.folder,'My PC Game')
        (self.db.root/r['stored_path']/'slot1.sav').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'changed'):
            self.db.backup_zip(r['id'],self.base/'bad.zip')
    def test_migration(self):
        r=self.db.import_pc_save(self.folder,'My PC Game')
        other=Archive(self.base/'archive')
        try:self.assertEqual(other.list_saves(platform='PC')[0]['id'],r['id'])
        finally:other.close()
    def test_wrong_platform_filter(self):
        self.db.import_pc_save(self.folder,'My PC Game')
        self.assertEqual(self.db.list_saves(platform='PS3'),[])

if __name__=='__main__':unittest.main()
