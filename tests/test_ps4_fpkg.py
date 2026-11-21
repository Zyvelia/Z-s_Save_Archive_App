from pathlib import Path
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from zarchive.ps4_fpkg import build_packages, inspect_dump, run_orbis, scan_dumps, validate_package, write_gp4


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


def make_package(package, dump, *, content_id=BASE_ID):
    sfo = (dump / 'sce_sys' / 'param.sfo').read_bytes()
    header_size = 0x2000
    sfo_offset = header_size + 32
    data = bytearray(sfo_offset + len(sfo))
    data[:4] = b'\x7fCNT'
    struct.pack_into('>I', data, 0x10, 1)
    struct.pack_into('>I4xQQ', data, 0x18, header_size, header_size, 32 + len(sfo))
    data[0x40:0x40 + len(content_id)] = content_id.encode()
    struct.pack_into('>I12xII', data, header_size, 0x1000, sfo_offset, len(sfo))
    data[sfo_offset:] = sfo
    package.write_bytes(data)


class FpkgTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.dumps = self.root / 'dumps'
        self.base = make_dump(self.dumps / 'nested' / 'CUSA12345-app', 'gd')
        (self.base / 'eboot.bin').write_bytes(b'executable')
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
            source, content_id = {
                'pkg_ps4_app': (self.base, BASE_ID),
                'pkg_ps4_patch': (self.update, BASE_ID),
                'pkg_ps4_ac_nodata': (self.dlc, DLC_ID),
            }[volume_type]
            make_package(output, source, content_id=content_id)

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

    def test_retry_patch_uses_existing_base_after_failure(self):
        base, update = map(inspect_dump, (self.base, self.update))

        def build_base_then_fail(tool, project, output, log, progress, cancelled):
            if ET.parse(project).findtext('volume/volume_type') == 'pkg_ps4_patch':
                raise RuntimeError('patch failed')
            make_package(output, self.base)

        with self.assertRaisesRegex(RuntimeError, 'patch failed'):
            build_packages([base, update], self.tool, self.output, runner=build_base_then_fail)
        existing_base, = self.output.rglob('*.pkg')

        def build_patch(tool, project, output, log, progress, cancelled):
            package = ET.parse(project).find('volume/package')
            self.assertEqual(Path(package.get('app_path')), existing_base)
            make_package(output, self.update)

        patch, = build_packages([update], self.tool, self.output, existing_base=existing_base, runner=build_patch)
        self.assertEqual(validate_package(patch, expected_category='gp'), BASE_ID)
        with self.assertRaisesRegex(ValueError, 'Expected a base'):
            build_packages([update], self.tool, self.output, existing_base=patch, runner=build_patch)

        other = make_dump(self.dumps / 'other', 'gd', 'UP0002-CUSA12345_00-GAMECONTENTID000')
        different_base = self.root / 'other.pkg'
        make_package(different_base, other, content_id='UP0002-CUSA12345_00-GAMECONTENTID000')
        with self.assertRaisesRegex(ValueError, 'Select a patch matching'):
            build_packages([update], self.tool, self.output, existing_base=different_base, runner=build_patch)

    def test_preflight_rejects_missing_eboot_and_warns_about_keystone(self):
        base = inspect_dump(self.base)
        (self.base / 'eboot.bin').unlink()

        def no_build(*args):
            self.fail('The external builder was invoked before preflight passed')

        with self.assertRaisesRegex(ValueError, 'eboot.bin'):
            build_packages([base], self.tool, self.output, runner=no_build)

        (self.base / 'eboot.bin').write_bytes(b'executable')
        messages = []

        def build(tool, project, output, log, progress, cancelled):
            self.assertTrue(any('Existing saves may not load' in message for message in messages))
            make_package(output, self.base)

        build_packages([base], self.tool, self.output, log=messages.append, runner=build)

    def test_rejects_truncated_and_wrong_identity_output(self):
        base = inspect_dump(self.base)

        def stub(tool, project, output, log, progress, cancelled):
            output.write_bytes(b'\x7fCNT' + bytes(60))

        with self.assertRaisesRegex(ValueError, 'truncated'):
            build_packages([base], self.tool, self.output, runner=stub)
        self.assertFalse(list(self.output.rglob('*.pkg')))

        def wrong_id(tool, project, output, log, progress, cancelled):
            make_package(output, self.base, content_id=DLC_ID)

        with self.assertRaisesRegex(ValueError, 'content ID does not match'):
            build_packages([base], self.tool, self.output, runner=wrong_id)
        self.assertFalse(list(self.output.rglob('*.pkg')))

    def test_existing_gp4_keeps_project_options_and_rebases_source_paths(self):
        base = inspect_dump(self.base)
        gp4 = self.root / 'existing.gp4'
        write_gp4(base, gp4, storage_type='bd50')
        imported = ET.parse(gp4)
        for entry in imported.findall('files/file'):
            entry.set('orig_path', 'X:/original-computer/' + entry.get('targ_path'))
        imported.write(gp4, encoding='utf-8', xml_declaration=True)
        original = gp4.read_bytes()
        (self.base / 'sce_sys' / 'keystone').write_bytes(b'keystone')

        def build(tool, project, output, log, progress, cancelled):
            built = ET.parse(project)
            self.assertEqual(built.find('volume/package').get('storage_type'), 'bd50')
            files = {entry.get('targ_path'): Path(entry.get('orig_path')) for entry in built.findall('files/file')}
            self.assertEqual(files['eboot.bin'], self.base / 'eboot.bin')
            self.assertEqual(files['sce_sys/keystone'], self.base / 'sce_sys' / 'keystone')
            make_package(output, self.base)

        build_packages([base], self.tool, self.output, existing_gp4=gp4, runner=build)
        self.assertEqual(gp4.read_bytes(), original)

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
