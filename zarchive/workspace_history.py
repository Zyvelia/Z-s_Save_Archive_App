"""Read conversion runs from a workspace parent, including earlier manifests."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile


def record_converter_status(workspace, status):
    workspace = Path(workspace)
    with NamedTemporaryFile(mode='w', encoding='utf-8', dir=workspace, delete=False) as file:
        temporary = Path(file.name)
        try:
            json.dump({'status': status}, file)
            file.close()
            temporary.replace(workspace / 'converter_status.json')
        finally:
            temporary.unlink(missing_ok=True)


def workspace_history(parent):
    if not parent:
        return []
    parent = Path(parent).expanduser()
    if not parent.is_dir():
        return []
    runs = []
    for folder in parent.iterdir():
        if folder.is_symlink() or getattr(folder, 'is_junction', lambda: False)() or not folder.is_dir():
            continue
        manifest = folder / 'conversion_manifest.json'
        failed = (folder / 'STAGING_FAILED.txt').is_file()
        cancelled = (folder / 'STAGING_CANCELLED.txt').is_file()
        if not (manifest.is_file() or failed or cancelled):
            continue
        metadata = {}
        if manifest.is_file():
            try:
                metadata = json.loads(manifest.read_text(encoding='utf-8'))
                if not isinstance(metadata, dict):
                    metadata = {}
            except (ValueError, OSError):
                pass
        status = 'Staged' if metadata else 'Unreadable manifest'
        if cancelled:
            status = 'Staging cancelled'
        elif failed:
            status = 'Staging failed'
        else:
            try:
                recorded = json.loads((folder / 'converter_status.json').read_text(encoding='utf-8'))
                if recorded.get('status') in ('Converter started', 'Converter finished', 'Converter failed'):
                    status = recorded['status']
            except (OSError, ValueError, AttributeError):
                pass
        size = 0
        for root, dirs, files in os.walk(folder, followlinks=False):
            dirs[:] = [name for name in dirs if not (Path(root) / name).is_symlink()
                       and not getattr(Path(root) / name, 'is_junction', lambda: False)()]
            for name in files:
                file = Path(root) / name
                try:
                    if not file.is_symlink():
                        size += file.stat().st_size
                except OSError:
                    continue
        try:
            modified = datetime.fromtimestamp(folder.stat().st_mtime, timezone.utc)
        except OSError:
            continue
        try:
            created = datetime.fromisoformat(metadata.get('created_utc', ''))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            created = modified
        runs.append({'folder': folder.resolve(), 'title': metadata.get('title') or folder.name,
                     'title_id': metadata.get('title_id') or '', 'date': created, 'bytes': size,
                     'status': status, 'can_inspect': bool(metadata) and not failed and not cancelled})
    return sorted(runs, key=lambda run: run['date'], reverse=True)
