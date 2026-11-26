"""Verified, backup-first in-place writes for BL3 character/profile files.

Every edit is first exported and re-decoded by the existing BL3 codec,
then the original source is copied to a timestamped backup (exclusive name)
and verified before atomically replacing the same filename.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
import uuid

from .bl3_native import write_character_copy, write_profile_copy


def _digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        while block := stream.read(1024 * 1024):
            h.update(block)
    return h.hexdigest()


def save_with_backup(source, *, kind, expected_sha256, platform, **values):
    """Return (source_path, backup_path); preserve source if backup fails.

    Requires a regular writable file; rejects symlinks and hardlinked files.
    The source must have the expected hash. Backups live beside the original
    in 'ZSaveArchive_Backups', with unique timestamped names.
    """
    original = Path(source).expanduser()
    if original.is_symlink() or not original.is_file():
        raise ValueError('Select a regular save file, not a symlink.')
    source = original.resolve(strict=True)
    if source.stat().st_nlink != 1:
        raise ValueError('Hard-linked saves cannot be edited in place safely.')
    if not os.access(source, os.W_OK):
        raise PermissionError('Source save is not writable.')
    if _digest(source) != expected_sha256:
        raise ValueError('The source save changed since loading. Reload before editing.')
    if kind == 'character':
        writer = write_character_copy
    elif kind == 'profile':
        writer = write_profile_copy
    else:
        raise ValueError('Unsupported save type.')

    backup_dir = source.parent / 'ZSaveArchive_Backups'
    if backup_dir.is_symlink():
        raise ValueError('Backup folder cannot be a symbolic link.')
    # Build and verify an edited copy first. If codec validation fails the
    # original and backup directory are unchanged.
    with tempfile.TemporaryDirectory(prefix='.zsa-edit-', dir=source.parent) as tmp:
        edited = Path(tmp) / source.name
        writer(source, edited, expected_sha256=expected_sha256,
               platform=platform, **values)
        if _digest(source) != expected_sha256:
            raise ValueError('Source changed while preparing the edit.')
        expected_output = _digest(edited)

        backup_dir.mkdir(exist_ok=True)
        if not backup_dir.is_dir() or backup_dir.is_symlink():
            raise ValueError('Backup folder is not a regular directory.')
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        backup = backup_dir / (source.name + '.' + timestamp + '.' +
                               uuid.uuid4().hex[:8] + '.bak')
        created = False
        try:
            with backup.open('xb') as out:
                created = True
                with source.open('rb') as inp:
                    shutil.copyfileobj(inp, out, 1024 * 1024)
                out.flush()
                os.fsync(out.fileno())
            if _digest(backup) != expected_sha256:
                raise ValueError('Backup verification failed; original was not edited.')
            if _digest(source) != expected_sha256:
                raise ValueError('Source changed during backup; original was not edited.')
            # os.replace is atomic on the same filesystem. Keep original mode.
            os.chmod(edited, source.stat().st_mode)
            os.replace(edited, source)
            if _digest(source) != expected_output:
                # Best-effort rollback if storage verification fails; backup
                # remains on disk regardless of rollback outcome.
                restore = Path(tmp) / 'restore'
                shutil.copy2(backup, restore)
                os.replace(restore, source)
                raise IOError('Edited file failed disk verification; backup restored.')
            return source, backup
        except BaseException:
            if created and backup.is_file() and _digest(backup) != expected_sha256:
                backup.unlink(missing_ok=True)
            raise
