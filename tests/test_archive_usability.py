import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from zarchive.editor_v18 import ArchiveV18
from zarchive.removable_drives import RemovableDrive, remembered_drive

try:
    from zarchive.ui_artwork import steam_app_id
    from zarchive.ui_preferences import sorted_by, valid_sort
except ImportError:
    sorted_by = steam_app_id = None


class ArchiveUsabilityTests(unittest.TestCase):
    def test_checkpoint_survives_reopen_and_is_searchable_and_backed_up(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'save.dat'
            source.write_bytes(b'save')
            archive = ArchiveV18(root / 'archive')
            try:
                record_id = archive.import_pc_save(source, 'Game Name', label='Original label')['id']
                archive.set_checkpoint(record_id, 'Boss', '  First   encounter  ')
                self.assertEqual(archive.search_page('first encounter')['total'], 1)
                path = archive.backup_zip(record_id, root / 'backup.zip')
                with ZipFile(path) as backup:
                    checkpoint = json.loads(backup.read('manifest.json'))['checkpoint']
                self.assertEqual(checkpoint, {'kind': 'Boss', 'label': 'First encounter'})
            finally:
                archive.close()

            archive = ArchiveV18(root / 'archive')
            try:
                record, = archive.list_saves('First encounter')
                self.assertEqual(record['label'], 'Original label')
                self.assertEqual(record['checkpoint_kind'], 'Boss')
                archive.set_checkpoint(record_id, 'Boss', '')
                self.assertEqual(archive.list_saves('First encounter'), [])
            finally:
                archive.close()

    def test_remembered_usb_matches_volume_serial_after_drive_letter_changes(self):
        preference = {'serial': 'ABCD1234', 'label': 'Saves'}
        unrelated = RemovableDrive('381FF216', 'Saves', Path('E:/'))
        changed_letter = RemovableDrive('ABCD1234', 'Renamed Saves', Path('F:/'))
        self.assertIsNone(remembered_drive(preference, [unrelated]))
        self.assertEqual(remembered_drive(preference, [unrelated, changed_letter]), changed_letter)
        cloned_serial = RemovableDrive('ABCD1234', 'Copy', Path('G:/'))
        self.assertIsNone(remembered_drive(preference, [changed_letter, cloned_serial]))

    @unittest.skipIf(sorted_by is None, 'PySide6 is required for sorting preferences')
    def test_multi_column_sort_uses_independent_directions_and_numeric_versions(self):
        rows = [('A', (1, 9)), ('B', (1, 0)), ('A', (1, 10)), ('B', (2, 0))]
        columns = {'Game': 0, 'Version': 1}
        order = [('Game', False), ('Version', True)]
        self.assertEqual(sorted_by(rows, order, lambda row, field: row[columns[field]]),
                         [('A', (1, 10)), ('A', (1, 9)), ('B', (2, 0)), ('B', (1, 0))])
        self.assertEqual(valid_sort([['Game', True], ['Game', False]], columns, order), order)

    @unittest.skipIf(steam_app_id is None, 'PySide6 is required for the artwork picker')
    def test_steam_artwork_uses_only_app_ids_and_official_store_links(self):
        self.assertEqual(steam_app_id('1285190'), '1285190')
        self.assertEqual(steam_app_id('https://store.steampowered.com/app/1285190/Borderlands_4/'), '1285190')
        self.assertIsNone(steam_app_id('https://store.steampowered.com.evil.test/app/1285190'))
        self.assertIsNone(steam_app_id('https://store.steampowered.com/bundle/1285190'))
        self.assertIsNone(steam_app_id('1285190/../../image'))
