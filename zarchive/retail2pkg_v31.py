"""Optional, user-supplied Retail2Pkg integration.

Never execute Retail2Pkg.bat against an original game or conversion workspace:
the batch file renames, moves, and deletes directories. Prepare a separate copy
instead, leaving actual execution to the user after inspecting the staged files.
"""
from __future__ import annotations
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from .converter_output_v21 import inspect_conversion_output

REQUIRED_FILES = (
    'CFW2OFW_Helper.exe', 'Retail2Pkg.bat', 'makepkg1.exe',
    'makepkg2.exe', 'make_npdata.exe', 'PS3Merge.exe',
    'Karmian.Core.dll', 'Karmian.Framework.dll', 'EmList.json',
)
OPTIONAL_FILES = ('CFW2OFW_settings.ini', 'PS3Merge.exe.Config')


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


def prepare_retail2pkg_handoff(workspace: str | Path, tool_folder: str | Path,
                               destination: str | Path) -> dict:
    """Copy compatible converted output and tool files to a NEW independent folder.

    The Retail2Pkg batch expects a BL*/BC* parent with both an NP* game
    folder and a BL*/BC* patch folder. Reject layouts that cannot be used
    rather than copying a pile of unrelated files and reporting success.
    """
    tools = inspect_retail2pkg_folder(tool_folder)
    source = Path(workspace).expanduser().resolve(strict=True)
    target = Path(destination).expanduser().absolute()
    if target.exists():
        raise FileExistsError('Select a new handoff folder; existing files cannot be overwritten')
    if not target.parent.is_dir() or target.parent.is_symlink():
        raise ValueError('Destination parent must be a normal, existing folder')
    report = inspect_conversion_output(source)
    toolroot = Path(tools['folder'])
    for origin in (source, toolroot):
        if target == origin or origin in target.parents or target in origin.parents:
            raise ValueError('Handoff must be separate from the conversion workspace and Retail2Pkg installation')
    candidates = []
    for folder in report['folders']:
        path = source / folder['relative_path']
        parent = path.parent
        if parent == source or not parent.name.upper().startswith(('BL','BC')):
            continue
        # Must include both converted digital game and physical patch directories.
        names = [p.name.upper() for p in parent.iterdir() if p.is_dir() and not p.is_symlink()]
        if any(n.startswith('NP') for n in names) and any(n.startswith(('BL','BC')) for n in names):
            if parent not in candidates: candidates.append(parent)
    if len(candidates) != 1:
        raise ValueError('Expected exactly one converted BL*/BC* parent containing NP* game and BL*/BC* patch folders. '
                         'Finish CFW2OFW conversion and inspect its output before preparing PKGs.')
    parent = candidates[0]
    for current, dirs, files in os.walk(parent, followlinks=False):
        for name in dirs + files:
            if (Path(current) / name).is_symlink():
                raise ValueError('Conversion output contains a symbolic link; refusing to copy')
    target.mkdir(parents=False, exist_ok=False)
    try:
        for name in tools['files']:
            shutil.copy2(toolroot / name, target / name)
        shutil.copytree(parent, target / parent.name)
        instructions = (
            'Retail2Pkg handoff (COPY). Your originals have not been changed.\n'
            'Review the copied folder layout before running any program.\n'
            'Retail2Pkg.bat MOVES and DELETES folders inside this handoff.\n'
            'The app does not run the batch file automatically or guarantee valid PKGs.\n'
            'If you choose to run it, launch it from THIS handoff folder only.\n'
            'Review resulting PKGs before transferring or installing on PS3.\n'
        )
        (target / 'RETAIL2PKG_HANDOFF_README.txt').write_text(instructions, encoding='utf-8')
        return {'destination': str(target), 'folders': [parent.name], 'instructions': instructions}
    except BaseException:
        # The output is an independent, new copy. Leave partial data for review
        # rather than silently deleting potentially large files.
        (target / 'HANDOFF_INCOMPLETE.txt').write_text('Preparation failed; inspect and delete this incomplete staging folder manually.\n', encoding='utf-8')
        raise


def build_pkgs_locally(workspace: str | Path, tool_folder: str | Path,
                       output_folder: str | Path, *, timeout: int = 7200,
                       runner=None) -> dict:
    """Build using a *new* isolated Retail2Pkg handoff, with no FTP calls.

    This is an explicit opt-in to execute the user's third-party batch file.
    The batch manipulates and removes its own working directories; originals
    remain untouched. Produced PKGs are copied to the selected local folder.
    """
    if sys.platform != 'win32' and runner is None:
        raise OSError('Retail2Pkg batch execution requires Windows')
    source = Path(workspace).expanduser().resolve(strict=True)
    kit = Path(tool_folder).expanduser().resolve(strict=True)
    output = Path(output_folder).expanduser().resolve(strict=True)
    if not output.is_dir() or output.is_symlink():
        raise ValueError('Select an existing normal folder for local PKG output')
    for origin in (source, kit):
        if output == origin or output in origin.parents or origin in output.parents:
            raise ValueError('The PKG output folder must be separate from the conversion workspace and toolkit')
    # Isolated stage is never reused, avoiding accidental deletion of earlier builds.
    stage = output / ('Retail2Pkg_Build_' + uuid.uuid4().hex[:12])
    prepared = prepare_retail2pkg_handoff(source, kit, stage)
    command = ['cmd.exe', '/d', '/c', 'call', 'Retail2Pkg.bat']
    invoke = runner or subprocess.run
    try:
        result = invoke(command, cwd=stage, stdin=subprocess.DEVNULL,
                        capture_output=True, text=True, errors='replace',
                        timeout=timeout, check=False)
    except Exception:
        (stage / 'BUILD_FAILED.txt').write_text('The external builder raised an error; inspect this staging folder.\n', encoding='utf-8')
        raise
    log = ((result.stdout or '') + '\n' + (result.stderr or ''))[-30000:]
    packages = sorted(stage.rglob('*.pkg'))
    output_pkgs = []
    if result.returncode == 0:
        for pkg in packages:
            if pkg.is_symlink() or not pkg.is_file() or pkg.stat().st_size < 64:
                continue
            with pkg.open('rb') as f:
                if f.read(4) != b'\x7fPKG':
                    continue
            dest = output / pkg.name
            if dest.exists():
                # Preserve previous output and never silently replace it.
                raise FileExistsError(f'Output package already exists: {dest}; source remains in {stage}')
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
