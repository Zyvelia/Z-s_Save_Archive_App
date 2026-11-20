"""Safe PS3 disc-image conversion assistant. Never modifies the selected source.

CFW2OFW Helper is an optional, separately installed third-party program.
It may delete PS3_GAME in its work directory; this adapter stages a copy.
"""
from __future__ import annotations
import os, re, shutil, subprocess, json
from tempfile import TemporaryFile
from pathlib import Path
from datetime import datetime, timezone
from .storage import read_param_sfo

TITLE_ID = re.compile(r'^(?:BLUS|BLES|BCUS|BCES|BLJM|BLJS|BCJS|BCAS|BLAS|BLKS|BCKS)[0-9]{5}$', re.I)


def find_7zip(*, env=None, exists=None, registry=None) -> Path | None:
    """Find 7z.exe on Windows. All paths validated; no binary is downloaded."""
    env = os.environ if env is None else env
    exists = (lambda p: p.is_file()) if exists is None else exists
    candidates = []
    override = env.get('Z_ARCHIVE_7ZIP')
    if override: candidates.append(Path(override.strip('"')))
    for key in ('ProgramFiles', 'ProgramFiles(x86)', 'ProgramW6432'):
        if env.get(key): candidates.append(Path(env[key]) / '7-Zip' / '7z.exe')
    if env.get('LOCALAPPDATA'):
        candidates.append(Path(env['LOCALAPPDATA']) / 'Programs' / '7-Zip' / '7z.exe')
    for folder in env.get('PATH', '').split(os.pathsep):
        if folder.strip(): candidates.append(Path(folder.strip('"')) / '7z.exe')
    if registry is None:
        registry = []
        if os.name == 'nt':
            try:
                import winreg
                for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                    for key in (r'SOFTWARE\7-Zip', r'SOFTWARE\WOW6432Node\7-Zip'):
                        try:
                            with winreg.OpenKey(hive, key) as handle:
                                root = winreg.QueryValueEx(handle,'Path')[0]
                                registry.append(root)
                        except OSError: pass
            except ImportError: pass
    for directory in registry:
        candidates.append(Path(directory) / '7z.exe')
    for candidate in candidates:
        try:
            if candidate.name.lower() == '7z.exe' and exists(candidate): return candidate
        except (OSError, ValueError): pass
    return None


def _progress(callback, text):
    if callback is not None: callback(text)


def inspect_game(folder: str | Path) -> dict:
    p = Path(folder).resolve(strict=True)
    game = p if p.name.upper() == 'PS3_GAME' else p / 'PS3_GAME'
    if not game.is_dir() or game.is_symlink():
        raise ValueError('Select a PS3_GAME folder or its containing directory')
    sfo = game / 'PARAM.SFO'
    if not sfo.is_file() or sfo.is_symlink():
        raise ValueError('PS3_GAME/PARAM.SFO is missing')
    info = read_param_sfo(sfo)
    title_id = info.get('TITLE_ID', '').upper()
    if not TITLE_ID.fullmatch(title_id):
        raise ValueError('Unsupported or unrecognized PS3 disc TITLE_ID')
    return {'title_id': title_id, 'title': info.get('TITLE','Unknown Game'), 'source': str(game), 'metadata': info}


def validate_helper(path: str | Path) -> Path:
    exe = Path(path).resolve(strict=True)
    if not exe.is_file() or exe.suffix.lower() != '.exe':
        raise ValueError('Select a CFW2OFW Helper .exe file')
    return exe


def inspect_iso(path: str | Path) -> dict:
    iso = Path(path).resolve(strict=True)
    if not iso.is_file() or iso.suffix.lower() != '.iso':
        raise ValueError('Select an existing .iso file')
    with iso.open('rb') as f:
        magic = f.read(0x10000)
    if b'CD001' not in magic and not any(magic[offset + 1:offset + 6] in {b'NSR02', b'NSR03'}
               for offset in range(0x8000, len(magic), 2048)):
        raise ValueError('ISO 9660 or UDF signature not detected; verify your ISO before extraction')
    return {'name': iso.name, 'bytes': iso.stat().st_size, 'source': str(iso), 'note':'ISO extraction is performed by a separately installed 7-Zip command-line tool; encrypted disc images may not extract.'}


class StagingCancelled(Exception):
    pass


