"""Local, immutable PS3 save ingestion and indexed metadata."""
from __future__ import annotations
import hashlib
import json
import zipfile
import os
import re
import shutil
import sqlite3
import stat
import struct
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

MAX_IMPORT_BYTES = 512 * 1024 * 1024
CATEGORIES = ('Legit', 'Modded', 'Unsorted')
DEFAULT_TAGS = ('Starter Save','Mid-Game','Endgame','100% Complete','New Game+','All Unlocks','All Characters','All Skills','All Weapons','All Cosmetics','Max Money','Max Level','Max XP','Unlimited Resources','Legendary Gear','Rare Items','Modded Weapons','Perfect Build','Hardcore','No Deaths','Speedrun','Challenge Run','Backup','Tested','Untested','PS4','PS4 USB Backup','PS4 FTP Backup')
ORIGIN_KINDS = ('Unknown','My own save','Friend / shared privately','Community upload','Website / download','PS3 console backup','PC / local game','Other','PS4 console backup')
TITLE_ID = re.compile(r'^[A-Z]{4}[0-9]{5}$')
SAVE_ID = re.compile(r'[a-f0-9]{32}')


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def read_param_sfo(path: Path) -> dict[str, str]:
    """Read string/integer values from standard PSF/SFO; reject corrupt offsets."""
    return parse_param_sfo(Path(path).read_bytes())


def parse_param_sfo(data: bytes) -> dict[str, str]:
    if len(data) < 20 or data[:4] != b'\x00PSF':
        raise ValueError('Not a valid PARAM.SFO (PSF signature missing)')
    _, version, key_offset, value_offset, count = struct.unpack_from('<4sIIII', data, 0)
    if version not in (0x101, 0x100) or count > 4096 or 20 + 16 * count > len(data):
        raise ValueError('Invalid PARAM.SFO header or entry count')
    if key_offset >= len(data) or value_offset >= len(data):
        raise ValueError('Invalid PARAM.SFO table offset')
    result: dict[str, str] = {}
    for i in range(count):
        key_rel, fmt, size, capacity, value_rel = struct.unpack_from('<HHIII', data, 20 + 16*i)
        kstart = key_offset + key_rel
        if kstart >= len(data):
            raise ValueError('Invalid PARAM.SFO key offset')
        kend = data.find(b'\0', kstart)
        if kend == -1 or kend - kstart > 256:
            raise ValueError('Invalid PARAM.SFO key')
        key = data[kstart:kend].decode('ascii', errors='replace')
        start = value_offset + value_rel
        if size > capacity or start > len(data) or size > len(data) - start:
            raise ValueError('Invalid PARAM.SFO value size')
        raw = data[start:start + size]
        if fmt == 0x0404 and len(raw) >= 4:
            result[key] = str(struct.unpack_from('<I', raw)[0])
        else:
            result[key] = raw.rstrip(b'\0').decode('utf-8', errors='replace')
    return result


def discover_saves(folder: Path) -> list[Path]:
    """Find SFO-containing directories, but do not traverse symlinked folders."""
    folder = Path(folder)
    if not folder.is_dir() or folder.is_symlink():
        raise ValueError('Choose a real existing directory')
    found = []
    for root, dirs, files in os.walk(folder, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(root) / d).is_symlink()]
        if 'PARAM.SFO' in files:
            found.append(Path(root))
            dirs.clear()  # never treat nested resources as separate saves
        if len(found) > 2000:
            raise ValueError('Too many save folders in a single scan (limit 2000)')
    return found


