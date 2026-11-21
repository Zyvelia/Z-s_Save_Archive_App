import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile

from test_v20 import write_sfo
from zarchive.iso_converter_v20 import extract_iso, stage_conversion
from zarchive.app_assets import asset_path
from zarchive.retail2pkg_v31 import build_pkgs_locally, stream_batch_log


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

    def test_build_runs_the_bundled_batch_on_the_windows_iso_copy(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            iso = root / 'disc.iso'
            iso.touch()
            output = root / 'Local output & packages'
            output.mkdir()
            messages, percentages = [], []

            def copy(source, destination, *, progress, extraction_progress):
                self.assertEqual(source, iso)
                destination.mkdir()
                write_sfo(destination / 'PARAM.SFO')
                extraction_progress(0)
                extraction_progress(100)

            def batch(stage, timeout, progress, console_status):
                self.assertEqual(stage.parent, output)
                self.assertTrue((stage / 'PS3_GAME' / 'PARAM.SFO').is_file())
                with ZipFile(asset_path('Retail2Pkg_ISO_Launcher_v3.zip')) as archive:
                    self.assertEqual((stage / 'Retail2Pkg.bat').read_bytes(),
                                     archive.read('Retail2Pkg ISO Launcher/Retail2Pkg/Retail2Pkg.bat'))
                packages = stage / 'BLUS30982'
                packages.mkdir()
                for suffix in ('', '_-_Update'):
                    (packages / f'BLUS30982{suffix}.pkg').write_bytes(b'\x7fPKG' + b'x' * 100)
                return SimpleNamespace(returncode=0)

            with patch('zarchive.retail2pkg_v31.copy_iso_game', side_effect=copy):
                result = build_pkgs_locally(iso, output, runner=batch, progress=messages.append,
                                            extraction_progress=percentages.append)
            self.assertEqual(percentages, [0, 100])
            self.assertEqual(len(result['packages']), 2)
            self.assertEqual(Path(result['folder']).name, 'BLUS30982')
            self.assertTrue(all(Path(pkg).is_file() for pkg in result['packages']))

    def test_batch_streams_carriage_and_backspace_progress(self):
        with tempfile.TemporaryDirectory() as scratch:
            log = Path(scratch) / 'batch.log'
            messages, statuses = [], []
            child = (
                "import sys, time; "
                "sys.stdout.write('Patch.pkg ... 21%\\b\\b\\b'); "
                "sys.stdout.flush(); time.sleep(0.8); print('done', flush=True)"
            )
            with log.open('wb') as output, subprocess.Popen(
                [sys.executable, '-u', '-c', child], stdout=output
            ) as process:
                result = stream_batch_log(process, log, 10, progress=messages.append,
                                          console_status=statuses.append, encoding='utf-8')
            self.assertEqual(result.returncode, 0)
            self.assertIn('Patch.pkg ... 21%', statuses)
            self.assertEqual(messages, ['Patch.pkg ... done'])
