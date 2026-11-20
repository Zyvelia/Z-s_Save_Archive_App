import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zarchive.retail2pkg_v31 import REQUIRED_FILES, build_pkgs_locally


class LocalPKGTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.kit = root / 'kit'
        self.kit.mkdir()
        for name in REQUIRED_FILES:
            (self.kit / name).write_bytes(b'fixture')
        self.work = root / 'workspace'
        self.work.mkdir()
        (self.work / 'conversion_manifest.json').write_text('{}', encoding='utf-8')
        game = self.work / 'BLUS12345'
        game.mkdir()
        for name in ('NPUB12345', 'BLUS12345'):
            folder = game / name
            folder.mkdir()
            (folder / 'PARAM.SFO').write_bytes(b'fixture')
        self.out = root / 'local_packages'
        self.out.mkdir()
        self.folder_report = {'folders': [{'relative_path': 'BLUS12345/NPUB12345'},
                                          {'relative_path': 'BLUS12345/BLUS12345'}]}

    def _mockbuild(self, command, **kw):
        self.assertEqual(command, ['cmd.exe', '/d', '/c', 'call', 'Retail2Pkg.bat'])
        self.assertEqual(kw['stdin'], __import__('subprocess').DEVNULL)
        stage = Path(kw['cwd'])
        self.assertEqual(stage.parent, self.out)
        (stage / 'BLUS12345' / 'Game.pkg').write_bytes(b'\x7fPKG' + b'X' * 100)
        return SimpleNamespace(returncode=0, stdout='built', stderr='')

    def test_build_without_ftp_and_preserve_original(self):
        with patch('zarchive.retail2pkg_v31.inspect_conversion_output', return_value=self.folder_report):
            result = build_pkgs_locally(self.work, self.kit, self.out, runner=self._mockbuild)
        self.assertTrue(result['success'])
        self.assertEqual(len(result['packages']), 1)
        self.assertEqual((self.out / 'Game.pkg').read_bytes()[:4], b'\x7fPKG')
        self.assertTrue((self.work / 'BLUS12345' / 'NPUB12345' / 'PARAM.SFO').exists())
        self.assertTrue((Path(result['staging']) / 'LOCAL_BUILD_RESULT.txt').exists())

    def test_reject_output_inside_source(self):
        with self.assertRaisesRegex(ValueError, 'separate'):
            build_pkgs_locally(self.work, self.kit, self.work, runner=self._mockbuild)

    def test_failed_builder_does_not_claim_pkg(self):
        def fail(command, **kw):
            return SimpleNamespace(returncode=2, stdout='Some folders are missing', stderr='')
        with patch('zarchive.retail2pkg_v31.inspect_conversion_output', return_value=self.folder_report):
            result = build_pkgs_locally(self.work, self.kit, self.out, runner=fail)
        self.assertFalse(result['success'])
        self.assertEqual(result['packages'], [])

    def test_reject_invalid_pkg_magic(self):
        def bad(command, **kw):
            (Path(kw['cwd']) / 'bad.pkg').write_bytes(b'wrong' * 40)
            return SimpleNamespace(returncode=0, stdout='done', stderr='')
        with patch('zarchive.retail2pkg_v31.inspect_conversion_output', return_value=self.folder_report):
            result = build_pkgs_locally(self.work, self.kit, self.out, runner=bad)
        self.assertFalse(result['success'])
        self.assertFalse((self.out / 'bad.pkg').exists())


if __name__ == '__main__':
    unittest.main()