def check_cancelled(cancelled):
    if cancelled is not None and cancelled():
        raise StagingCancelled('Staging cancelled. Any partial workspace was kept.')


def copy_staging_file(src, dest, cancelled):
    if cancelled is None:
        return shutil.copy2(src, dest)
    with open(src, 'rb') as source, open(dest, 'xb') as target:
        while True:
            check_cancelled(cancelled)
            block = source.read(1024 * 1024)
            if not block:
                break
            target.write(block)
    shutil.copystat(src, dest)
    return dest


def safe_copy_tree(src: Path, dest: Path, cancelled=None) -> None:
    if src.is_symlink() or not src.is_dir(): raise ValueError('Source folder cannot be a symlink')
    def reject_links(folder, names):
        check_cancelled(cancelled)
        for name in names:
            child = Path(folder) / name
            if child.is_symlink() or getattr(child, 'is_junction', lambda: False)():
                raise ValueError('Source contains symbolic links, which are not supported')
        return []
    shutil.copytree(src, dest, ignore=reject_links,
                    copy_function=lambda source, target: copy_staging_file(source, target, cancelled))


def extract_iso(command, cancelled, progress=None):
    # A file keeps large extractor logs out of memory and avoids pipe deadlocks.
    with TemporaryFile() as log, subprocess.Popen(
        command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT
    ) as process:
        from time import monotonic
        started = monotonic()
        deadline = started + 3600
        next_update = started + 10
        try:
            while True:
                check_cancelled(cancelled)
                try:
                    code = process.wait(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    now = monotonic()
                    if now >= deadline:
                        raise RuntimeError('7-Zip extraction timed out after one hour.')
                    if now >= next_update:
                        elapsed = int(now - started)
                        _progress(progress, f'7-Zip is still extracting ({elapsed // 60}:{elapsed % 60:02d} elapsed).')
                        next_update = now + 10
        except BaseException:
            process.kill()
            process.wait()
            raise
        if code:
            length = log.seek(0, os.SEEK_END)
            log.seek(max(0, length - 1200))
            raise RuntimeError('7-Zip extraction failed: ' + log.read().decode(errors='replace'))


def find_extracted_game(root: Path, cancelled=None) -> Path:
    """Find the single game folder even when the image has a wrapper directory."""
    games = []
    for directory, children, _ in os.walk(root, followlinks=False):
        check_cancelled(cancelled)
        parent = Path(directory)
        for name in children[:]:
            child = parent / name
            if child.is_symlink() or getattr(child, 'is_junction', lambda: False)():
                children.remove(name)
            elif name.upper() == 'PS3_GAME':
                children.remove(name)
                games.append(child)
    if len(games) != 1:
        if not games:
            raise ValueError('The extracted ISO has no PS3_GAME folder. Check that this is an extractable PS3 disc image.')
        raise ValueError('The ISO contains multiple PS3_GAME folders. Select the game folder you want to package.')
    return games[0]


def next_workspace(parent: str | Path, source: str | Path, *, timestamp: str | None = None) -> Path:
    """Find a fresh child staging directory under a reusable parent.

    This does not create or overwrite anything. stage_conversion retains its
    exclusive-create safety check against collisions and racing processes.
    """
    folder = Path(parent).expanduser().resolve()
    if folder.exists() and (not folder.is_dir() or folder.is_symlink()):
        raise ValueError('Workspace parent must be a regular directory')
    src = Path(source)
    label = src.stem if src.suffix.lower() == '.iso' else (src.parent.name if src.name.upper() == 'PS3_GAME' else src.name)
    label = re.sub(r'[^A-Za-z0-9_-]+', '_', label).strip('_')[:36] or 'PS3_Game'
    stamp = timestamp or datetime.now().strftime('%Y%m%d_%H%M%S')
    if not re.fullmatch(r'[0-9]{8}_[0-9]{6}', stamp):
        raise ValueError('Invalid workspace timestamp')
    stem = f'{label}_{stamp}'
    for count in range(10000):
        candidate = folder / (stem if count == 0 else f'{stem}_{count:03d}')
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    raise FileExistsError('No unused conversion workspace name available')


def stage_conversion(source: str | Path, helper: str | Path, destination: str | Path, *, extractor: str | Path | None = None, progress=None, cancelled=None) -> dict:
    """Prepare a newly created workspace, preserving inputs; never run downloaded tools implicitly."""
    _progress(progress, "Checking conversion helper and source...")
    check_cancelled(cancelled)
    tool = validate_helper(helper)
    work = Path(destination).expanduser().resolve()
    if work.exists(): raise FileExistsError('Choose a new, empty workspace path; existing files will not be overwritten')
    src = Path(source).resolve(strict=True)
    if src.is_dir():
        info = inspect_game(src)
    elif src.suffix.lower() == '.iso':
        inspect_iso(src)
        if not extractor:
            detected = find_7zip()
            if not detected: raise ValueError('ISO extraction requires 7z.exe; use Auto-find or Browse')
            extractor = detected
        ex = Path(extractor).resolve(strict=True)
        if not ex.is_file() or ex.suffix.lower() != '.exe': raise ValueError('Select a valid 7z.exe')
        info = None
    else: raise ValueError('Select a PS3_GAME folder or a PS3 ISO')
    # Require workspace outside source and helper directories.
    if src.is_dir() and (src == work or src in work.parents or work in src.parents):
        raise ValueError('Work directory must be separate from game source')
    if tool.parent == work or tool.parent in work.parents or work in tool.parent.parents:
        raise ValueError('Work directory must be separate from helper installation')
    _progress(progress, "Creating separate staging workspace...")
    check_cancelled(cancelled)
    work.mkdir(parents=True, exist_ok=False)
    try:
        # Copy executable and support files into work folder, never copy arbitrary subtrees.
        _progress(progress, "Copying converter support files...")
        for entry in tool.parent.iterdir():
            check_cancelled(cancelled)
            if entry.name.lower() in {'conversion_manifest.json', 'staging_failed.txt',
                                     'staging_cancelled.txt', 'converter_status.json'}:
                continue
            if entry.is_symlink(): raise ValueError('Converter installation contains symlinks')
            if entry.is_file() and entry.stat().st_size <= 256*1024*1024:
                copy_staging_file(entry, work / entry.name, cancelled)
        staged_tool = work / tool.name
        if not staged_tool.exists():raise ValueError('Converter executable was not staged')
        if info is None:
            _progress(progress, f'Extracting {src.name} ({src.stat().st_size / 1024**3:.2f} GiB) with 7-Zip.')
            _progress(progress, f'7-Zip executable: {ex}')
            extract_dir = work / 'extracted'
            extract_dir.mkdir()
            command = [str(ex),'x','-y',f'-o{extract_dir}',str(src)]
            extract_iso(command, cancelled, progress)
            _progress(progress, 'Finding and validating extracted PS3_GAME...')
            game = find_extracted_game(extract_dir, cancelled)
            info = inspect_game(game)
            _progress(progress, f"Found {info['title']} [{info['title_id']}] in {game.relative_to(extract_dir)}.")
            _progress(progress, 'Placing PS3_GAME beside the toolkit files…')
            shutil.move(str(game),str(work / 'PS3_GAME'))
            shutil.rmtree(extract_dir)
        else:
            _progress(progress, 'Copying PS3_GAME (large games may take a while)...')
            safe_copy_tree(Path(info['source']),work / 'PS3_GAME', cancelled)
        check_cancelled(cancelled)
        meta = {'title_id':info['title_id'],'title':info['title'],'input':str(src),'helper':str(tool),
                'created_utc':datetime.now(timezone.utc).isoformat(), 'workspace':str(work),
                'warning':'Conversion requires separate confirmation and does not guarantee an installable PKG or a working XMB game.'}
        _progress(progress, 'Saving conversion manifest...')
        (work/'conversion_manifest.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
        _progress(progress, 'Staging completed successfully.')
        return meta
    except BaseException as exc:
        marker = 'STAGING_CANCELLED.txt' if isinstance(exc, StagingCancelled) else 'STAGING_FAILED.txt'
        try:
            (work / marker).write_text(str(exc), encoding='utf-8')
        except OSError:
            pass
        raise


def helper_command(workspace: str | Path, helper_name: str) -> list[str]:
    work = Path(workspace).resolve(strict=True)
    name = Path(helper_name).name
    if name != helper_name:raise ValueError('Expected helper executable filename, not an arbitrary path')
    exe = work / name
    if not exe.is_file() or exe.suffix.lower()!='.exe' or not (work/'PS3_GAME').is_dir():
        raise ValueError('Missing staged helper or PS3_GAME')
    return [str(exe)]
