"""Local PS4 dump inspection, GP4 generation, and supervised package builds."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
from queue import Empty, Full, Queue
import re
import shutil
import struct
import subprocess
from tempfile import TemporaryDirectory
from threading import Event, Thread
import xml.etree.ElementTree as ET

from .storage import parse_param_sfo, read_param_sfo

CATEGORIES = {'gd': 'Base', 'gp': 'Patch', 'ac': 'DLC'}
VOLUME_CATEGORIES = {'pkg_ps4_app': 'gd', 'pkg_ps4_patch': 'gp',
                     'pkg_ps4_ac_data': 'ac', 'pkg_ps4_ac_nodata': 'ac'}
SFO_ENTRY_ID = 0x1000
MAX_SFO_BYTES = 1024 * 1024
CONTENT_ID = re.compile(r'[A-Z]{2}[0-9]{4}-(CUSA[0-9]{5})_[0-9]{2}-[A-Z0-9_]{16}')
VERSION = re.compile(r'[0-9]{1,3}(?:\.[0-9]{1,3}){1,3}')
PASSCODE = '0' * 32
ABOUT_DIRECTORY = 'sce_sys/about'
FAT32_FILE_LIMIT = (1 << 32) - 1
EXCLUDED = {'sce_sys/playgo-chunk.dat', 'sce_sys/playgo-chunk.sha',
            'sce_sys/playgo-manifest.xml', '.complete', '.dumping', 'dump.log'}


@dataclass(frozen=True)
class Dump:
    path: Path
    title_id: str
    content_id: str
    title: str
    category: str
    app_ver: str
    version: str

    @property
    def build_version(self):
        return self.app_ver or self.version


def _check_cancelled(cancelled):
    if cancelled():
        raise InterruptedError('Build cancelled.')


def long_path(path) -> Path:
    value = os.path.abspath(path)
    if os.name == 'nt' and len(value) >= 240 and not value.startswith('\\\\?\\'):
        value = ('\\\\?\\UNC\\' + value[2:]) if value.startswith('\\\\') else '\\\\?\\' + value
    return Path(value)


def _linked(path):
    return path.is_symlink() or getattr(path, 'is_junction', lambda: False)()


def safe_title(value):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f\ufffd]', '_', value)
    name = ' '.join(name.split()).strip(' .')[:96].rstrip(' .')
    if re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', name, re.I):
        name = '_' + name
    return name or 'Untitled PS4 game'


def inspect_dump(folder):
    folder = long_path(folder)
    system = folder / 'sce_sys'
    sfo = system / 'param.sfo'
    if any(_linked(path) for path in (folder, system, sfo)):
        raise ValueError('A linked dump or param.sfo is unsupported.')
    if sfo.stat().st_size > MAX_SFO_BYTES:
        raise ValueError('param.sfo exceeds 1 MiB.')
    fields = read_param_sfo(sfo)
    category = fields.get('CATEGORY', '').lower()
    if category not in CATEGORIES:
        raise ValueError(f"Unsupported or missing CATEGORY: {category or '(empty)'}")
    title_id = fields.get('TITLE_ID', '').upper()
    content_id = fields.get('CONTENT_ID', '').upper()
    content = CONTENT_ID.fullmatch(content_id)
    if not content:
        raise ValueError('Missing or invalid CONTENT_ID.')
    if not title_id and category == 'ac':
        title_id = content[1]
    if title_id != content[1]:
        raise ValueError('TITLE_ID is missing or differs from CONTENT_ID.')
    title = fields.get('TITLE', '').strip()
    if not title:
        raise ValueError('Missing TITLE.')
    app_ver, version = (fields.get(key, '').strip() for key in ('APP_VER', 'VERSION'))
    if any(value and not VERSION.fullmatch(value) for value in (app_ver, version)):
        raise ValueError('Invalid APP_VER or VERSION.')
    if not (app_ver or version) and category != 'ac':
        raise ValueError('Missing APP_VER and VERSION.')
    return Dump(folder, title_id, content_id, title, category, app_ver, version)


def scan_dumps(source, cancelled=lambda: False):
    root = long_path(source)
    if not root.is_dir() or _linked(root):
        raise ValueError('Choose an existing dumps directory.')
    dumps, errors = [], []
    for directory, folders, _ in os.walk(root, onerror=lambda exc: errors.append(str(exc))):
        _check_cancelled(cancelled)
        path = Path(directory)
        if (path / 'sce_sys' / 'param.sfo').is_file():
            try:
                dumps.append(inspect_dump(path))
            except (OSError, ValueError) as exc:
                errors.append(f'{path}: {exc}')
            # Content under a dump root is payload, not another dump.
            folders.clear()
        else:
            folders[:] = sorted(name for name in folders if not _linked(path / name))
    return sorted(dumps, key=lambda dump: (dump.title_id, dump.category, dump.title, str(dump.path))), errors


def validate_tool(executable, *, require_helpers=False):
    path = long_path(executable)
    if path.name.casefold() != 'orbis-pub-cmd.exe' or not path.is_file():
        raise ValueError('Select an existing orbis-pub-cmd.exe.')
    with path.open('rb') as stream:
        if stream.read(2) != b'MZ':
            raise ValueError('The selected tool is not a Windows executable.')
    if require_helpers:
        helper = path.parent / 'ext' / 'sc.exe'
        try:
            with helper.open('rb') as stream:
                valid_helper = stream.read(2) == b'MZ'
        except OSError:
            valid_helper = False
        if not valid_helper:
            raise ValueError(f'Missing or unreadable publishing helper: {helper}. '
                             'Extract the complete matching publishing tools bundle and reselect orbis-pub-cmd.exe.')
    return path


def validate_package(path, *, expected_content_id=None, expected_category=None, expected_version=None):
    """Check package bounds and read its identity from the header and embedded SFO."""
    path = long_path(path)
    if _linked(path) or not path.is_file():
        raise ValueError(f'Choose an existing, unlinked PS4 package: {path}')
    with path.open('rb') as stream:
        file_size = os.fstat(stream.fileno()).st_size
        header = stream.read(0x490)
        if len(header) != 0x490 or header[:4] != b'\x7fCNT':
            raise ValueError(f'Invalid or truncated PS4 PKG header: {path.name}')
        entry_count, _, table_offset = struct.unpack_from('>III', header, 0x10)
        body_offset, body_size = struct.unpack_from('>QQ', header, 0x20)
        image_offset, image_size = struct.unpack_from('>QQ', header, 0x410)
        declared_size = struct.unpack_from('>Q', header, 0x430)[0]
        body_end = body_offset + body_size
        if (not 0 < entry_count <= 0xFFFF or not len(header) <= body_offset <= table_offset
                or table_offset + entry_count * 32 > body_end or body_end > file_size
                or (image_size and (image_offset < body_end or image_offset + image_size > file_size))
                or (declared_size and not max(body_end, image_offset + image_size) <= declared_size <= file_size)):
            raise ValueError(f'PS4 PKG table, body, or image extends outside the package: {path.name}')
        raw_content_id = header[0x40:0x70].split(b'\0', 1)[0]
        content_id = raw_content_id.decode('ascii', errors='replace')
        if not CONTENT_ID.fullmatch(content_id):
            raise ValueError(f'Invalid PS4 PKG content ID: {path.name}')
        stream.seek(table_offset)
        sfo_entry = None
        for _ in range(entry_count):
            entry_id, offset, size = struct.unpack_from('>I12xII', stream.read(32))
            if size and (offset < body_offset or offset + size > body_end):
                raise ValueError(f'PS4 PKG entry extends outside the package body: {path.name}')
            if entry_id == SFO_ENTRY_ID:
                if sfo_entry is not None or not 0 < size <= MAX_SFO_BYTES:
                    raise ValueError(f'Invalid PS4 PKG PARAM.SFO entry: {path.name}')
                sfo_entry = offset, size
        if sfo_entry is None:
            raise ValueError(f'PS4 PKG is missing PARAM.SFO: {path.name}')
        stream.seek(sfo_entry[0])
        fields = parse_param_sfo(stream.read(sfo_entry[1]))
    if fields.get('CONTENT_ID') != content_id or (expected_content_id and content_id != expected_content_id):
        raise ValueError(f'PS4 PKG content ID does not match: {path.name} ({content_id})')
    if expected_category and fields.get('CATEGORY', '').lower() != expected_category:
        raise ValueError(f'Expected a {CATEGORIES[expected_category].lower()} PS4 package: {path.name}')
    if expected_version:
        version = fields.get('APP_VER', '').strip() or fields.get('VERSION', '').strip()
        if not VERSION.fullmatch(version) or tuple(map(int, version.split('.'))) != tuple(map(int, expected_version.split('.'))):
            raise ValueError(f'PS4 PKG version does not match: {path.name} (expected {expected_version}, found {version or "none"})')
    return content_id


def preflight_dump(dump, preserve_keystone, log):
    if inspect_dump(dump.path) != dump:
        raise ValueError(f'Dump metadata changed. Scan again: {dump.path}')
    if (dump.path / '.dumping').exists():
        raise ValueError(f'Dump is still in progress or did not finish: {dump.path}')
    if dump.category != 'gd':
        return
    eboot = dump.path / 'eboot.bin'
    if _linked(eboot) or not eboot.is_file() or not eboot.stat().st_size:
        raise ValueError(f'Base dump is missing a usable eboot.bin: {dump.path}')
    keystone = dump.path / 'sce_sys' / 'keystone'
    if preserve_keystone and (not keystone.is_file() or not keystone.stat().st_size):
        log(f'Warning: {dump.title_id} base dump has no usable sce_sys/keystone. Existing saves may not load.')


def read_existing_gp4(path):
    path = long_path(path)
    if (_linked(path) or not path.is_file() or path.suffix.casefold() != '.gp4'
            or path.stat().st_size > 32 * 1024 * 1024):
        raise ValueError('Choose an existing build GP4 project up to 32 MiB.')
    try:
        project = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise ValueError(f'Invalid GP4 project: {exc}') from exc
    package = project.find('volume/package')
    if project.tag != 'psproject' or project.get('fmt') != 'gp4' or package is None:
        raise ValueError('Choose a PS4 build GP4 project.')
    category = VOLUME_CATEGORIES.get(project.findtext('volume/volume_type'))
    content_id = package.get('content_id', '')
    if category is None or not CONTENT_ID.fullmatch(content_id):
        raise ValueError('The GP4 does not identify a supported PS4 package.')
    return project, content_id, category


def scan_build_inputs(source, cancelled=lambda: False):
    dumps, errors = scan_dumps(source, cancelled)
    root = long_path(source)
    siblings = Counter((dump.path.parent, dump.content_id, dump.category) for dump in dumps)
    projects = {}
    notices = []
    matches = {}

    def nearby_projects(folder, content_id, category):
        if folder not in projects:
            projects[folder] = {}
            try:
                files = sorted(folder.iterdir())
            except OSError as error:
                notices.append(f'Could not look for GP4 files in {folder}: {error}')
                files = []
            for path in files:
                _check_cancelled(cancelled)
                if path.suffix.casefold() != '.gp4' or not path.is_file() or 'gp4fv' in path.stem.casefold():
                    continue
                try:
                    _, project_id, project_category = read_existing_gp4(path)
                except (OSError, ValueError) as error:
                    notices.append(f'Ignoring {path}: {error}')
                    continue
                projects[folder].setdefault((project_id, project_category), []).append(path)
        return projects[folder].get((content_id, category), [])

    for dump in dumps:
        _check_cancelled(cancelled)
        parent = dump.path.parent
        candidates = nearby_projects(dump.path, dump.content_id, dump.category)
        if not candidates and (parent == root or root in parent.parents):
            candidates = nearby_projects(parent, dump.content_id, dump.category)
            if candidates and siblings[parent, dump.content_id, dump.category] > 1:
                notices.append(f'{dump.path}: shared GP4 could match multiple dumps. A GP4 will be generated.')
                continue
        if len(candidates) == 1:
            matches[dump.path] = candidates[0]
        elif candidates:
            notices.append(f'{dump.path}: multiple matching GP4 files. A GP4 will be generated unless you choose an override.')
    return dumps, errors, matches, notices


def write_existing_gp4(project, dump, destination, *, preserve_keystone, base_package, cancelled):
    files, directories = _payload(dump, preserve_keystone, cancelled)
    available = {target.casefold(): (target, path) for target, path in files}
    listing = project.find('files')
    if listing is None or len(project.findall('files')) != 1 or project.find('rootdir') is None:
        raise ValueError('Expected one file list and a root directory in the build GP4.')
    included = set()
    for entry in list(listing):
        _check_cancelled(cancelled)
        target = entry.get('targ_path', '').replace('\\', '/').casefold()
        if entry.tag != 'file' or target in included:
            raise ValueError(f'Invalid or duplicate GP4 file entry: {target}')
        if (target == ABOUT_DIRECTORY or target.startswith(ABOUT_DIRECTORY + '/')
                or (target == 'sce_sys/keystone' and not preserve_keystone)):
            listing.remove(entry)
            continue
        if target not in available:
            raise ValueError(f'GP4 file is missing from this build dump: {target}. Use auto-generated GP4 for verification dumps.')
        included.add(target)
        entry.set('targ_path', available[target][0])
        entry.set('orig_path', str(long_path(available[target][1])))
    required = {'sce_sys/param.sfo'}
    if dump.category == 'gd':
        required.add('eboot.bin')
    if not required <= included:
        raise ValueError(f'GP4 is missing required files: {", ".join(sorted(required - included))}')
    if preserve_keystone and 'sce_sys/keystone' in available and 'sce_sys/keystone' not in included:
        target, source = available['sce_sys/keystone']
        ET.SubElement(listing, 'file', targ_path=target, orig_path=str(long_path(source)))
    package = project.find('volume/package')
    package.set('passcode', PASSCODE)
    if dump.category == 'gp':
        package.set('app_path', str(long_path(base_package)))
    else:
        package.attrib.pop('app_path', None)
    # Recreate the directory tree from the selected dump, ignoring paths in the imported tree.
    project.remove(project.find('rootdir'))
    write_project(project, directories, destination)


def _payload(dump, preserve_keystone, cancelled):
    files, directories = [], set()

    def fail(error):
        raise error

    for directory, folders, names in os.walk(dump.path, onerror=fail):
        _check_cancelled(cancelled)
        path = Path(directory)
        # The publishing tools create this directory during image generation.
        folders[:] = [
            name for name in folders
            if (path / name).relative_to(dump.path).as_posix().casefold() != ABOUT_DIRECTORY
        ]
        for name in sorted(folders + names):
            entry = path / name
            if _linked(entry):
                raise ValueError(f'Linked dump entry: {entry}')
            relative = entry.relative_to(dump.path)
            target = relative.as_posix()
            lower = target.casefold()
            if entry.is_dir():
                directories.add(relative.parts)
                continue
            if (lower == ABOUT_DIRECTORY or lower in EXCLUDED
                    or (len(relative.parts) == 1 and lower.endswith('.gp4'))):
                continue
            if lower == 'sce_sys/keystone' and not preserve_keystone:
                continue
            if not entry.is_file():
                raise ValueError(f'Unsupported dump entry: {entry}')
            files.append((target, entry))
    return sorted(files), sorted(directories)


def write_gp4(dump, destination, *, preserve_keystone=True, storage_type='digital50',
              base_package=None, cancelled=lambda: False):
    if storage_type not in {'digital50', 'bd50'}:
        raise ValueError('Unsupported storage type.')
    if dump.category == 'gp' and not base_package:
        raise ValueError('A patch GP4 requires its built base package.')
    files, directories = _payload(dump, preserve_keystone, cancelled)
    if not files:
        raise ValueError(f'No files to package in {dump.path}')
    volume_type = {'gd': 'pkg_ps4_app', 'gp': 'pkg_ps4_patch'}.get(dump.category)
    if dump.category == 'ac':
        has_data = any(not target.casefold().startswith('sce_sys/') for target, _ in files)
        volume_type = 'pkg_ps4_ac_data' if has_data else 'pkg_ps4_ac_nodata'

    project = ET.Element('psproject', fmt='gp4', version='1000')
    volume = ET.SubElement(project, 'volume')
    ET.SubElement(volume, 'volume_type').text = volume_type
    ET.SubElement(volume, 'volume_id').text = 'PS4VOLUME'
    ET.SubElement(volume, 'volume_ts').text = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    attributes = {'content_id': dump.content_id, 'passcode': PASSCODE}
    if dump.category in ('gd', 'gp'):
        attributes.update(storage_type=storage_type, app_type='full', c_date=datetime.now().date().isoformat())
    else:
        attributes['entitlement_key'] = PASSCODE
    if dump.category == 'gp':
        attributes['app_path'] = str(long_path(base_package))
    ET.SubElement(volume, 'package', attributes)
    if dump.category in ('gd', 'gp'):
        info = ET.SubElement(volume, 'chunk_info', chunk_count='1', scenario_count='1')
        ET.SubElement(ET.SubElement(info, 'chunks'), 'chunk', id='0', label='Chunk #0', layer_no='0')
        scenarios = ET.SubElement(info, 'scenarios', default_id='0')
        ET.SubElement(scenarios, 'scenario', id='0', type='sp', initial_chunk_count='1',
                      label='Scenario #0').text = '0'
    listing = ET.SubElement(project, 'files', img_no='0')
    paths = set()
    for target, source in files:
        if target.casefold() in paths or any(ord(char) < 32 for char in target):
            raise ValueError(f'Duplicate or invalid GP4 target path: {target}')
        paths.add(target.casefold())
        ET.SubElement(listing, 'file', targ_path=target, orig_path=str(long_path(source)))
    write_project(project, directories, destination)


def write_project(project, directories, destination):
    nodes = {(): ET.SubElement(project, 'rootdir')}
    for parts in directories:
        nodes[parts] = ET.SubElement(nodes[parts[:-1]], 'dir', targ_name=parts[-1])
    with long_path(destination).open('xb') as stream:
        ET.ElementTree(project).write(stream, encoding='utf-8', xml_declaration=True)


def build_plan(dumps, *, existing_base_id=None):
    groups = {}
    for dump in dumps:
        groups.setdefault(dump.title_id, []).append(dump)
    result = []
    for title_id, items in sorted(groups.items()):
        bases = [dump for dump in items if dump.category == 'gd']
        patches = [dump for dump in items if dump.category == 'gp']
        if len(bases) > 1:
            raise ValueError(f'{title_id}: select only one base game.')
        if patches:
            base_id = bases[0].content_id if bases else existing_base_id
            if base_id is None:
                raise ValueError(f'{title_id}: select its base dump or an existing base package before building a patch.')
            if any(patch.content_id != base_id for patch in patches):
                raise ValueError(f'{title_id}: the selected patch and base game have different CONTENT_ID values.')
        title = (bases[0] if bases else patches[0] if patches else items[0]).title
        order = sorted(items, key=lambda dump: (list(CATEGORIES).index(dump.category),
                                                tuple(map(int, dump.build_version.split('.'))) if dump.build_version else (),
                                                dump.content_id))
        for dump in order:
            label = f'{CATEGORIES[dump.category]} v{dump.build_version}' if dump.category != 'ac' else f'DLC {dump.content_id[-16:]}'
            parent = f'{safe_title(title)} [{title_id}]'
            filename = f'{safe_title(dump.title)} [{title_id}] [{label}].pkg'
            result.append((dump, Path(parent, filename)))
    keys = [str(path).casefold() for _, path in result]
    if len(keys) != len(set(keys)):
        raise ValueError('Selected dumps would produce duplicate package names.')
    return result


def run_orbis(tool, project, package, log, progress, cancelled):
    command = [str(tool), 'img_create', str(project), str(package)]
    with subprocess.Popen(command, cwd=tool.parent, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)) as process:
        messages = Queue(maxsize=256)
        stop_reader = Event()

        def enqueue(value):
            while not stop_reader.is_set():
                try:
                    messages.put(value, timeout=0.2)
                    return True
                except Full:
                    continue
            return False

        def read_output():
            try:
                # Universal newline translation also handles CR-only progress updates.
                from io import TextIOWrapper
                with TextIOWrapper(process.stdout, encoding='utf-8', errors='replace') as stream:
                    for line in stream:
                        if not enqueue(line):
                            break
            except (OSError, ValueError) as exc:
                enqueue(exc)
            finally:
                enqueue(None)

        reader = Thread(target=read_output, daemon=True)
        reader.start()
        try:
            while True:
                _check_cancelled(cancelled)
                try:
                    line = messages.get(timeout=0.2)
                except Empty:
                    continue
                if line is None:
                    break
                if isinstance(line, Exception):
                    raise RuntimeError(f'Cannot read build output: {line}') from line
                line = line.rstrip()
                if line:
                    log(line)
                    values = re.findall(r'(?<!\d)(\d{1,3})\s*%', line)
                    if values and 0 <= int(values[-1]) <= 100:
                        progress(int(values[-1]))
            while process.poll() is None:
                _check_cancelled(cancelled)
                try:
                    process.wait(timeout=0.2)
                except subprocess.TimeoutExpired:
                    pass
            if process.returncode:
                code = process.returncode
                extra = ' Check whether this tool supports extended Windows paths.' if max(len(str(project)), len(str(package))) >= 240 else ''
                raise RuntimeError(f'orbis-pub-cmd.exe exited with code {code} (0x{code & 0xffffffff:08X}).{extra}')
        except BaseException:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            raise
        finally:
            stop_reader.set()
            reader.join(timeout=1)


def prepare_batch(dumps, executable, output, *, preserve_keystone, existing_base, resume, filesystem,
                  require_helpers, log, cancelled):
    _check_cancelled(cancelled)
    tool = validate_tool(executable, require_helpers=require_helpers)
    root = long_path(output)
    if not root.is_dir() or _linked(root):
        raise ValueError('Choose an existing output directory.')
    dumps = list(dumps)
    base_packages = {}
    existing_base_id = None
    if existing_base:
        existing_base_id = validate_package(existing_base, expected_category='gd')
        if not any(dump.category == 'gp' and dump.content_id == existing_base_id for dump in dumps):
            raise ValueError('Select a patch matching the existing base package.')
        if any(dump.category == 'gd' and dump.content_id == existing_base_id for dump in dumps):
            raise ValueError('Uncheck the matching base dump to reuse its existing package.')
        base_packages[CONTENT_ID.fullmatch(existing_base_id)[1]] = long_path(existing_base)
    plan = build_plan(dumps, existing_base_id=existing_base_id)
    if not plan:
        raise ValueError('Select at least one dump to build.')

    jobs, warnings = [], []
    reusable_bases = set(base_packages)
    required = 0
    fat32 = filesystem.strip().casefold() in {'fat32', 'vfat', 'msdos'}
    for dump, relative in plan:
        _check_cancelled(cancelled)
        final = long_path(root / relative)
        if any(final == source.path or source.path in final.parents for source in dumps):
            raise ValueError(f'Output is inside a selected dump: {final}')
        if _linked(final) or _linked(final.parent):
            raise ValueError(f'Output path is linked: {final}')
        reuse = final.exists()
        if reuse:
            if not resume:
                raise ValueError(f'Output already exists: {final}. Use Resume batch to verify and reuse it.')
            try:
                validate_package(final, expected_content_id=dump.content_id,
                                 expected_category=dump.category, expected_version=dump.build_version)
            except (OSError, ValueError) as error:
                raise ValueError(f'Cannot resume with {final.name}: {error}. '
                                 'Move the existing file aside or use another output folder.') from error
            if dump.category == 'gd':
                reusable_bases.add(dump.title_id)
            if dump.category == 'gp' and dump.title_id not in reusable_bases:
                raise ValueError(f'Cannot reuse {final.name} while its base needs to be rebuilt. '
                                 'Move the patch aside so both packages can be built together.')
        else:
            preflight_dump(dump, preserve_keystone, log)
            files, directories = _payload(dump, preserve_keystone, cancelled)
            # Budget from the uncompressed dump, allowing for PFS alignment and package metadata.
            block = 64 * 1024
            estimate = (8 * 1024 * 1024) + len(directories) * block
            for _, source in files:
                _check_cancelled(cancelled)
                size = source.stat().st_size
                estimate += ((size + block - 1) // block) * block
            required += estimate
            if fat32 and estimate > FAT32_FILE_LIMIT:
                warnings.append(f'{final.name} may exceed FAT32’s maximum file size of 4 GiB minus 1 byte. '
                                'Choose an exFAT or NTFS output drive.')
        jobs.append((dump, final, reuse))

    free = shutil.disk_usage(root).free
    if required > free:
        warnings.append(f'Estimated output needs {required / (1 << 30):.2f} GiB. '
                        f'The output drive has {free / (1 << 30):.2f} GiB free.')
    return tool, base_packages, jobs, required, free, warnings


def check_batch(dumps, executable, output, *, preserve_keystone=True, existing_base=None,
                resume=False, filesystem='', log=lambda _: None, cancelled=lambda: False):
    _, _, jobs, required, free, warnings = prepare_batch(
        dumps, executable, output, preserve_keystone=preserve_keystone, existing_base=existing_base,
        resume=resume, filesystem=filesystem, require_helpers=True, log=log, cancelled=cancelled,
    )
    reused = sum(reuse for _, _, reuse in jobs)
    return len(jobs) - reused, reused, required, free, warnings


def build_packages(dumps, executable, output, *, preserve_keystone=True, storage_type='digital50',
                   existing_base=None, existing_gp4=None, nearby_gp4s=None, row_gp4s=None,
                   resume=False, filesystem='', allow_size_warnings=False,
                   log=lambda _: None, progress=lambda _: None, cancelled=lambda: False, runner=None):
    if os.name != 'nt' and runner is None:
        raise OSError('Building FPKGs requires Windows.')
    dumps = list(dumps)
    tool, base_packages, jobs, _, _, warnings = prepare_batch(
        dumps, executable, output, preserve_keystone=preserve_keystone, existing_base=existing_base,
        resume=resume, filesystem=filesystem, require_helpers=runner is None, log=log, cancelled=cancelled,
    )
    if warnings and not allow_size_warnings:
        raise ValueError('\n'.join(warnings))
    for warning in warnings:
        log(f'Warning: {warning}')
    row_gp4s = row_gp4s or {}
    for dump, _, reuse in jobs:
        chosen = row_gp4s.get(dump.path)
        if chosen and not reuse:
            _, content_id, category = read_existing_gp4(chosen)
            if (content_id, category) != (dump.content_id, dump.category):
                raise ValueError(f'{chosen} does not match the content ID or package type for {dump.path.name}.')
    nearby_gp4s = nearby_gp4s or {}
    imported_dump = None
    if existing_gp4:
        override_project, content_id, category = read_existing_gp4(existing_gp4)
        matches = [dump for dump in dumps if (dump.content_id, dump.category) == (content_id, category)]
        if len(matches) != 1:
            raise ValueError('Select exactly one dump matching the existing GP4 content ID and package type.')
        imported_dump = matches[0]
    invoke = runner or run_orbis
    ready = []
    for index, (dump, final, reuse) in enumerate(jobs, 1):
        _check_cancelled(cancelled)
        if reuse:
            log(f'[{index}/{len(jobs)}] Reusing verified {final.name}')
            if dump.category == 'gd':
                base_packages[dump.title_id] = final
            ready.append(final)
            progress(100)
            continue
        final.parent.mkdir(exist_ok=True)
        log(f'[{index}/{len(jobs)}] Building {final.name}')
        progress(0)
        with TemporaryDirectory(prefix='.fpkg-', dir=final.parent) as scratch:
            project_path = long_path(Path(scratch) / 'project.gp4')
            package = long_path(Path(scratch) / 'package.pkg')
            project_options = dict(preserve_keystone=preserve_keystone, cancelled=cancelled,
                                   base_package=base_packages.get(dump.title_id))
            matched_gp4 = nearby_gp4s.get(dump.path) if dump.path not in row_gp4s else None
            chosen_gp4 = row_gp4s.get(dump.path)
            if chosen_gp4:
                project, content_id, category = read_existing_gp4(chosen_gp4)
                if (content_id, category) != (dump.content_id, dump.category):
                    raise ValueError(f'The GP4 changed after selection: {chosen_gp4}')
                log(f'Using selected GP4: {chosen_gp4}')
                write_existing_gp4(project, dump, project_path, **project_options)
            elif dump == imported_dump and dump.path not in row_gp4s:
                log(f'Using existing GP4: {existing_gp4}')
                write_existing_gp4(override_project, dump, project_path, **project_options)
            elif matched_gp4:
                try:
                    project, content_id, category = read_existing_gp4(matched_gp4)
                    if (content_id, category) != (dump.content_id, dump.category):
                        raise ValueError('The project no longer matches the scanned dump.')
                    write_existing_gp4(project, dump, project_path, **project_options)
                except ValueError as error:
                    log(f'Could not use {matched_gp4}: {error} Generating a GP4.')
                except FileNotFoundError:
                    log(f'GP4 no longer exists: {matched_gp4}. Generating a GP4.')
                else:
                    log(f'Using existing GP4: {matched_gp4}')
            if not project_path.exists():
                write_gp4(dump, project_path, storage_type=storage_type, **project_options)
            invoke(tool, project_path, package, log, progress, cancelled)
            _check_cancelled(cancelled)
            validate_package(package, expected_content_id=dump.content_id, expected_category=dump.category,
                             expected_version=dump.build_version)
            # Windows rename fails if a concurrent build has already published this name.
            if os.name == 'nt':
                package.rename(final)
            else:
                os.link(package, final)
        if dump.category == 'gd':
            base_packages[dump.title_id] = final
        ready.append(final)
        progress(100)
        log(f'Saved {final}')
    return ready