def folder_digest(folder: Path) -> tuple[str, int, int]:
    h = hashlib.sha256()
    total = count = 0
    for root, dirs, files in os.walk(folder, followlinks=False):
        dirs.sort()
        files.sort()
        for d in dirs:
            if (Path(root) / d).is_symlink():
                raise ValueError('Save contains a symlinked directory')
        for name in files:
            f = Path(root) / name
            if f.is_symlink() or not f.is_file():
                raise ValueError('Save contains an unsupported special file')
            rel = f.relative_to(folder).as_posix().encode('utf-8')
            h.update(len(rel).to_bytes(4, 'little'))
            h.update(rel)
            count += 1
            with f.open('rb') as stream:
                while chunk := stream.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_IMPORT_BYTES:
                        raise ValueError('Save is over the 512 MiB per-import limit')
                    h.update(chunk)
    return h.hexdigest(), total, count


class Archive:
    def __init__(self, root: Path):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.data_dir = self.root / 'objects'
        self.data_dir.mkdir(exist_ok=True)
        self.conn = sqlite3.connect(self.root / 'archive.sqlite3')
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA foreign_keys=ON')
        self.conn.execute('PRAGMA journal_mode=WAL')
        self.conn.executescript('''
          CREATE TABLE IF NOT EXISTS saves (
            id TEXT PRIMARY KEY, game TEXT NOT NULL, title_id TEXT NOT NULL,
            category TEXT NOT NULL, label TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
            region TEXT NOT NULL DEFAULT 'Unknown', status TEXT NOT NULL DEFAULT 'Unverified',
            file_hash TEXT NOT NULL, size_bytes INTEGER NOT NULL,
            file_count INTEGER NOT NULL, source_folder TEXT NOT NULL,
            stored_path TEXT NOT NULL UNIQUE, metadata_json TEXT NOT NULL,
            imported_at TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS saves_game ON saves(game);
          CREATE INDEX IF NOT EXISTS saves_hash ON saves(file_hash);
        ''')
        cols = {r['name'] for r in self.conn.execute('PRAGMA table_info(saves)')}
        if 'platform' not in cols:
            self.conn.execute("ALTER TABLE saves ADD COLUMN platform TEXT NOT NULL DEFAULT 'PS3'")
        if 'tags_json' not in cols:
            self.conn.execute("ALTER TABLE saves ADD COLUMN tags_json TEXT NOT NULL DEFAULT '[]'")
        for col in ('origin_kind','origin_name','origin_url','origin_notes'):
            if col not in cols:
                self.conn.execute(f"ALTER TABLE saves ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")
        if 'removed_at' not in cols:
            self.conn.execute('ALTER TABLE saves ADD COLUMN removed_at TEXT')
        self.conn.execute('CREATE TEMP VIEW IF NOT EXISTS active_saves AS SELECT * FROM saves WHERE removed_at IS NULL')
        self.conn.commit()
        self._recover_interrupted_removals()

    @staticmethod
    def _managed_directory_exists(path):
        try:
            info = path.lstat()
        except FileNotFoundError:
            return False
        if not stat.S_ISDIR(info.st_mode) or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError(f'Expected a real archive directory: {path}')
        return True

    def _recover_interrupted_removals(self):
        try:
            if not self._managed_directory_exists(self.data_dir):
                return
        except ValueError:
            return
        staged = list(self.data_dir.glob('.removing-*'))
        if not staged:
            return
        with self.conn:
            self.conn.execute('BEGIN IMMEDIATE')
            for folder in staged:
                record_id = folder.name.removeprefix('.removing-')
                if not SAVE_ID.fullmatch(record_id):
                    continue
                original = self.data_dir / record_id
                row = self.conn.execute('SELECT stored_path FROM saves WHERE id=?', (record_id,)).fetchone()
                if (row and Path(row['stored_path']) == original.relative_to(self.root)
                        and not self._managed_directory_exists(original) and self._managed_directory_exists(folder)):
                    folder.rename(original)

    def _delete_save_record(self, record_id):
        self.conn.execute('DELETE FROM saves WHERE id=?', (record_id,))

    def remove_saves(self, record_ids, *, only_removed=False):
        """Remove indexed saves and their managed copies, returning any files left to clean up."""
        if not self._managed_directory_exists(self.data_dir):
            raise ValueError('Archive objects directory is missing.')
        removed = 0
        staged = []
        self.conn.execute('BEGIN IMMEDIATE')
        try:
            for record_id in dict.fromkeys(record_ids):
                if not SAVE_ID.fullmatch(record_id):
                    raise ValueError('Invalid save ID.')
                row = self.conn.execute('SELECT stored_path, removed_at FROM saves WHERE id=?', (record_id,)).fetchone()
                if row is None or (only_removed and row['removed_at'] is None):
                    continue
                original = self.data_dir / record_id
                if Path(row['stored_path']) != original.relative_to(self.root):
                    raise ValueError(f'Unexpected archived path for save {record_id}.')
                pending = self.data_dir / ('.removing-' + record_id)
                if self._managed_directory_exists(pending):
                    raise ValueError(f'An interrupted removal needs recovery. Reopen the archive. {pending}')
                if self._managed_directory_exists(original):
                    original.rename(pending)
                    staged.append((original, pending))
                self._delete_save_record(record_id)
                removed += 1
            self.conn.commit()
        except BaseException:
            try:
                for original, pending in reversed(staged):
                    try:
                        pending.rename(original)
                    except OSError:
                        # The record remains indexed; reopening the archive retries the move.
                        continue
            finally:
                self.conn.rollback()
            raise

        remaining = []
        for _, pending in staged:
            try:
                shutil.rmtree(pending)
            except OSError:
                remaining.append(pending)
        return removed, remaining

    def trash_saves(self, record_ids):
        """Hide saves while keeping the archived files and linked records available for undo."""
        removed_at = now()
        with self.conn:
            updated = self.conn.executemany(
                'UPDATE saves SET removed_at=? WHERE id=? AND removed_at IS NULL',
                ((removed_at, record_id) for record_id in dict.fromkeys(record_ids)),
            )
        return updated.rowcount

    def list_removed_saves(self):
        return [dict(row) for row in self.conn.execute(
            """SELECT id, game, platform, label, size_bytes, removed_at FROM saves
               WHERE removed_at IS NOT NULL ORDER BY removed_at DESC, game COLLATE NOCASE, id""")]

    def restore_removed_saves(self, record_ids):
        restored = 0
        with self.conn:
            self.conn.execute('BEGIN IMMEDIATE')
            for record_id in dict.fromkeys(record_ids):
                row = self.conn.execute(
                    'SELECT * FROM saves WHERE id=? AND removed_at IS NOT NULL', (record_id,)
                ).fetchone()
                if row is None:
                    continue
                stored = self.data_dir / record_id
                if (not SAVE_ID.fullmatch(record_id) or Path(row['stored_path']) != stored.relative_to(self.root)
                        or not self._managed_directory_exists(stored)):
                    raise ValueError(f"Archived files are unavailable for {row['game']} — {row['label']}.")
                duplicate = self.conn.execute(
                    'SELECT 1 FROM active_saves WHERE platform=? AND file_hash=?',
                    (row['platform'], row['file_hash']),
                ).fetchone()
                if duplicate:
                    raise ValueError(f"An identical active save already exists for {row['game']} — {row['label']}.")
                self.conn.execute('UPDATE saves SET removed_at=NULL WHERE id=?', (record_id,))
                restored += 1
        return restored

    def set_origin(self, record_id: str, *, kind: str, name: str = '', url: str = '', notes: str = '') -> None:
        """Record human-entered provenance; never claim authenticity from this field."""
        from urllib.parse import urlsplit
        if kind not in ORIGIN_KINDS: raise ValueError('Invalid origin type')
        name = str(name).strip()
        url = str(url).strip()
        notes = str(notes).strip()
        if len(name) > 200 or len(url) > 2048 or len(notes) > 1500:
            raise ValueError('Origin information is too long')
        if url:
            parts = urlsplit(url)
            if parts.scheme not in ('https','http') or not parts.hostname or parts.username or parts.password:
                raise ValueError('Enter an HTTP(S) source link without credentials')
        with self.conn:
            cur = self.conn.execute('UPDATE saves SET origin_kind=?, origin_name=?, origin_url=?, origin_notes=? WHERE id=? AND removed_at IS NULL', (kind, name, url, notes, record_id))
            if cur.rowcount != 1: raise ValueError('Save not found')

    def import_save(self, folder: Path, category: str = 'Unsorted', label: str = '', notes: str = '') -> dict:
        if category not in CATEGORIES:
            raise ValueError('Invalid save category')
        folder = Path(folder).expanduser().resolve(strict=True)
        if not folder.is_dir() or not (folder / 'PARAM.SFO').is_file():
            raise ValueError('Select a PS3 save folder containing PARAM.SFO')
        if folder == self.root or self.root in folder.parents:
            raise ValueError('Do not re-import files from the managed archive')
        meta = read_param_sfo(folder / 'PARAM.SFO')
        title_id = meta.get('TITLE_ID', '').strip().upper()
        if not TITLE_ID.fullmatch(title_id):
            # Some games use save-specific ids; preserve actual SFO id if unrecognized
            title_id = title_id[:40] or 'UNKNOWN'
        game = (meta.get('TITLE') or folder.name).strip()[:160]
        region = ('USA' if title_id.startswith(('BLUS', 'NPUB')) else
                  'Europe' if title_id.startswith(('BLES','BCES','NPEB')) else
                  'Japan' if title_id.startswith(('BLJM','BLJS','NPJB')) else 'Unknown')
        checksum, size, files = folder_digest(folder)
        if self.conn.execute('SELECT 1 FROM active_saves WHERE file_hash=?', (checksum,)).fetchone():
            raise ValueError('Identical save already exists in archive (SHA-256 duplicate)')
        record_id = uuid.uuid4().hex
        dest = self.data_dir / record_id
        stage = Path(tempfile.mkdtemp(prefix='.import-', dir=self.root))
        try:
            # dirs_exist_ok=False; do not allow symlinks, even if metadata passed earlier
            shutil.copytree(folder, stage / 'save', symlinks=False)
            copied_hash, copied_size, copied_files = folder_digest(stage / 'save')
            if (copied_hash, copied_size, copied_files) != (checksum, size, files):
                raise ValueError('Source changed during import; no files were registered')
            (stage / 'save').rename(dest)
            row = dict(id=record_id, game=game, title_id=title_id, category=category,
                       label=(label.strip() or meta.get('SUB_TITLE') or 'Imported save')[:150],
                       notes=notes[:5000], region=region, status='Unverified', file_hash=checksum,
                       size_bytes=size, file_count=files, source_folder=folder.name,
                       stored_path=str(dest.relative_to(self.root)),
                       metadata_json=json.dumps(meta), imported_at=now())
            try:
                self.conn.execute('''INSERT INTO saves (id,game,title_id,category,label,notes,region,status,
                         file_hash,size_bytes,file_count,source_folder,stored_path,metadata_json,imported_at)
                         VALUES (:id,:game,:title_id,:category,:label,:notes,:region,:status,
                         :file_hash,:size_bytes,:file_count,:source_folder,:stored_path,:metadata_json,:imported_at)''',row)
                self.conn.commit()
            except Exception:
                shutil.rmtree(dest, ignore_errors=True)
                raise
            return row
        finally:
            shutil.rmtree(stage, ignore_errors=True)

    def import_pc_save(self, source: Path, game: str, category: str = 'Unsorted', label: str = '', notes: str = '') -> dict:
        return self._import_local_save(source, game, 'PC', category, label, notes)

    def import_ps4_save(self, source: Path, game: str, category: str = 'Unsorted', label: str = '', notes: str = '') -> dict:
        return self._import_local_save(source, game, 'PS4', category, label, notes)

    def _import_local_save(self, source, game, platform, category, label, notes):
        if category not in CATEGORIES:
            raise ValueError('Invalid category')
        game = game.strip()[:160]
        if not game or any(c in game for c in chr(10)+chr(13)+chr(9)):
            raise ValueError('Enter a valid game name')
        original = Path(source).expanduser()
        if original.is_symlink():
            raise ValueError('Symlink source not supported')
        source = original.resolve(strict=True)
        if not (source.is_file() or source.is_dir()):
            raise ValueError('Select a file or directory')
        if source == self.root or self.root in source.parents:
            raise ValueError('Cannot import from the managed archive')
        stage = Path(tempfile.mkdtemp(prefix=f'.{platform.lower()}-import-', dir=self.root))
        try:
            copied = stage/'save'
            if source.is_dir():
                folder_digest(source)
                shutil.copytree(source,copied,symlinks=False)
            else:
                if source.stat().st_size > MAX_IMPORT_BYTES:
                    raise ValueError('Source exceeds 512 MiB limit')
                copied.mkdir()
                shutil.copy2(source,copied/source.name)
            checksum,size,files = folder_digest(copied)
            if source.is_dir() and (checksum,size,files) != folder_digest(source):
                raise ValueError('Source changed during import')
            if self.conn.execute('SELECT 1 FROM active_saves WHERE file_hash=? AND platform=?',(checksum,platform)).fetchone():
                raise ValueError(f'Identical {platform} save already exists (SHA-256 duplicate)')
            record_id = uuid.uuid4().hex
            dest = self.data_dir/record_id
            copied.rename(dest)
            title = next((part.upper() for part in (source.name, *(p.name for p in source.parents))
                          if re.fullmatch(r'CUSA[0-9]{5}', part, re.I)), platform) if platform == 'PS4' else platform
            row = dict(id=record_id,game=game,title_id=title,category=category,
                label=(label.strip() or source.name)[:150],notes=notes[:5000],region=platform,
                status='Unverified',file_hash=checksum,size_bytes=size,file_count=files,
                source_folder=source.name,stored_path=str(dest.relative_to(self.root)),
                metadata_json='{}',imported_at=now(),platform=platform,tags_json=json.dumps(['PS4'] if platform == 'PS4' else []))
            try:
                self.conn.execute("""INSERT INTO saves (id,game,title_id,category,label,notes,region,status,
                    file_hash,size_bytes,file_count,source_folder,stored_path,metadata_json,imported_at,platform,tags_json)
                    VALUES (:id,:game,:title_id,:category,:label,:notes,:region,:status,
                    :file_hash,:size_bytes,:file_count,:source_folder,:stored_path,:metadata_json,:imported_at,:platform,:tags_json)""",row)
                self.conn.commit()
            except Exception:
                shutil.rmtree(dest,ignore_errors=True)
                raise
            return row
        finally:
            shutil.rmtree(stage,ignore_errors=True)

    def set_tags(self, record_id: str, tags: list[str]):
        clean=[]
        for tag in tags:
            t=' '.join(str(tag).split())[:40]
            if t and t.casefold() not in {v.casefold() for v in clean}:
                clean.append(t)
        if len(clean)>24:
            raise ValueError('Maximum 24 tags per save')
        self.conn.execute('UPDATE saves SET tags_json=? WHERE id=? AND removed_at IS NULL',(json.dumps(clean,ensure_ascii=False),record_id))
        self.conn.commit()

    def list_tags(self):
        tags={t.casefold():t for t in DEFAULT_TAGS}
        for row in self.conn.execute('SELECT tags_json FROM active_saves'):
            for t in json.loads(row['tags_json'] or '[]'):
                tags.setdefault(t.casefold(),t)
        return sorted(tags.values(),key=str.casefold)

    def backup_zip(self,record_id: str,target: Path) -> Path:
        row=self.conn.execute('SELECT * FROM active_saves WHERE id=?',(record_id,)).fetchone()
        if row is None:
            raise ValueError('Save not found')
        folder=(self.root/row['stored_path']).resolve()
        if not folder.is_relative_to(self.data_dir.resolve()):
            raise ValueError('Unsafe archived path')
        if folder_digest(folder)!=(row['file_hash'],row['size_bytes'],row['file_count']):
            raise ValueError('Archived files changed: backup cancelled')
        target=Path(target).expanduser().resolve()
        if target.suffix.lower()!='.zip':
            raise ValueError('Backup must be a .zip file')
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():
            raise FileExistsError('Backup exists; choose a new filename')
        manifest={k:row[k] for k in ('platform','game','title_id','category','label','notes','region','status','file_hash','size_bytes','file_count','source_folder','imported_at')}
        manifest['tags']=json.loads(row['tags_json'] or '[]')
        manifest['origin']={k: row[k] for k in ('origin_kind','origin_name','origin_url','origin_notes')}
        manifest['created_at']=now()
        fd,tmp=tempfile.mkstemp(prefix='.backup-',suffix='.zip',dir=target.parent)
        os.close(fd)
        try:
            with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
                z.writestr('manifest.json',json.dumps(manifest,indent=2,ensure_ascii=False))
                z.writestr('README.txt',"Z Save Archive Backup\nOriginal save files are in save/.\nUse your game's normal restore procedure.\n")
                for f in sorted(folder.rglob('*')):
                    if f.is_file():
                        z.write(f,'save/'+f.relative_to(folder).as_posix())
            with zipfile.ZipFile(tmp) as z:
                if z.testzip() is not None:
                    raise ValueError('ZIP integrity verification failed')
            os.replace(tmp,target)
            return target
        finally:
            if os.path.exists(tmp): os.unlink(tmp)

    def list_saves(self,query: str='',category: str='All',platform: str='All',tag: str='All') -> list[dict]:
        q=f'%{query.strip()}%'
        rows=[dict(r) for r in self.conn.execute("""SELECT * FROM active_saves WHERE
            (game LIKE ? OR title_id LIKE ? OR label LIKE ? OR notes LIKE ? OR tags_json LIKE ? OR origin_kind LIKE ? OR origin_name LIKE ? OR origin_url LIKE ?)
            AND (?='All' OR category=?) AND (?='All' OR platform=?)
            ORDER BY imported_at DESC,game COLLATE NOCASE""",(q,q,q,q,q,q,q,q,category,category,platform,platform))]
        for r in rows:
            r['tags']=json.loads(r['tags_json'] or '[]')
        return [r for r in rows if tag=='All' or tag in r['tags']]

    def games(self,query: str='',platform: str='All') -> list[dict]:
        q=f'%{query.strip()}%'
        return [dict(r) for r in self.conn.execute("""SELECT game,title_id,region,platform,COUNT(*) AS saves,
            SUM(size_bytes) AS bytes,MAX(imported_at) AS updated FROM active_saves
            WHERE (game LIKE ? OR title_id LIKE ?) AND (?='All' OR platform=?)
            GROUP BY game,title_id,region,platform ORDER BY game COLLATE NOCASE""",(q,q,platform,platform))]

    def update(self, record_id: str, *, category: str, label: str, notes: str, status: str) -> None:
        if category not in CATEGORIES or status not in ('Unverified','Verified','Needs fixes'):
            raise ValueError('Unsupported category or test status')
        self.conn.execute('UPDATE saves SET category=?,label=?,notes=?,status=? WHERE id=? AND removed_at IS NULL',
                          (category,label.strip()[:150],notes[:5000],status,record_id))
        self.conn.commit()

    def stats(self) -> tuple[int,int,int]:
        row = self.conn.execute('SELECT COUNT(*),COUNT(DISTINCT game || title_id),SUM(status="Verified") FROM active_saves').fetchone()
        return row[1],row[0],row[2] or 0

    def close(self):
        self.conn.close()
