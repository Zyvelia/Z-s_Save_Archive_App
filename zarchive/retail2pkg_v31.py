"""Use a user-supplied Retail2Pkg toolkit to build packages from a disc ISO.

Never execute Retail2Pkg.bat against an original game or conversion workspace:
the batch file renames, moves, and deletes directories. Prepare a separate copy
instead and run the batch there after user confirmation.
"""
from __future__ import annotations
import hashlib
import os
from time import monotonic
from types import SimpleNamespace
import shutil
import subprocess
import sys
import uuid
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from zipfile import ZipFile
from .app_assets import asset_path
from .converter_output_v21 import validate_pkg
from .iso_converter_v20 import inspect_game
from .windows_iso import copy_iso_game

REQUIRED_FILES = (
    'CFW2OFW_Helper.exe', 'Retail2Pkg.bat', 'makepkg1.exe',
    'makepkg2.exe', 'make_npdata.exe', 'PS3Merge.exe',
    'Karmian.Core.dll', 'Karmian.Framework.dll', 'EmList.json',
)
OPTIONAL_FILES = ('CFW2OFW_settings.ini', 'PS3Merge.exe.Config', 'MSVCR120.dll')
LAUNCHER_BATCH = 'Retail2Pkg_launcher.bat'
# The original toolkit and the first standalone launcher both omitted the
# helper's failure check. Leave other user-supplied batch variants untouched.
PREVIOUS_BATCHES = {
    'b6b84b399e1a97e7dbe88f87caf20352d4982bdde7119a273788a77f0004fafc',
    'b54937260c30310ddc25ad1c972aeceb9e5a81cb0ba34c4944915584850faea0',
}


def inspect_retail2pkg_folder(folder: str | Path) -> dict:
    """Validate the root of an unpacked Retail2Pkg kit; no code execution."""
    root = Path(folder).expanduser().resolve(strict=True)
    if not root.is_dir() or root.is_symlink():
        raise ValueError('Select the extracted Retail2Pkg folder, not the ZIP')
    missing = [name for name in REQUIRED_FILES if not (root / name).is_file()]
    if missing:
        raise ValueError('Retail2Pkg folder is missing: ' + ', '.join(missing))
    for name in (*REQUIRED_FILES, *OPTIONAL_FILES):
        item = root / name
        if item.is_symlink():
            raise ValueError(f'Symbolic links are not permitted in converter tools: {name}')
    return {'folder': str(root), 'helper': str(root / 'CFW2OFW_Helper.exe'),
            'batch': str(root / 'Retail2Pkg.bat'), 'files': [name for name in (*REQUIRED_FILES, *OPTIONAL_FILES) if (root / name).is_file()],
            'warning': 'Retail2Pkg.bat moves and deletes folders. Never run it inside your original source or conversion workspace.'}


def unpack_retail2pkg_kit(package: Path, destination: Path) -> None:
    """Copy tool files from an original toolkit ZIP or a standalone launcher ZIP."""
    names = {name.casefold(): name for name in (*REQUIRED_FILES, *OPTIONAL_FILES)}
    with ZipFile(package) as archive:
        tools = {}
        for member in archive.infolist():
            path = PurePosixPath(member.filename)
            if member.is_dir() or path.name.casefold() not in names:
                continue
            launcher_layout = path.parts[:2] == ('Retail2Pkg ISO Launcher', 'Retail2Pkg')
            if path.is_absolute() or '..' in path.parts or len(path.parts) > (3 if launcher_layout else 2):
                raise ValueError('Expected the original Retail2Pkg ZIP or the Retail2Pkg ISO Launcher ZIP.')
            entries = tools.setdefault(path.parent, {})
            name = names[path.name.casefold()]
            if name in entries or member.file_size > 64 * 1024**2:
                raise ValueError(f'Duplicate or oversized toolkit file in ZIP: {name}')
            entries[name] = member
        complete = [entries for entries in tools.values() if all(name in entries for name in REQUIRED_FILES)]
        if len(complete) != 1:
            raise ValueError('The ZIP must contain one complete Retail2Pkg toolkit with Retail2Pkg.bat and its companion tools.')
        for name, member in complete[0].items():
            with archive.open(member) as source, (destination / name).open('xb') as target:
                shutil.copyfileobj(source, target)


def _batch_working_directory(stage: Path) -> Path:
    # Retail2Pkg.bat expands %CD% without quotes in its move commands.
    if not any(c in str(stage) for c in ' &()^%!'):
        return stage
    from ctypes import WinDLL, create_unicode_buffer
    short_path = create_unicode_buffer(32768)
    length = WinDLL('kernel32').GetShortPathNameW(str(stage), short_path, len(short_path))
    if 0 < length < len(short_path) and not any(c in short_path.value for c in ' &()^%!'):
        return Path(short_path.value)
    raise ValueError('Retail2Pkg.bat requires a work path without spaces or CMD special characters. '
                     'Choose a local output folder with a simple path, such as C:\\PS3Build.')


