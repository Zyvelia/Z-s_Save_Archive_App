"""Stage a dragged Borderlands save into the protected editor workspace.

Never edit the original dropped file. Reject raw PS4 containers, symlinks,
oversized files, duplicate drop payloads and invalid/mismatched game data.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import uuid

from .bl3_native import load_character, load_profile

LIMIT = 32 * 1024 * 1024


def stage_dropped_save(source, workspace, *, platform, kind):
    src = Path(source).expanduser()
    root = Path(workspace).resolve(strict=True)
    if not root.is_dir() or root.is_symlink():
        raise ValueError('The protected working directory is unavailable.')
    if src.is_symlink() or not src.is_file():
        raise ValueError('Drop a regular save file, not a directory or shortcut.')
    if not 32 <= src.stat().st_size <= LIMIT:
        raise ValueError('Save size is outside the supported GVAS range.')
    src = src.resolve(strict=True)
    # Decode before writing anything into the workspace.
    reader = load_character if kind == 'character' else load_profile if kind == 'profile' else None
    if reader is None:
        raise ValueError('Unknown save type.')
    reader(src, platform)
    digest = hashlib.sha256(src.read_bytes()).hexdigest()
    folder = root / 'Dropped_Saves'
    if folder.is_symlink():
        raise ValueError('Dropped save directory cannot be a symbolic link.')
    folder.mkdir(exist_ok=True)
    if not folder.resolve().is_relative_to(root):
        raise ValueError('Invalid drop destination.')
    target = folder / f'{kind}_{uuid.uuid4().hex[:12]}_{src.name}'
    # The original filename remains visible while each import is unique.
    with src.open('rb') as original, target.open('xb') as copy:
        shutil.copyfileobj(original, copy, 1024 * 1024)
    try:
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError('Copied save failed integrity verification.')
        if hashlib.sha256(src.read_bytes()).hexdigest() != digest:
            raise ValueError('Dropped source changed while importing.')
        reader(target, platform)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return target
