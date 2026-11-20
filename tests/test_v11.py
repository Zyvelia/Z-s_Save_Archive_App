import json, tempfile, unittest
from pathlib import Path
from zarchive.upgrade_v11 import ArchiveV11

class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.arc=ArchiveV11(self.root/'archive');self.addCleanup(self.arc.close)
        self.src=self.root/'pc';self.src.mkdir();(self.src/'save.dat').write_bytes(b'abc')
        self.a=self.arc.import_pc_save(self.src,'Example Game')
    def test_variant_and_game_progress(self):
        vid=self.arc.create_variant('PC','Example Game','Starter')
        self.arc.assign_variant(self.a['id'],vid)
        self.assertEqual(self.arc.variants('PC','Example Game')[0]['name'],'Starter')
        self.arc.set_game_progress('PC','Example Game','Completed')
        self.assertEqual(self.arc.game_progress_list()[0]['progress'],'Completed')
        with self.assertRaises(ValueError):self.arc.set_game_progress('PC','Example Game','Invalid')
    def test_bulk_edit_and_undo(self):
        op=self.arc.bulk_metadata([self.a['id']],category='Modded',tags=['Max Money'],visibility='Private')
        record=self.arc.list_saves()[0]
        self.assertEqual((record['category'],record['tags']),('Modded',['Max Money']))
        self.arc.undo_metadata(op)
        self.assertEqual(self.arc.list_saves()[0]['category'],'Unsorted')
        self.assertEqual(self.arc.list_saves()[0]['tags'],[])
        with self.assertRaises(ValueError):self.arc.undo_metadata(op)
    def test_diff(self):
        self.src.joinpath('save.dat').write_bytes(b'xyz')
        self.src.joinpath('new.txt').write_text('new')
        b=self.arc.import_pc_save(self.src,'Example Game')
        delta=self.arc.save_diff(self.a['id'],b['id'])
        self.assertEqual(delta['changed'],['save.dat'])
        self.assertEqual(delta['added'],['new.txt'])
    def test_watch_scan_changes_and_dedup(self):
        self.arc.watch_folder_add('Example Game',self.src)
        report=self.arc.scan_watch_folders()
        self.assertEqual(report[0]['state'],'duplicate')
        self.assertEqual(self.arc.scan_watch_folders()[0]['state'],'unchanged')
        (self.src/'save.dat').write_bytes(b'changed')
        self.assertEqual(self.arc.scan_watch_folders()[0]['state'],'imported')
    def test_compression_archive(self):
        self.arc.set_compression('Fast')
        self.assertEqual(self.arc.compression(),'Fast')
        out=self.arc.compressed_backup(self.a['id'],self.root/'out.zip')
        import zipfile
        with zipfile.ZipFile(out) as z:self.assertEqual(z.read('save/save.dat'),b'abc')
        with self.assertRaises(FileExistsError):self.arc.compressed_backup(self.a['id'],out)
    def test_catalog_and_payload(self):
        pages=self.arc.github_pages_catalog(self.root/'site')
        self.assertTrue((pages/'index.html').is_file())
        self.assertTrue((pages/'.nojekyll').exists())
        self.assertTrue(self.arc.github_release_payload('v1.2','Release')['draft'])
        with self.assertRaises(ValueError):self.arc.github_release_payload('../bad','X')
    def test_task_history(self):
        self.arc.record_task('import','success','done')
        self.assertEqual(self.arc.tasks()[0]['status'],'success')
        with self.assertRaises(ValueError):self.arc.record_task('import','oops')
    def test_migration_non_destructive(self):
        sid=self.a['id'];self.arc.close()
        self.arc=ArchiveV11(self.root/'archive')
        self.assertEqual(self.arc._save(sid)['game'],'Example Game')

class MigrationAndPublishingTests(unittest.TestCase):
    def test_upgrade_existing_v10_database(self):
        from zarchive.upgrade_v10 import ArchiveV10
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'archive';src=Path(tmp)/'files';src.mkdir();(src/'data.bin').write_bytes(b'save')
            old=ArchiveV10(root);record=old.import_pc_save(src,'My Game');old.close()
            upgraded=ArchiveV11(root)
            self.assertEqual(upgraded._save(record['id'])['file_hash'],record['file_hash'])
            self.assertEqual(upgraded.variants(),[])
            upgraded.close()
    def test_github_upload_guardrails_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=ArchiveV11(Path(tmp)/'archive')
            src=Path(tmp)/'source';src.mkdir();(src/'data').write_bytes(b'x')
            item=a.import_pc_save(src,'Test')
            with self.assertRaises(ValueError):
                a.github_upload_verified_save('owner','repo',1,item['id'],reviewed=False,token='dummy')
            with self.assertRaises(ValueError):
                a.github_upload_verified_save('owner','repo',1,item['id'],reviewed=True,token='dummy')
            a.close()
