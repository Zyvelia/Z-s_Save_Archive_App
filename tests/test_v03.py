import json
import tempfile
import unittest
from pathlib import Path
from zarchive.enhanced import EnhancedArchive

class V03(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.a=EnhancedArchive(self.base/'archive')
        self.addCleanup(self.a.close)
        d=self.base/'testfile';d.write_bytes(b'Save bytes')
        self.row=self.a.import_pc_save(d,'Test Game')
        self.sid=self.row['id']

    def test_backup_restore_history_integrity(self):
        b=self.a.make_backup(self.sid)
        history=self.a.backup_history(self.sid)
        self.assertEqual(len(history),1)
        bid=history[0]['id']
        self.assertTrue(self.a.verify_backup(bid))
        target=self.base/'restored'
        self.a.restore_backup(bid,target)
        self.assertEqual((target/'testfile').read_bytes(),b'Save bytes')
        with self.assertRaises(FileExistsError):self.a.restore_backup(bid,target)
        self.assertTrue(self.a.audit()==[])
        with b.open('ab') as f:f.write(b'TAMPER')
        self.assertFalse(self.a.verify_backup(bid))
        self.assertTrue(self.a.audit())

    def test_tags_colors_bulk_and_collection(self):
        self.a.bulk_tag([self.sid],['All Unlocks','Max Money'])
        self.a.set_tag_color('Max Money','Amber')
        self.assertIn(('Max Money','Amber'),self.a.tag_styles())
        self.assertIn('Max Money',self.a.list_saves()[0]['tags'])
        cid=self.a.create_collection('Favorites')
        self.a.add_to_collection(cid,'PC','Test Game')
        self.assertEqual(self.a.collection_games(cid),[('PC','Test Game')])

    def test_release_requires_public_and_verified(self):
        target=self.base/'release.zip'
        with self.assertRaises(ValueError):self.a.export_release(self.sid,target)
        self.a.set_visibility(self.sid,'Public')
        with self.assertRaises(ValueError):self.a.export_release(self.sid,target)
        self.a.update(self.sid,category='Modded',label='boost',notes='test',status='Verified')
        self.a.export_release(self.sid,target)
        self.assertTrue(target.exists())

    def test_migration_existing_v02(self):
        from zarchive.storage import Archive
        p=self.base/'old'
        old=Archive(p)
        f=self.base/'another';f.write_text('data')
        old.import_pc_save(f,'Legacy');old.close()
        new=EnhancedArchive(p)
        self.addCleanup(new.close)
        self.assertEqual(new.stats()[1],1)
        self.assertEqual(new.list_saves()[0]['visibility'],'Private')

    def test_screenshot(self):
        f=self.base/'shot.png';f.write_bytes(b'fake png')
        result=self.a.screenshot(self.sid,f)
        self.assertTrue(result.is_file())
        self.assertEqual(len(self.a.screenshots(self.sid)),1)

if __name__=='__main__':unittest.main()

class NestedBackup(unittest.TestCase):
    def test_nested_directory_restore(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);a=EnhancedArchive(root/'archive')
            try:
                src=root/'src';(src/'nested'/'deep').mkdir(parents=True)
                (src/'root.bin').write_bytes(b'root')
                (src/'nested'/'inside.bin').write_bytes(b'middle')
                (src/'nested'/'deep'/'tail.bin').write_bytes(b'end')
                row=a.import_pc_save(src,'Nested')
                a.make_backup(row['id'])
                bid=a.backup_history(row['id'])[0]['id']
                self.assertTrue(a.verify_backup(bid))
                a.restore_backup(bid,root/'out')
                self.assertEqual((root/'out'/'nested'/'deep'/'tail.bin').read_bytes(),b'end')
            finally:a.close()
