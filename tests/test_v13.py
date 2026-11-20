import json, tempfile, unittest
from pathlib import Path
from zarchive.upgrade_v13 import ArchiveV13

class V13Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.external=tempfile.TemporaryDirectory()
        self.base=Path(self.temp.name);self.source=self.base/'pc';self.source.mkdir();(self.source/'save.dat').write_bytes(b'A')
        self.a=ArchiveV13(self.base/'archive')
        self.sid=self.a.import_pc_save(self.source,'Test PC Game')['id']
    def tearDown(self):self.a.close();self.temp.cleanup();self.external.cleanup()
    def test_game_registration(self):
        k=self.a.add_game_path('Test PC Game',self.source)
        self.assertEqual(self.a.game_paths()[0]['id'],k)
        self.a.remove_game_path(k);self.assertEqual(self.a.game_paths(),[])
    def test_reject_internal_game_path(self):
        with self.assertRaises(ValueError):self.a.add_game_path('bad',self.a.root)
    def test_location_definitions(self):
        p=self.base/'defs.json';p.write_text(json.dumps([{'game':'X','path':'%USERPROFILE%/Saved Games/X'}]))
        self.assertEqual(self.a.import_location_definitions(p),1)
        self.assertEqual(self.a.import_location_definitions(p),1)
        self.assertTrue(any(r['game']=='X' for r in self.a.candidate_paths({'USERPROFILE':str(self.base)})))
    def test_bad_definitions_atomic(self):
        p=self.base/'bad.json';p.write_text(json.dumps([{'game':'Good','path':'%USERPROFILE%/abc'},{'game':'Bad','path':'../secret'}]))
        with self.assertRaises(ValueError):self.a.import_location_definitions(p)
        self.assertEqual(self.a.conn.execute('SELECT COUNT(*) FROM discovery_definitions').fetchone()[0],0)
    def test_epic_discovery(self):
        p=self.base/'epic';p.mkdir();(p/'one.item').write_text(json.dumps({'DisplayName':'A Game','InstallLocation':'D:/Games/A'}))
        (p/'invalid.item').write_text('broken')
        self.assertEqual(len(self.a.epic_installations(p)),1)
        self.assertFalse(self.a.epic_installations(p)[0]['save_location_confirmed'])
    def test_gog_discovery(self):
        p=self.base/'gog';(p/'Test').mkdir(parents=True)
        self.assertEqual(self.a.gog_installations(p)[0]['game'],'Test')
    def test_xbox_candidates(self):
        p=self.base/'Packages'/'SomeGame'/'SystemAppData'/'wgs';p.mkdir(parents=True)
        self.assertEqual(len(self.a.xbox_candidates({'LOCALAPPDATA':str(self.base)})),1)
    def test_cloud_warning(self):
        out=self.a.cloud_restore_warning('C:/Steam/userdata/123','Steam')
        self.assertFalse(out['safe_to_auto_restore']);self.assertGreater(len(out['warnings']),0)
    def test_backup_rule_gate(self):
        w=self.a.watch_folder_add('Test PC Game',self.source)
        with self.assertRaises(ValueError):self.a.configure_backup_rule(w,min_interval=1)
        self.assertEqual(self.a.run_backup_rules(),[])
        self.a.configure_backup_rule(w,enabled=True,min_interval=60)
        result=self.a.run_backup_rules(time_now=1000)
        self.assertIn(result[0]['state'],('duplicate','imported'))
        self.assertEqual(self.a.run_backup_rules(time_now=1001)[0]['state'],'interval')
    def test_changed_snapshot(self):
        w=self.a.watch_folder_add('Test PC Game',self.source)
        self.a.configure_backup_rule(w,enabled=True,min_interval=60)
        self.a.run_backup_rules(time_now=1000)
        (self.source/'save.dat').write_bytes(b'B')
        self.assertEqual(self.a.run_backup_rules(time_now=1061)[0]['state'],'imported')
        self.assertEqual(len(self.a.list_saves()),2)
    def test_verify_archive(self):
        self.assertTrue(self.a.verify_all_saves()[0]['valid'])
        stored=self.a.root/self.a._save(self.sid)['stored_path']
        (stored/'save.dat').write_bytes(b'corrupted')
        self.assertFalse(self.a.verify_all_saves()[0]['valid'])
    def test_mirror_and_integrity(self):
        dest=Path(self.external.name)/'mirror'
        report=self.a.mirror_archive(dest)
        self.assertGreater(report['files'],1)
        self.assertTrue(self.a.verify_mirror(dest)['verified'])
        (dest/'objects'/self.sid/'save.dat').write_bytes(b'corrupted')
        self.assertFalse(self.a.verify_mirror(dest)['verified'])
    def test_no_mirror_overwrite(self):
        dest=Path(self.external.name)/'mirror'
        self.a.mirror_archive(dest)
        with self.assertRaises(FileExistsError):self.a.mirror_archive(dest)
    def test_events_health(self):
        self.a.notification('info','Test')
        self.assertEqual(self.a.notifications()[0]['message'],'Test')
        self.assertTrue(self.a.archive_health()['sqlite_ok'])
    def test_no_auto_delete_on_retention(self):
        w=self.a.watch_folder_add('Test PC Game',self.source)
        self.a.configure_backup_rule(w,enabled=True,keep_latest=1)
        self.assertEqual(self.a.backup_rules()[0]['keep_latest'],1)
        self.assertEqual(len(self.a.list_saves()),1)

if __name__=='__main__':unittest.main()

class V13LibraryTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();p=Path(self.t.name)
        self.source=p/'input';self.source.mkdir();(self.source/'data').write_text('hello')
        self.a=ArchiveV13(p/'archive')
        self.sid=self.a.import_pc_save(self.source,'My PC Game',label='Slot One')['id']
    def tearDown(self):self.a.close();self.t.cleanup()
    def test_smart_label(self):
        label=self.a.smart_save_name(self.sid)
        self.assertIn('My PC Game',label);self.assertIn('PC',label)
    def test_timeline(self):
        self.assertEqual(self.a.save_timeline('My PC Game')[0]['id'],self.sid)
        self.assertEqual(self.a.save_timeline('Other'),[])
    def test_duplicate_detection(self):self.assertEqual(self.a.duplicate_candidates(),[])
    def test_search(self):
        self.assertEqual(self.a.universal_search('Slot One')[0]['id'],self.sid)
        self.assertEqual(self.a.universal_search('My PC')[0]['id'],self.sid)
        self.assertEqual(self.a.universal_search('NOMATCH'),[])
