import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile

from test_v20 import write_sfo
from zarchive.iso_converter_v20 import extract_iso, stage_conversion
from zarchive.retail2pkg_v31 import LAUNCHER_FOLDER, TOOL_FILES, run_launcher


class DiscPackageBuildTests(unittest.TestCase):
    def test_extraction_reports_progress_from_the_child_process(self):
        reported = []
        extract_iso([sys.executable, '-u', '-c',
                     "import time; print('  21% 1 - file', flush=True); time.sleep(0.8)"],
                    None, extraction_progress=reported.append)
        self.assertEqual(reported, [0, 21, 100])

    def test_extraction_retains_error_before_progress_noise(self):
        command = [sys.executable, '-c', "import sys; "
                   "print('ERROR: Unexpected end of archive'); "
                   "print(' 99% - PS3UPDAT.PUP' * 500); "
                   "print('Open Errors: 1'); sys.exit(2)"]
        with self.assertRaises(RuntimeError) as raised:
            extract_iso(command, None)
        message = str(raised.exception)
        self.assertIn('Unexpected end of archive', message)
        self.assertIn('Open Errors: 1', message)
        self.assertNotIn('PS3UPDAT.PUP', message)

    def test_winrar_command_extracts_to_the_staging_directory(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            iso = root / 'disc.iso'
            iso.write_bytes(b'\0' * 0x8001 + b'CD001')
            toolkit = root / 'tools'
            toolkit.mkdir()
            helper = toolkit / 'CFW2OFW_Helper.exe'
            helper.touch()
            winrar = toolkit / 'WinRAR.exe'
            winrar.touch()
            stage = root / 'stage'

            def extract(command, cancelled, progress, extraction_progress):
                self.assertEqual(command[:4], [str(winrar), 'x', '-ibck', '-y'])
                self.assertEqual(Path(command[-2]), iso)
                self.assertEqual(Path(command[-1]), stage / 'extracted')
                game = Path(command[-1]) / 'PS3_GAME'
                game.mkdir()
                write_sfo(game / 'PARAM.SFO')

            with patch('zarchive.iso_converter_v20.extract_iso', side_effect=extract):
                stage_conversion(iso, helper, stage, extractor=winrar)
            self.assertTrue((stage / 'PS3_GAME' / 'PARAM.SFO').is_file())

    def test_launches_start_cmd_with_unmodified_scripts_and_companions(self):
        scripts = {'Start.cmd': b'@echo off\r\n', 'Launch.ps1': b'Write-Host launcher\r\n'}
        hashes = {name: hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest()
                  for name, data in scripts.items()}
        with tempfile.TemporaryDirectory() as scratch:
            package = Path(scratch) / 'Launcher v3.zip'
            with ZipFile(package, 'w') as archive:
                for name, data in scripts.items():
                    archive.writestr(f'{LAUNCHER_FOLDER}/{name}', data)
                for name in TOOL_FILES:
                    archive.writestr(f'{LAUNCHER_FOLDER}/Retail2Pkg/{name}', name.encode())
                archive.writestr('../outside.cmd', b'not part of the launcher')

            def run(command, *, cwd, **kwargs):
                self.assertEqual(command[-3:], ['/d', '/c', r'.\Start.cmd'])
                for name, data in scripts.items():
                    self.assertEqual((cwd / name).read_bytes(), data)
                self.assertEqual((cwd / 'Retail2Pkg' / 'Retail2Pkg.bat').read_bytes(), b'Retail2Pkg.bat')
                self.assertFalse((cwd / 'outside.cmd').exists())
                return SimpleNamespace(returncode=0)

            with patch('zarchive.retail2pkg_v31.SCRIPT_HASHES', hashes):
                run_launcher(package, runner=run)
            with self.assertRaisesRegex(ValueError, 'differs from the supported'):
                run_launcher(package, runner=self.fail)
