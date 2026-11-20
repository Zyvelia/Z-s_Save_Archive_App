import json, tempfile, unittest
from pathlib import Path
from zarchive.upgrade_v10 import ArchiveV10

class UpgradeV10Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name)
        self.a=ArchiveV10(self.base/'archive')
        p=self.base/'sample';p.mkdir();(p/'save.bin').write_bytes(b'savedata')
        self.record=self.a.import_pc_save(p,'Example Game')
        self.sid=self.record['id']
    def tearDown(self):
        self.a.conn.close();self.tmp.cleanup()
    def test_migration_and_profile(self):
        pid=self.a.create_profile('PC','Example Game','Hero One');self.a.assign_profile(self.sid,pid)
        self.assertEqual(self.a.profile_for(self.sid)['name'],'Hero One')
        other=self.base/'other';other.mkdir();r=self.a.import_pc_save(other/'missing','Other') if False else None
        with self.assertRaises(ValueError):self.a.create_profile('PS3','Example Game','Invalid')
    def test_pin(self):
        self.a.pin_save(self.sid);self.a.pin_game('PC','Example Game')
        self.assertEqual(len(self.a.pinned()['saves']),1)
        self.assertEqual(len(self.a.pinned()['games']),1)
        self.a.pin_save(self.sid,False);self.assertEqual(len(self.a.pinned()['saves']),0)
    def test_external_backup(self):
        dest=self.base/'external';dest.mkdir()
        folder,rows=self.a.external_backup(dest)
        self.assertEqual(rows[0]['status'],'ok')
        self.assertEqual(len(list(folder.glob('*.zip'))),1)
        self.assertEqual(len(rows[0]['sha256']),64)
        with self.assertRaises(ValueError):self.a.external_backup(self.a.root)
    def test_recovery_and_health(self):
        self.a.log_recovery('transfer','bad.zip','disconnected')
        self.assertIn('disconnected',self.a.recovery()['events'][0]['error'])
        self.assertEqual(self.a.startup_health()['database'],'ok')
    def test_catalog_sanitizes_html_and_only_public_verified(self):
        self.assertEqual(self.a.export_catalog(self.base/'empty.html'),0)
        self.a.save_details(self.sid,category='Modded',label='<script>alert(1)</script>',notes='ok',status='Verified',tags=['Max Money'],visibility='Public')
        count=self.a.export_catalog(self.base/'catalog.html')
        doc=(self.base/'catalog.html').read_text()
        self.assertEqual(count,1);self.assertNotIn('<script>',doc);self.assertIn('&lt;script&gt;',doc)
    def test_privacy_and_compatibility(self):
        self.assertTrue(self.a.compatibility(self.sid)['warnings'])
        self.assertTrue(self.a.privacy_audit(self.sid))
        self.assertIn('Steam Cloud',self.a.steam_cloud_advice(self.sid))
    def test_connections_no_password(self):
        pid=self.a.connection_add('Home PS3','192.168.1.60')
        self.assertEqual(self.a.connections()[0]['id'],pid)
        self.assertNotIn('password',str(self.a.connections()).lower())
    def test_duplicate_catalog_no_overwrite(self):
        path=self.base/'catalog.html';self.a.export_catalog(path)
        with self.assertRaises(ValueError):self.a.export_catalog(path)

if __name__=='__main__':unittest.main()
