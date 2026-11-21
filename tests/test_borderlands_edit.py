from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from zarchive.borderlands_edit import EDITORS, match_editor, open_editor, stage_save
from zarchive.storage import Archive


class BorderlandsEditTests(unittest.TestCase):
    def test_ps4_working_copy_can_be_reimported_without_changing_original(self):
        with TemporaryDirectory() as scratch:
            root = Path(scratch)
            archive = Archive(root / 'archive')
            self.addCleanup(archive.close)
            original = root / 'CUSA12345' / '01.sav'
            original.parent.mkdir()
            original.write_bytes(b'initial save')
            output = root / 'working'
            output.mkdir()
            folder = stage_save(original, output, archive.root, platform='PS4')
            (folder / original.name).write_bytes(b'edited save')
            row = archive.import_ps4_save(folder, 'Borderlands 3')
            self.assertEqual(row['title_id'], 'CUSA12345')
            self.assertEqual(original.read_bytes(), b'initial save')
            self.assertTrue(match_editor(next(item for item in EDITORS if item.key == 'bl3_ps4'), row))

    def test_editor_receives_only_the_working_directory(self):
        with TemporaryDirectory() as scratch:
            root = Path(scratch).resolve()
            editor = root / 'editor.exe'
            editor.write_bytes(b'MZ')
            folder = root / 'copy'
            folder.mkdir()
            runner = Mock()
            open_editor(editor, folder, runner=runner)
            runner.assert_called_once_with([str(editor)], cwd=folder)

    def test_copy_cannot_be_staged_inside_archive_or_source(self):
        with TemporaryDirectory() as scratch:
            root = Path(scratch)
            archive = root / 'archive'
            archive.mkdir()
            original = root / 'original'
            original.mkdir()
            with self.assertRaisesRegex(ValueError, 'outside the archive'):
                stage_save(original, archive, archive, platform='PS3')
            with self.assertRaisesRegex(ValueError, 'outside the source'):
                stage_save(original, original, archive, platform='PS3')
