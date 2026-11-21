"""Use the bundled Retail2Pkg v3 workflow with paths selected in Save Archive."""
from __future__ import annotations

from collections import deque
import hashlib
import re
import os
from pathlib import Path
import shutil
import subprocess
import sys
from time import monotonic
from types import SimpleNamespace
import uuid
from zipfile import ZipFile

from .app_assets import asset_path
from .converter_output_v21 import validate_pkg
from .console_v27 import summarize_transfer
from .iso_converter_v20 import inspect_game
from .windows_iso import copy_folder_game, copy_iso_game

LAUNCHER_FOLDER = 'Retail2Pkg ISO Launcher'
SCRIPT_HASHES = {
    'Start.cmd': '6ec0b7607d1edbf7603735f00513948af21eef3466419ba4d049395b3bf5e517',
    'Launch.ps1': '5591f9ec97ba8a8e74712958d2d2af30edcde50f107c620e04625210000cb9df',
}
TOOL_FILES = (
    'CFW2OFW_Helper.exe', 'CFW2OFW_settings.ini', 'EmList.json',
    'Karmian.Core.dll', 'Karmian.Framework.dll', 'PS3Merge.exe',
    'PS3Merge.exe.Config', 'Retail2Pkg.bat', 'make_npdata.exe',
    'makepkg1.exe', 'makepkg2.exe', 'package.conf',
)


def extract_toolkit(archive_path: Path, destination: Path) -> None:
    """Stage the bundled batch and companion files in the work folder."""
    required = (*SCRIPT_HASHES, *(f'Retail2Pkg/{name}' for name in TOOL_FILES))
    optional = 'Retail2Pkg/MSVCR120.dll'
    with ZipFile(archive_path) as archive:
        members = {}
        for entry in archive.infolist():
            relative = entry.filename.removeprefix(LAUNCHER_FOLDER + '/')
            if relative not in required and relative != optional:
                continue
            if relative in members or entry.is_dir() or entry.file_size > 16 * 1024**2:
                raise ValueError(f'Invalid or duplicate Retail2Pkg launcher file: {relative}')
            members[relative] = entry
        missing = [name for name in required if name not in members]
        if missing:
            raise ValueError('Select the complete Retail2Pkg ISO Launcher v3 ZIP. Missing: ' + ', '.join(missing))
        for name, expected in SCRIPT_HASHES.items():
            script = archive.read(members[name]).replace(b'\r\n', b'\n')
            if hashlib.sha256(script).hexdigest() != expected:
                raise ValueError(f'{name} differs from the supported Retail2Pkg ISO Launcher v3 script.')
        for name, entry in members.items():
            if not name.startswith('Retail2Pkg/'):
                continue
            with archive.open(entry) as source, (destination / Path(name).name).open('xb') as target:
                shutil.copyfileobj(source, target)


class PatchProgress:
    """Estimate the current patch from the helper's reported percentages."""

    def __init__(self):
        self.patch = None
        self.samples = deque(maxlen=12)

    def update(self, line, now):
        match = re.fullmatch(r'(.+?\.pkg)\s+\.\.\.\s*(\d{1,3})%\s*', line, re.I)
        if not match or int(match[2]) > 100:
            self.patch = None
            self.samples.clear()
            return
        patch, percent = match[1], int(match[2])
        if patch != self.patch or (self.samples and percent < self.samples[-1]['bytes']):
            self.samples.clear()
        self.patch = patch
        if not self.samples or percent > self.samples[-1]['bytes']:
            self.samples.append({'time': now, 'bytes': percent, 'total': 100})

    def estimate(self, now):
        if not self.samples:
            return None
        last = self.samples[-1]
        if last['bytes'] >= 100:
            return 'Patch download complete'
        quiet = now - last['time']
        if quiet >= 20:
            return f"Patch {last['bytes']}% · no progress for {int(quiet)}s"
        if last['time'] - self.samples[0]['time'] < 1:
            return f"Patch {last['bytes']}% · estimating time left…"
        eta = summarize_transfer(self.samples)['eta_seconds']
        remaining = max(1, round(eta))
        minutes, seconds = divmod(remaining, 60)
        return f"Patch {last['bytes']}% · about {minutes}:{seconds:02d} left"


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
    system_root = Path(os.environ.get('SystemRoot', r'C:\Windows'))
    log_name = 'Retail2Pkg.log'
    log_path = stage / log_name
    log_path.touch(exist_ok=False)
    launch_line = (r'title Retail2Pkg - Save Archive & echo See Save Archive for the live log.'
                   rf' & call .\Retail2Pkg.bat /launcher > {log_name} 2>&1')
    command = [str(system_root / 'System32' / 'cmd.exe'), '/d', '/v:off', '/s', '/c', launch_line]
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    # Keep a console for the legacy helper API while hiding its window.
    startup.wShowWindow = subprocess.SW_HIDE
    with subprocess.Popen(command, cwd=stage, startupinfo=startup,
                          creationflags=subprocess.CREATE_NEW_CONSOLE) as process:
        try:
            return stream_batch_log(process, log_path, timeout, progress=progress,
                                    console_status=console_status, encoding='oem')
        except BaseException:
            if process.poll() is None:
                process.kill()
            raise


