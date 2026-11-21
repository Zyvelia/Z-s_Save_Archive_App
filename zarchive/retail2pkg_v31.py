"""Run the user-selected Retail2Pkg ISO Launcher v3 on Windows."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile

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


def extract_launcher(archive_path: Path, destination: Path) -> None:
    """Stage the known launcher scripts and the companion files they need."""
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
        (destination / 'Retail2Pkg').mkdir()
        for name, entry in members.items():
            with archive.open(entry) as source, (destination / name).open('xb') as target:
                shutil.copyfileobj(source, target)


def run_launcher(archive_path: str | Path, *, runner=None) -> None:
    if sys.platform != 'win32' and runner is None:
        raise OSError('Retail2Pkg ISO Launcher requires Windows 10 or 11.')
    package = Path(archive_path).expanduser().resolve(strict=True)
    if not package.is_file() or package.suffix.lower() != '.zip':
        raise ValueError('Select the Retail2Pkg ISO Launcher v3 ZIP.')
    cmd = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'cmd.exe'
    with TemporaryDirectory(prefix='save-archive-retail2pkg-') as temporary:
        staging = Path(temporary)
        extract_launcher(package, staging)
        # Keep the original console and file dialogs, including the final pause.
        launch = runner or subprocess.run
        result = launch([str(cmd), '/d', '/c', r'.\Start.cmd'], cwd=staging,
                        creationflags=getattr(subprocess, 'CREATE_NEW_CONSOLE', 0), check=False)
        if result.returncode:
            raise RuntimeError(f'Retail2Pkg ISO Launcher exited with code {result.returncode}. '
                               'Its console displays the conversion error before closing.')
