import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zarchive.editor_v18 import ArchiveV18
from zarchive.storage import Archive, discover_saves, folder_digest, read_param_sfo


def write_sfo(path, entries=None):
    entries = entries or {'TITLE':'Borderlands 2','TITLE_ID':'BLUS30982','SUB_TITLE':'Chapter 01'}
    keys=bytearray();values=bytearray();indexes=bytearray()
    for key,value in entries.items():
        key_offset=len(keys);keys += key.encode()+b'\x00'
        raw=value.encode()+b'\x00';value_offset=len(values);values += raw
        indexes += struct.pack('<HHIII',key_offset,0x0204,len(raw),len(raw),value_offset)
    ks=20+len(indexes);vs=ks+len(keys)
    path.write_bytes(struct.pack('<4sIIII',b'\x00PSF',0x101,ks,vs,len(entries))+indexes+keys+values)

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.home=Path(self.tmp.name);self.source=self.home/'USB'/'SAVE1';self.source.mkdir(parents=True)
        write_sfo(self.source/'PARAM.SFO');(self.source/'DATA.BIN').write_bytes(b'example save data')
        self.db=Archive(self.home/'library');self.addCleanup(self.db.close)
    def test_sfo(self):
        self.assertEqual(read_param_sfo(self.source/'PARAM.SFO')['TITLE_ID'],'BLUS30982')
    def test_discovery(self):
        self.assertEqual(discover_saves(self.home/'USB'),[self.source])
    def test_corrupted_sfo(self):
        (self.source/'PARAM.SFO').write_bytes(b'bad')
        with self.assertRaises(ValueError):read_param_sfo(self.source/'PARAM.SFO')
    def test_import_and_original_preserved(self):
        record=self.db.import_save(self.source,'Legit')
        self.assertEqual(record['title_id'],'BLUS30982')
        self.assertEqual(self.db.stats(),(1,1,0))
        self.assertEqual((self.source/'DATA.BIN').read_bytes(),b'example save data')
        self.assertEqual((self.db.root/record['stored_path']/'DATA.BIN').read_bytes(),b'example save data')
    def test_duplicate_rejected(self):
        self.db.import_save(self.source)
        with self.assertRaisesRegex(ValueError,'Identical save'):self.db.import_save(self.source)
        self.assertEqual(len(self.db.list_saves()),1)
    def test_update(self):
        record=self.db.import_save(self.source)
        self.db.update(record['id'],category='Modded',label='Boosted',notes='Max money',status='Verified')
        row=self.db.list_saves('Boosted')[0]
        self.assertEqual((row['category'],row['notes'],row['status']),('Modded','Max money','Verified'))
        self.assertEqual(self.db.stats(),(1,1,1))
    def test_bad_category(self):
        with self.assertRaises(ValueError):self.db.import_save(self.source,'Fake')
    def test_digest_changes(self):
        a=folder_digest(self.source)[0];(self.source/'DATA.BIN').write_bytes(b'different')
        self.assertNotEqual(a,folder_digest(self.source)[0])
    def test_settings_persist(self):
        self.db.import_save(self.source);self.assertEqual(len(self.db.games()),1)
        other=Archive(self.home/'library')
        try:self.assertEqual(len(other.list_saves()),1)
        finally:other.close()
    def test_no_meta(self):
        (self.source/'PARAM.SFO').unlink()
        with self.assertRaises(ValueError):self.db.import_save(self.source)

    def test_remove_saves_deletes_only_selected_archived_copies(self):
        first = self.db.import_save(self.source)
        local_file = self.home / 'DATA2.BIN'
        local_file.write_bytes(b'other save')
        second = self.db.import_ps4_save(local_file, 'Second game')
        third = self.db.import_pc_save(local_file, 'Third game')

        count, remaining = self.db.remove_saves([first['id'], second['id'], first['id']])
        self.assertEqual((count, remaining), (2, []))
        self.assertEqual([row['id'] for row in self.db.list_saves()], [third['id']])
        for record in (first, second):
            self.assertFalse((self.db.root / record['stored_path']).exists())
        self.assertEqual((self.source / 'DATA.BIN').read_bytes(), b'example save data')
        self.assertEqual(local_file.read_bytes(), b'other save')
        self.assertEqual(self.db.remove_saves([second['id']]), (0, []))
        self.db.import_save(self.source)

    def test_failed_batch_reinstates_archived_files_and_entries(self):
        first = self.db.import_save(self.source)
        second = self.db.import_pc_save(self.source, 'Second game')
        delete_record = self.db._delete_save_record

        def fail_second(record_id):
            if record_id == second['id']:
                raise OSError('simulated failure')
            delete_record(record_id)

        with patch.object(self.db, '_delete_save_record', side_effect=fail_second):
            with self.assertRaisesRegex(OSError, 'simulated failure'):
                self.db.remove_saves([first['id'], second['id']])
        self.assertEqual(len(self.db.list_saves()), 2)
        self.assertTrue(all((self.db.root / row['stored_path']).is_dir() for row in (first, second)))

    def test_reopening_archive_recovers_staged_copy_for_indexed_save(self):
        record = self.db.import_save(self.source)
        original = self.db.root / record['stored_path']
        pending = original.with_name('.removing-' + record['id'])
        original.rename(pending)
        other = Archive(self.db.root)
        try:
            self.assertTrue(original.is_dir())
            self.assertFalse(pending.exists())
            self.assertEqual(other.list_saves()[0]['id'], record['id'])
        finally:
            other.close()

    def test_removing_save_with_edit_history_preserves_backup_and_output(self):
        archive = ArchiveV18(self.home / 'extended')
        self.addCleanup(archive.close)
        save = archive.import_save(self.source)
        backup = archive.make_backup(save['id'])
        output = self.home / 'edited.bin'
        output.write_bytes(b'edited copy')
        with archive.conn:
            archive.conn.execute('INSERT INTO edits_v18 VALUES (?,?,?,?,?,?,?,?)',
                                 ('edit', save['id'], 'editor', str(backup), str(output), 'old', 'new', 'now'))
        self.assertEqual(archive.remove_saves([save['id']]), (1, []))
        self.assertFalse(archive.list_saves())
        self.assertFalse(archive.conn.execute('SELECT 1 FROM edits_v18').fetchone())
        self.assertTrue(backup.is_file())
        self.assertEqual(output.read_bytes(), b'edited copy')

    def test_recently_removed_preserves_metadata_attachments_and_pins(self):
        archive = ArchiveV18(self.home / 'trash')
        self.addCleanup(archive.close)
        save = archive.import_save(self.source, label='Checkpoint', notes='Keep these notes')
        record_id = save['id']
        archive.set_tags(record_id, ['Boss'])
        archive.pin_save(record_id)
        backup = archive.make_backup(record_id)
        screenshot = self.home / 'screenshot.png'
        screenshot.write_bytes(b'screenshot')
        attachment = archive.screenshot(record_id, screenshot)
        stored = archive.root / save['stored_path']

        self.assertEqual(archive.trash_saves([record_id, record_id]), 1)
        self.assertEqual(archive.trash_saves([record_id]), 0)
        self.assertEqual(archive.list_saves(), [])
        self.assertEqual(archive.games(), [])
        self.assertEqual(archive.pinned()['saves'], [])
        self.assertEqual(archive.search_page()['total'], 0)
        self.assertEqual(archive.universal_search('Checkpoint'), [])
        removed, = archive.list_removed_saves()
        self.assertEqual((removed['id'], removed['label']), (record_id, 'Checkpoint'))
        self.assertTrue(stored.is_dir())

        reopened = ArchiveV18(archive.root)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.restore_removed_saves([record_id]), 1)
        self.assertEqual(reopened.restore_removed_saves([record_id]), 0)
        restored, = reopened.list_saves()
        self.assertEqual((restored['label'], restored['notes'], restored['tags']),
                         ('Checkpoint', 'Keep these notes', ['Boss']))
        self.assertEqual(reopened.pinned()['saves'][0]['id'], record_id)
        self.assertEqual(len(reopened.backup_history(record_id)), 1)
        self.assertEqual(len(reopened.screenshots(record_id)), 1)
        self.assertEqual(reopened.list_removed_saves(), [])
        self.assertTrue(backup.is_file() and attachment.is_file())

    def test_recently_removed_restore_keeps_active_duplicate_and_is_atomic(self):
        first = self.db.import_save(self.source)
        other = self.db.import_pc_save(self.source, 'Second game')
        self.db.trash_saves([first['id'], other['id']])
        duplicate = self.db.import_save(self.source)
        with self.assertRaisesRegex(ValueError, 'identical active save'):
            self.db.restore_removed_saves([other['id'], first['id']])
        self.assertEqual([row['id'] for row in self.db.list_saves()], [duplicate['id']])
        self.assertEqual({row['id'] for row in self.db.list_removed_saves()}, {other['id'], first['id']})

    def test_recently_removed_permanent_delete_never_applies_to_restored_save(self):
        save = self.db.import_save(self.source)
        record_id = save['id']
        self.db.trash_saves([record_id])
        self.db.restore_removed_saves([record_id])
        self.assertEqual(self.db.remove_saves([record_id], only_removed=True), (0, []))
        self.assertTrue((self.db.root / save['stored_path']).is_dir())
        self.db.trash_saves([record_id])
        self.assertEqual(self.db.remove_saves([record_id], only_removed=True), (1, []))
        self.assertFalse((self.db.root / save['stored_path']).exists())
        self.assertEqual(self.db.list_removed_saves(), [])
        self.assertTrue((self.source / 'DATA.BIN').is_file())

    def test_migrating_an_existing_archive_leaves_its_saves_active(self):
        save = self.db.import_save(self.source)
        self.db.conn.executescript('DROP VIEW temp.active_saves; ALTER TABLE saves DROP COLUMN removed_at;')
        reopened = Archive(self.db.root)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.list_saves()[0]['id'], save['id'])
        self.assertEqual(reopened.list_removed_saves(), [])

if __name__=='__main__':unittest.main()