def prepare_local_batch(iso_path: str | Path, tool_folder: str | Path,
                        output_folder: str | Path, *, progress=None,
                        extraction_progress=None) -> Path:
    """Extract disc data beside a fresh copy of the selected batch and tools."""
    def report(label, path):
        if progress is not None:
            progress(f'{label}: {path}')

    report('Checking ISO', iso_path)
    source = Path(iso_path).expanduser().resolve(strict=True)
    if not source.is_file() or source.suffix.lower() != '.iso':
        raise ValueError('Select an existing PS3 disc ISO.')
    report('Checking toolkit', tool_folder)
    kit = Path(tool_folder).expanduser().resolve(strict=True)
    if kit.is_file() and kit.suffix.lower() == '.zip':
        report('Unpacking toolkit', kit)
        with TemporaryDirectory(prefix='retail2pkg-kit-') as scratch:
            unpack_retail2pkg_kit(kit, Path(scratch))
            return prepare_local_batch(source, scratch, output_folder,
                                       progress=progress, extraction_progress=extraction_progress)
    toolkit = inspect_retail2pkg_folder(kit)
    report('Checking output folder', output_folder)
    output = Path(output_folder).expanduser().resolve(strict=True)
    if not output.is_dir() or output == kit or kit in output.parents or output in kit.parents:
        raise ValueError('Choose an existing output folder separate from the toolkit directory.')
    if str(output).startswith('\\\\'):
        raise ValueError('Choose an output folder on a local drive so Retail2Pkg can use it.')
    stage = output / ('Retail2Pkg_Build_' + uuid.uuid4().hex[:12])
    report('Working folder', stage)
    stage.mkdir()
    try:
        for name in toolkit['files']:
            shutil.copyfile(kit / name, stage / name)
        batch = stage / 'Retail2Pkg.bat'
        batch_hash = hashlib.sha256(batch.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
        if batch_hash in PREVIOUS_BATCHES:
            updated = asset_path(LAUNCHER_BATCH).read_bytes().splitlines()
            batch.write_bytes(b'\r\n'.join(updated) + b'\r\n')
            report('Using the updated Retail2Pkg batch in the working folder', batch)

        game = stage / 'PS3_GAME'
        copy_iso_game(source, game, progress=progress, extraction_progress=extraction_progress)
        info = inspect_game(game)
        report('Game found', f"{info['title']} [{info['title_id']}]")
    except Exception as exc:
        raise RuntimeError(f'{exc}\nWorking folder: {stage}') from exc
    report('PS3_GAME is beside Retail2Pkg.bat', stage)
    return stage


def stream_batch_log(process, log_path: Path, timeout: int, *, progress, console_status, encoding):
    """Read complete console lines and render the current line's backspaces."""
    deadline = monotonic() + timeout
    line = []
    cursor = 0
    previous_status = ''
    tail = ''
    with log_path.open(encoding=encoding, errors='replace', newline='') as reader:
        while True:
            try:
                exit_code = process.wait(timeout=0.25)
            except subprocess.TimeoutExpired:
                exit_code = None
                if monotonic() >= deadline:
                    process.kill()
                    process.wait()
                    raise TimeoutError('Retail2Pkg did not finish within the build timeout.')
            lines = []
            while chunk := reader.read(65536):
                for character in chunk:
                    if character == '\n':
                        lines.append(''.join(line))
                        line.clear()
                        cursor = 0
                    elif character == '\r':
                        cursor = 0
                    elif character == '\b':
                        cursor = max(0, cursor - 1)
                    elif cursor < len(line):
                        line[cursor] = character
                        cursor += 1
                    else:
                        line.append(character)
                        cursor += 1
            status = ''.join(line).rstrip()
            if exit_code is not None and status:
                lines.append(status)
                status = ''
            if lines:
                text = '\n'.join(lines)
                tail = (tail + text + '\n')[-30000:]
                if progress is not None:
                    progress(text)
            if status != previous_status and console_status is not None:
                console_status(status)
            previous_status = status
            if exit_code is not None:
                return SimpleNamespace(returncode=exit_code, stdout=tail, stderr='')


def run_windows_batch(stage, timeout, progress, console_status):
    staged_lines = (stage / 'Retail2Pkg.bat').read_bytes().splitlines()
    launcher_lines = asset_path(LAUNCHER_BATCH).read_bytes().splitlines()
    launcher_batch = [line.rstrip() for line in staged_lines] == launcher_lines
    working_dir = stage if launcher_batch else _batch_working_directory(stage)
    env = dict(os.environ)
    env['PATH'] = str(working_dir) + os.pathsep + env.get('PATH', '')
    log_name = f'Retail2Pkg_{uuid.uuid4().hex[:8]}.log'
    log_path = stage / log_name
    log_path.touch(exist_ok=False)
    batch_argument = ' /launcher' if launcher_batch else ''
    command = ['cmd.exe', '/d', '/v:off', '/s', '/c',
               'title Retail2Pkg - Watch the log in Save Archive'
               ' & echo Watch the log in Save Archive. Use this window for input prompts.'
               rf' & call .\Retail2Pkg.bat{batch_argument} > {log_name} 2>&1']
    # Redirect inside cmd so Windows still gives the new console a keyboard.
    with subprocess.Popen(command, cwd=working_dir, env=env,
                          creationflags=subprocess.CREATE_NEW_CONSOLE) as process:
        try:
            return stream_batch_log(process, log_path, timeout, progress=progress,
                                    console_status=console_status, encoding='oem')
        except BaseException:
            if process.poll() is None:
                process.kill()
            raise


def build_pkgs_locally(iso_path: str | Path, tool_folder: str | Path,
                       output_folder: str | Path, *, timeout: int = 7200,
                       runner=None, progress=None, extraction_progress=None, console_status=None) -> dict:
    """Run the chosen Retail2Pkg batch on an isolated copy of disc input.

    This is an explicit opt-in to execute the user's third-party batch file.
    The batch manipulates and removes its own working directories; originals
    remain untouched. Produced PKGs are copied to the selected local folder.
    """
    if sys.platform != 'win32' and runner is None:
        raise OSError('Retail2Pkg batch execution requires Windows')
    stage = prepare_local_batch(iso_path, tool_folder, output_folder,
                                progress=progress, extraction_progress=extraction_progress)
    output = stage.parent
    previous_packages = {path for path in stage.rglob('*') if path.suffix.lower() == '.pkg'}
    command = ['cmd.exe', '/d', '/c', 'call', 'Retail2Pkg.bat']
    if progress is not None:
        progress('Starting Retail2Pkg.bat. Its output appears here. Use the Windows console for key prompts.')
    try:
        if runner is None:
            result = run_windows_batch(stage, timeout, progress, console_status)
        else:
            result = runner(command, cwd=stage, stdin=subprocess.DEVNULL,
                            capture_output=True, text=True, errors='replace',
                            timeout=timeout, check=False)
    except Exception as exc:
        raise RuntimeError(f'{exc}\nStaging folder: {stage}') from exc
    if progress is not None:
        progress(f'Retail2Pkg.bat exited with code {result.returncode}. Checking for new PKG files…')
    log = ((result.stdout or '') + '\n' + (result.stderr or ''))[-30000:]
    packages = sorted(path for path in stage.rglob('*')
                      if path.suffix.lower() == '.pkg' and path not in previous_packages
                      and path.relative_to(stage).parts[0].casefold() not in {'patch', 'ps3_game'})
    output_pkgs = []
    if result.returncode == 0:
        for pkg in packages:
            try:
                validate_pkg(stage, pkg)
            except (OSError, ValueError):
                continue
            dest = output / pkg.name
            if dest.exists():
                # Preserve previous output and never silently replace it.
                raise FileExistsError(f'Output package already exists: {dest}; source remains in {stage}')
            if progress is not None:
                progress(f'Copying {pkg.name} ({pkg.stat().st_size / 1024**2:.1f} MiB) to the output folder.')
            # Exclusive create prevents overwrite even if files appear mid-build.
            with pkg.open('rb') as src, dest.open('xb') as dst:
                shutil.copyfileobj(src, dst, 1024*1024)
            output_pkgs.append(str(dest))
    success = result.returncode == 0 and bool(output_pkgs)
    status = 'Completed' if success else 'No valid PKGs produced; inspect the staging folder and build log'
    (stage / 'LOCAL_BUILD_RESULT.txt').write_text(
        f'{status}\nBuilder exit code: {result.returncode}\nPackages copied: {len(output_pkgs)}\n\n{log}',
        encoding='utf-8', errors='replace')
    return {'success': success, 'exit_code': result.returncode,
            'packages': output_pkgs, 'staging': str(stage),
            'output_folder': str(output), 'log': log,
            'warning': 'Package magic checked only; game compatibility and installability are not guaranteed.'}
