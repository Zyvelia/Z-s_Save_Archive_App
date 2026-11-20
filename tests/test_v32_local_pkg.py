import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zarchive.retail2pkg_v31 import REQUIRED_FILES, build_pkgs_locally, prepare_local_batch


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

    def test_disc_input_runs_the_selected_batch_on_a_copy(self):
        from test_v20 import write_sfo

        disc = self.work.parent / 'disc backup' / 'PS3_GAME'
        disc.mkdir(parents=True)
        write_sfo(disc / 'PARAM.SFO')
        batch = b'@echo off\r\nCFW2OFW_Helper\r\npause>nul'
        (self.kit / 'Retail2Pkg.bat').write_bytes(batch)

        def builder(command, **kw):
            stage = Path(kw['cwd'])
            self.assertEqual(command[-1], 'Retail2Pkg.bat')
            self.assertEqual((stage / 'Retail2Pkg.bat').read_bytes(), batch)
            self.assertTrue((stage / 'PS3_GAME' / 'PARAM.SFO').is_file())
            (stage / 'PS3_GAME' / 'PARAM.SFO').unlink()
            (stage / 'Game.pkg').write_bytes(b'\x7fPKG' + b'X' * 100)
            return SimpleNamespace(returncode=0, stdout='built', stderr='')

        result = build_pkgs_locally(disc, self.kit, self.out, runner=builder)
        self.assertTrue(result['success'])
        self.assertTrue((disc / 'PARAM.SFO').is_file())
        self.assertEqual((self.kit / 'Retail2Pkg.bat').read_bytes(), batch)
        self.assertTrue((self.out / 'Game.pkg').is_file())

    def test_prepare_batch_folder_from_udf_iso(self):
        from test_v20 import write_sfo

        iso = self.out / 'game.iso'
        iso.write_bytes(b'\0' * 0x8001 + b'NSR03')
        extractor = self.kit / '7z.exe'
        extractor.touch()

        def extract(command, cancelled):
            self.assertEqual(Path(command[0]), extractor)
            self.assertEqual(Path(command[-1]), iso)
            destination = Path(next(arg[2:] for arg in command if arg.startswith('-o')))
            game = destination / 'PS3_GAME'
            game.mkdir()
            write_sfo(game / 'PARAM.SFO')

        with patch('zarchive.iso_converter_v20.extract_iso', side_effect=extract):
            result = prepare_local_batch(iso, self.kit, self.out, extractor=extractor)
        staged = Path(result['staging'])
        self.assertTrue((staged / 'PS3_GAME' / 'PARAM.SFO').is_file())
        self.assertEqual((staged / 'Retail2Pkg.bat').read_bytes(),
                         (self.kit / 'Retail2Pkg.bat').read_bytes())
        self.assertTrue(iso.is_file())

    def test_iso_to_pkg_extracts_before_running_the_batch(self):
        from test_v20 import write_sfo

        iso = self.out / 'disc.iso'
        iso.write_bytes(b'\0' * 0x8001 + b'CD001')
        extractor = self.kit / '7z.exe'
        extractor.touch()
        messages = []

        def extract(command, cancelled):
            destination = Path(next(arg[2:] for arg in command if arg.startswith('-o')))
            game = destination / 'PS3_GAME'
            game.mkdir()
            write_sfo(game / 'PARAM.SFO')

        def builder(command, **kwargs):
            stage = Path(kwargs['cwd'])
            for path in ('PS3_GAME/PARAM.SFO', 'CFW2OFW_Helper.exe', 'Retail2Pkg.bat'):
                self.assertTrue((stage / path).is_file(), path)
            self.assertIn('PS3_GAME is ready beside', '\n'.join(messages))
            (stage / 'Disc.pkg').write_bytes(b'\x7fPKG' + b'x' * 100)
            return SimpleNamespace(returncode=0, stdout='', stderr='')

        with patch('zarchive.iso_converter_v20.extract_iso', side_effect=extract):
            result = build_pkgs_locally(iso, self.kit, self.out, extractor=extractor,
                                        runner=builder, progress=messages.append)
        self.assertTrue(result['success'])
        self.assertEqual(result['packages'], [str(self.out / 'Disc.pkg')])

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

    def test_staged_existing_pkg_does_not_count_as_new_output(self):
        (self.work / 'BLUS12345' / 'Old.pkg').write_bytes(b'\x7fPKG' + b'X' * 100)

        def no_output(command, **kw):
            return SimpleNamespace(returncode=0, stdout='done', stderr='')

        with patch('zarchive.retail2pkg_v31.inspect_conversion_output', return_value=self.folder_report):
            result = build_pkgs_locally(self.work, self.kit, self.out, runner=no_output)
        self.assertFalse(result['success'])
        self.assertFalse((self.out / 'Old.pkg').exists())

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
