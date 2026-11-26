"""Advanced actions must respect the same backup-first source edit guarantees."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import hashlib
import unittest

from zarchive.bl3_inplace import save_advanced_with_backup


def sha(data):
    return hashlib.sha256(data).hexdigest()


class BL3AdvancedBackupTests(unittest.TestCase):
    @patch('zarchive.bl3_advanced.write_advanced_copy')
    def test_advanced_edit_updates_original_only_after_verified_backup(self, writer):
        with TemporaryDirectory() as scratch:
            source = Path(scratch) / 'profile'
            original = b'GVAS' + b'profile' * 10
            source.write_bytes(original)
            def fake_writer(src, output, **kwargs):
                self.assertEqual(kwargs['kind'], 'profile')
                self.assertEqual(kwargs['platform'], 'PS4')
                self.assertEqual(kwargs['actions'], [{'op': 'guardian_tokens', 'value': 15}])
                Path(output).write_bytes(b'GVAS' + b'updated' * 10)
                return Path(output)
            writer.side_effect = fake_writer
            result, backup = save_advanced_with_backup(
                source, kind='profile', platform='PS4',
                expected_sha256=sha(original),
                actions=[{'op': 'guardian_tokens', 'value': 15}])
            self.assertEqual(result, source)
            self.assertNotEqual(source.read_bytes(), original)
            self.assertEqual(backup.read_bytes(), original)
            self.assertEqual(backup.parent.name, 'ZSaveArchive_Backups')

    @patch('zarchive.bl3_advanced.write_advanced_copy', side_effect=ValueError('Unsupported item'))
    def test_decoder_failure_does_not_create_backup_or_modify_source(self, writer):
        with TemporaryDirectory() as scratch:
            source = Path(scratch) / '1'
            original = b'GVAS' + b'character' * 10
            source.write_bytes(original)
            with self.assertRaisesRegex(ValueError, 'Unsupported item'):
                save_advanced_with_backup(
                    source, kind='character', platform='PC',
                    expected_sha256=sha(original),
                    actions=[{'op': 'item_add', 'code': 'BL3(YWJj)'}])
            self.assertEqual(source.read_bytes(), original)
            self.assertFalse((source.parent / 'ZSaveArchive_Backups').exists())

    def test_advanced_bad_kind_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            save_advanced_with_backup('/nonexistent', kind='future',
                                      platform='Xbox', expected_sha256='',
                                      actions=[{'op': 'max_sdu'}])


if __name__ == '__main__':
    unittest.main()