def find_packages(stage: Path) -> list[Path]:
    for folder in sorted(stage.iterdir()):
        # CFW2OFW can name the directory after the game followed by its disc ID.
        # Retail2Pkg names the game and update PKGs after that full directory name.
        if not folder.is_dir() or folder.is_symlink() or getattr(folder, 'is_junction', lambda: False)():
            continue
        game = folder / f'{folder.name}.pkg'
        update = folder / f'{folder.name}_-_Update.pkg'
        if not (game.is_file() and update.is_file()):
            continue
        packages = [game, update]
        fix = folder / f'{folder.name}_-_Fix.pkg'
        if fix.is_file():
            packages.append(fix)
        for package in packages:
            validate_pkg(stage, package)
        return packages
    raise ValueError('Retail2Pkg did not leave both the game and update PKGs.')


def build_pkgs_locally(source_path, output_folder, *, progress=None, extraction_progress=None,
                       console_status=None, runner=None, timeout=7200):
    if sys.platform != 'win32' and runner is None:
        raise OSError('Retail2Pkg requires Windows 10 or 11.')
    if progress:
        progress(f'Checking game source: {source_path}')
    source = Path(source_path).expanduser().resolve(strict=True)
    from_iso = source.is_file() and source.suffix.lower() == '.iso'
    if not from_iso:
        if not source.is_dir():
            raise ValueError('Select an existing PS3 disc ISO or PS3_GAME folder.')
        source = Path(inspect_game(source)['source'])
    if progress:
        progress(f'Checking output folder: {output_folder}')
    output = Path(output_folder).expanduser().resolve(strict=True)
    if not output.is_dir() or str(output).startswith('\\\\'):
        raise ValueError('Choose an existing output folder on a local drive.')

    if not from_iso and (output == source or source in output.parents):
        raise ValueError('Choose an output folder outside the source PS3_GAME folder.')

    stage = output / ('Retail2Pkg_' + uuid.uuid4().hex[:8])
    if progress:
        progress(f'Working folder: {stage}')
    stage.mkdir()
    try:
        extract_toolkit(asset_path('Retail2Pkg_ISO_Launcher_v3.zip'), stage)
        if runner is None:
            system_root = Path(os.environ.get('SystemRoot', r'C:\Windows'))
            x86_system = system_root / 'SysWOW64'
            if not x86_system.is_dir():
                x86_system = system_root / 'System32'
            if not any((folder / 'MSVCR120.dll').is_file() for folder in (x86_system, stage)):
                raise RuntimeError('Install the Microsoft Visual C++ 2013 Redistributable (x86) to supply MSVCR120.dll.')
        game = stage / 'PS3_GAME'
        copy_game = copy_iso_game if from_iso else copy_folder_game
        copy_game(source, game, progress=progress, extraction_progress=extraction_progress)
        info = inspect_game(game)
        if progress:
            progress(f"Found {info['title']} [{info['title_id']}]. Starting Retail2Pkg.bat.")
            progress('If PS3Merge opens, select the working folder printed above.')
        invoke = runner or run_windows_batch
        result = invoke(stage, timeout, progress, console_status)
        if result.returncode:
            raise RuntimeError(f'Retail2Pkg exited with code {result.returncode}. Check the build log.')
        packages = find_packages(stage)
        return {'packages': [str(path) for path in packages], 'folder': str(packages[0].parent)}
    except (OSError, RuntimeError, ValueError) as exc:
        raise RuntimeError(f'{exc}\nWorking folder: {stage}') from exc
