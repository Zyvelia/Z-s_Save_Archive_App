"""In-place save writes must create and verify backups before replacement."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from zarchive.bl3_inplace import save_with_backup


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class InPlaceSaveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.original = Path(self.temp.name) / '1'
        self.original.write_bytes(b'GVAS-original-character')
        self.expected = digest(self.original)

    @staticmethod
    def writer(source, dest, *, expected_sha256, platform, **values):
        assert digest(source) == expected_sha256
        Path(dest).write_bytes(b'GVAS-edited-character')

    @patch('zarchive.bl3_inplace.write_character_copy')
    def test_edits_same_file_with_verified_backup(self, writer):
        writer.side_effect = self.writer
        output, backup = save_with_backup(
            self.original, kind='character', platform='PS4',
            expected_sha256=self.expected, name='Zane', level=50,
            money=200, eridium=50)
        self.assertEqual(output, self.original)
        self.assertEqual(self.original.read_bytes(), b'GVAS-edited-character')
        self.assertEqual(backup.parent.name, 'ZSaveArchive_Backups')
        self.assertEqual(backup.read_bytes(), b'GVAS-original-character')

    @patch('zarchive.bl3_inplace.write_character_copy')
    def test_stale_edit_does_not_modify_file(self, writer):
        self.original.write_bytes(b'changed-on-disk')
        with self.assertRaisesRegex(ValueError, 'changed'):
            save_with_backup(self.original, kind='character', platform='PS4',
                             expected_sha256=self.expected, name='Zane',
                             level=50, money=200, eridium=50)
        writer.assert_not_called()
        self.assertFalse((self.original.parent / 'ZSaveArchive_Backups').exists())

    @patch('zarchive.bl3_inplace.write_character_copy')
    def test_failed_codec_does_not_change_file_or_make_backup(self, writer):
        writer.side_effect = ValueError('decoder rejected file')
        with self.assertRaisesRegex(ValueError, 'decoder rejected'):
            save_with_backup(self.original, kind='character', platform='PS4',
                             expected_sha256=self.expected, name='Zane',
                             level=50, money=200, eridium=50)
        self.assertEqual(digest(self.original), self.expected)
        self.assertFalse((self.original.parent / 'ZSaveArchive_Backups').exists())

    def test_rejects_unknown_kind(self):
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            save_with_backup(self.original, kind='inventory', platform='PC',
                             expected_sha256=self.expected)

    def test_symlink_rejected(self):
        link = self.original.parent / 'linked'
        try:
            link.symlink_to(self.original)
        except (OSError, NotImplementedError):
            self.skipTest('File symlinks unavailable')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            save_with_backup(link, kind='character', platform='PC',
                             expected_sha256=self.expected)


if __name__ == '__main__':
    unittest.main()
