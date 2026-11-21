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
from zarchive.retail2pkg_v31 import REQUIRED_FILES, build_pkgs_locally, stream_batch_log


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

    def test_streams_partial_patch_progress_and_keeps_completed_lines(self):
        with tempfile.TemporaryDirectory() as scratch:
            log = Path(scratch) / 'batch.log'
            messages, statuses = [], []
            child = (
                "import sys, time; "
                "sys.stdout.write('Game identified: BLUS30061\\r\\nPatch.pkg ... 01%\\b\\b\\b'); "
                "sys.stdout.flush(); time.sleep(0.8); "
                "print('done', flush=True)"
            )
            with log.open('wb') as output, subprocess.Popen(
                [sys.executable, '-u', '-c', child], stdout=output
            ) as process:
                result = stream_batch_log(process, log, 10, progress=messages.append,
                                          console_status=statuses.append, encoding='utf-8')
            self.assertIn('Patch.pkg ... 01%', statuses)
            self.assertEqual(statuses[-1], '')
            self.assertEqual(messages, ['Game identified: BLUS30061', 'Patch.pkg ... done'])
            self.assertEqual(result.returncode, 0)

    def test_batch_runs_next_to_the_extracted_game_and_output_is_collected(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            iso = root / 'disc.iso'
            iso.write_bytes(b'\0' * 0x8001 + b'CD001')
            kit = root / 'Retail2Pkg.zip'
            with ZipFile(kit, 'w') as archive:
                for name in REQUIRED_FILES:
                    archive.writestr(f'Retail2Pkg/{name}', name.encode())
            extractor = root / '7z.exe'
            extractor.touch()
            output = root / 'output'
            output.mkdir()

            def extract(command, cancelled, progress, extraction_progress):
                self.assertIn('-bsp1', command)
                self.assertIn('-ir!PS3_GAME', command)
                extracted = Path(next(item[2:] for item in command if item.startswith('-o')))
                game = extracted / 'Disc Backup' / 'PS3_GAME'
                game.mkdir(parents=True)
                write_sfo(game / 'PARAM.SFO')

            def batch(command, cwd, **kwargs):
                self.assertEqual(command[-1], 'Retail2Pkg.bat')
                self.assertEqual((cwd / 'Retail2Pkg.bat').read_bytes(), b'Retail2Pkg.bat')
                self.assertTrue((cwd / 'PS3_GAME' / 'PARAM.SFO').is_file())
                (cwd / 'Disc.pkg').write_bytes(b'\x7fPKG' + b'x' * 100)
                (cwd / 'patch').mkdir()
                (cwd / 'patch' / 'Downloaded.pkg').write_bytes(b'\x7fPKG' + b'x' * 100)
                return SimpleNamespace(returncode=0, stdout='', stderr='')

            with patch('zarchive.iso_converter_v20.extract_iso', side_effect=extract):
                result = build_pkgs_locally(iso, kit, output, extractor=extractor, runner=batch)
            self.assertTrue(result['success'])
            self.assertEqual(result['packages'], [str(output / 'Disc.pkg')])
            self.assertFalse((output / 'Downloaded.pkg').exists())
