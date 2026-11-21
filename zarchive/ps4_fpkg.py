"""Local PS4 dump inspection, GP4 generation, and supervised package builds."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
from queue import Empty, Full, Queue
import re
import subprocess
from tempfile import TemporaryDirectory
from threading import Event, Thread
import xml.etree.ElementTree as ET

from .storage import read_param_sfo

CATEGORIES = {'gd': 'Base', 'gp': 'Patch', 'ac': 'DLC'}
CONTENT_ID = re.compile(r'[A-Z]{2}[0-9]{4}-(CUSA[0-9]{5})_[0-9]{2}-[A-Z0-9_]{16}')
VERSION = re.compile(r'[0-9]{1,3}(?:\.[0-9]{1,3}){1,3}')
PASSCODE = '0' * 32
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
    if sfo.stat().st_size > 1024 * 1024:
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


def validate_tool(executable):
    path = long_path(executable)
    if path.name.casefold() != 'orbis-pub-cmd.exe' or not path.is_file():
        raise ValueError('Select an existing orbis-pub-cmd.exe.')
    with path.open('rb') as stream:
        if stream.read(2) != b'MZ':
            raise ValueError('The selected tool is not a Windows executable.')
    return path


def _payload(dump, preserve_keystone, cancelled):
    files, directories = [], set()

    def fail(error):
        raise error

    for directory, folders, names in os.walk(dump.path, onerror=fail):
        _check_cancelled(cancelled)
        path = Path(directory)
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
            if lower in EXCLUDED or (len(relative.parts) == 1 and lower.endswith('.gp4')):
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
    nodes = {(): ET.SubElement(project, 'rootdir')}
    for parts in directories:
        nodes[parts] = ET.SubElement(nodes[parts[:-1]], 'dir', targ_name=parts[-1])
    with long_path(destination).open('xb') as stream:
        ET.ElementTree(project).write(stream, encoding='utf-8', xml_declaration=True)


def build_plan(dumps):
    groups = {}
    for dump in dumps:
        groups.setdefault(dump.title_id, []).append(dump)
    result = []
    for title_id, items in sorted(groups.items()):
        bases = [dump for dump in items if dump.category == 'gd']
        patches = [dump for dump in items if dump.category == 'gp']
        if len(bases) > 1:
            raise ValueError(f'{title_id}: select only one base game.')
        if patches and not bases:
            raise ValueError(f'{title_id}: select its base game before building a patch.')
        if any(patch.content_id != bases[0].content_id for patch in patches):
            raise ValueError(f'{title_id}: the selected patch and base game have different CONTENT_ID values.')
        title = (bases[0] if bases else items[0]).title
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


def build_packages(dumps, executable, output, *, preserve_keystone=True, storage_type='digital50',
                   log=lambda _: None, progress=lambda _: None, cancelled=lambda: False, runner=None):
    if os.name != 'nt' and runner is None:
        raise OSError('Building FPKGs requires Windows.')
    _check_cancelled(cancelled)
    tool = validate_tool(executable)
    root = long_path(output)
    if not root.is_dir() or _linked(root):
        raise ValueError('Choose an existing output directory.')
    plan = build_plan(dumps)
    if not plan:
        raise ValueError('Select at least one dump to build.')
    base_packages = {}
    for dump, relative in plan:
        _check_cancelled(cancelled)
        final = root / relative
        if (root == dump.path or dump.path in root.parents or final.exists() or _linked(final)
                or _linked(final.parent)):
            raise ValueError(f'Output is inside a dump, already exists, or is linked: {final}')
    invoke = runner or run_orbis
    created = []
    for index, (dump, relative) in enumerate(plan, 1):
        _check_cancelled(cancelled)
        final = long_path(root / relative)
        final.parent.mkdir(exist_ok=True)
        log(f'[{index}/{len(plan)}] Building {relative.name}')
        progress(0)
        with TemporaryDirectory(prefix='.fpkg-', dir=final.parent) as scratch:
            project = long_path(Path(scratch) / 'project.gp4')
            package = long_path(Path(scratch) / 'package.pkg')
            write_gp4(dump, project, preserve_keystone=preserve_keystone, storage_type=storage_type,
                      base_package=base_packages.get(dump.title_id), cancelled=cancelled)
            invoke(tool, project, package, log, progress, cancelled)
            _check_cancelled(cancelled)
            if not package.is_file() or _linked(package) or package.stat().st_size < 64:
                raise RuntimeError(f'The tool did not produce a complete package for {relative.name}.')
            with package.open('rb') as stream:
                if stream.read(4) != b'\x7fCNT':
                    raise RuntimeError(f'The tool output has an invalid PS4 PKG signature: {relative.name}')
            # Windows rename fails if a concurrent build has already published this name.
            if os.name == 'nt':
                package.rename(final)
            else:
                os.link(package, final)
        if dump.category == 'gd':
            base_packages[dump.title_id] = final
        created.append(final)
        progress(100)
        log(f'Saved {final}')
    return created
