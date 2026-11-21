from pathlib import Path
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from zarchive.ps4_fpkg import build_packages, inspect_dump, run_orbis, scan_dumps, write_gp4


BASE_ID = 'UP0001-CUSA12345_00-GAMECONTENTID000'
DLC_ID = 'UP0001-CUSA12345_00-ADDONCONTENT0000'


def make_dump(folder, category, content=BASE_ID, **changes):
    fields = {'TITLE_ID': 'CUSA12345', 'TITLE': 'Test: Game', 'CATEGORY': category,
              'CONTENT_ID': content, 'APP_VER': '01.02', 'VERSION': '01.00'}
    fields.update(changes)
    keys, values, table = bytearray(), bytearray(), bytearray()
    for name, value in fields.items():
        raw = value.encode() + b'\0'
        table.extend(struct.pack('<HHIII', len(keys), 0x204, len(raw), len(raw), len(values)))
        keys.extend(name.encode() + b'\0')
        values.extend(raw)
    system = folder / 'sce_sys'
    system.mkdir(parents=True)
    offset = 20 + len(table)
    (system / 'param.sfo').write_bytes(
        struct.pack('<4sIIII', b'\0PSF', 0x101, offset, offset + len(keys), len(fields))
        + table + keys + values
    )
    return folder


class FpkgTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.dumps = self.root / 'dumps'
        self.base = make_dump(self.dumps / 'nested' / 'CUSA12345-app', 'gd')
        self.update = make_dump(self.dumps / 'nested' / 'CUSA12345-patch', 'gp', APP_VER='02.00')
        self.dlc = make_dump(self.dumps / 'nested' / 'CUSA12345-ac', 'ac', DLC_ID, TITLE_ID='', TITLE='Extra')
        self.output = self.root / 'output'
        self.output.mkdir()
        self.tool = self.root / 'orbis-pub-cmd.exe'
        self.tool.write_bytes(b'MZmock')

    def test_scan_reports_bad_metadata_and_groups_nested_dumps(self):
        make_dump(self.dumps / 'invalid', 'gd', CONTENT_ID='')
        dumps, errors = scan_dumps(self.dumps)
        self.assertEqual({dump.category for dump in dumps}, {'gd', 'gp', 'ac'})
        self.assertEqual({dump.title_id for dump in dumps}, {'CUSA12345'})
        self.assertIn('CONTENT_ID', errors[0])

    def test_gp4_payload_paths_and_optional_keystone(self):
        (self.base / 'sce_sys' / 'keystone').touch()
        (self.base / 'sce_sys' / 'playgo-chunk.dat').touch()
        (self.base / 'foo').mkdir()
        (self.base / 'foo' / 'a&b.bin').touch()
        for include in (True, False):
            gp4 = self.root / f'{include}.gp4'
            write_gp4(inspect_dump(self.base), gp4, preserve_keystone=include, storage_type='bd50')
            root = ET.parse(gp4).getroot()
            self.assertEqual(root.attrib, {'fmt': 'gp4', 'version': '1000'})
            self.assertEqual(root.find('volume/package').get('storage_type'), 'bd50')
            files = {file.get('targ_path') for file in root.findall('files/file')}
            self.assertIn('foo/a&b.bin', files)
            self.assertNotIn('sce_sys/playgo-chunk.dat', files)
            self.assertEqual('sce_sys/keystone' in files, include)
            self.assertIsNotNone(root.find("rootdir/dir[@targ_name='foo']"))

    def test_dlc_payload_changes_volume_type(self):
        for expected in ('pkg_ps4_ac_nodata', 'pkg_ps4_ac_data'):
            destination = self.root / (expected + '.gp4')
            write_gp4(inspect_dump(self.dlc), destination)
            self.assertEqual(ET.parse(destination).findtext('volume/volume_type'), expected)
            (self.dlc / 'payload.bin').touch()

    def test_queue_marries_patch_to_published_base_and_cleans_projects(self):
        projects, types = [], []

        def builder(tool, project, output, log, progress, cancelled):
            projects.append(project)
            root = ET.parse(project)
            volume_type = root.findtext('volume/volume_type')
            types.append(volume_type)
            if volume_type == 'pkg_ps4_patch':
                base = Path(root.find('volume/package').get('app_path'))
                self.assertTrue(base.is_file())
                self.assertIn('[Base v01.02]', base.name)
            output.write_bytes(b'\x7fCNT' + b'x' * 100)

        dumps, _ = scan_dumps(self.dumps)
        files = build_packages(dumps[::-1], self.tool, self.output, runner=builder)
        self.assertEqual(types, ['pkg_ps4_app', 'pkg_ps4_patch', 'pkg_ps4_ac_nodata'])
        self.assertEqual(len(files), 3)
        self.assertTrue(all(file.is_file() for file in files))
        self.assertTrue(all(not project.exists() for project in projects))
        self.assertEqual(files[0].parent.name, 'Test_ Game [CUSA12345]')

    def test_cancelled_build_does_not_publish_partial_package(self):
        cancelled = Event()

        def builder(tool, project, output, log, progress, should_cancel):
            output.write_bytes(b'\x7fCNT' + b'x' * 100)
            cancelled.set()

        with self.assertRaises(InterruptedError):
            build_packages([inspect_dump(self.base)], self.tool, self.output,
                           runner=builder, cancelled=cancelled.is_set)
        self.assertFalse(list(self.output.rglob('*.pkg')))
        self.assertFalse(list(self.output.rglob('*.gp4')))

    def test_orbis_streams_progress_and_reports_exit_code(self):
        start = subprocess.Popen

        def child(command, **kwargs):
            self.assertEqual(command[1], 'img_create')
            return start([sys.executable, '-u', '-c',
                          "import sys; print('Building 42%'); print('tool error', file=sys.stderr); sys.exit(7)"],
                         **kwargs)

        log, progress = [], []
        with patch('zarchive.ps4_fpkg.subprocess.Popen', side_effect=child):
            with self.assertRaisesRegex(RuntimeError, 'code 7'):
                run_orbis(self.tool, self.root / 'in.gp4', self.root / 'out.pkg',
                          log.append, progress.append, lambda: False)
        self.assertEqual(progress, [42])
        self.assertIn('tool error', log)
