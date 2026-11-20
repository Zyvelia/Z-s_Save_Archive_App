"""v0.3 extensions. Existing v0.2 save records are not rewritten or deleted."""
from __future__ import annotations
import json, os, re, sqlite3, hashlib, tempfile, zipfile, shutil, uuid
from pathlib import Path
from .storage import Archive, now, folder_digest, CATEGORIES

COLORS={'Violet':'#aa8af3','Blue':'#62a6f5','Green':'#66c9a3','Amber':'#e6b768','Pink':'#e68bb3','Gray':'#9995a4'}

class EnhancedArchive(Archive):
    def __init__(self, root):
        super().__init__(root)
        self.conn.executescript('''
        CREATE TABLE IF NOT EXISTS tag_styles(name TEXT PRIMARY KEY COLLATE NOCASE, color TEXT NOT NULL DEFAULT 'Violet');
        CREATE TABLE IF NOT EXISTS collections(id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE);
        CREATE TABLE IF NOT EXISTS collection_games(collection_id TEXT NOT NULL, platform TEXT NOT NULL, game TEXT NOT NULL,
          PRIMARY KEY(collection_id,platform,game), FOREIGN KEY(collection_id) REFERENCES collections(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS backups(id TEXT PRIMARY KEY, save_id TEXT NOT NULL, path TEXT NOT NULL UNIQUE,
          created_at TEXT NOT NULL, zip_sha256 TEXT NOT NULL, verified INTEGER NOT NULL DEFAULT 1,
          FOREIGN KEY(save_id) REFERENCES saves(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS screenshots(id TEXT PRIMARY KEY, save_id TEXT NOT NULL, path TEXT NOT NULL,
          FOREIGN KEY(save_id) REFERENCES saves(id) ON DELETE CASCADE);
        ''')
        cols={r['name'] for r in self.conn.execute('PRAGMA table_info(saves)')}
        if 'visibility' not in cols:
            self.conn.execute("ALTER TABLE saves ADD COLUMN visibility TEXT NOT NULL DEFAULT 'Private'")
        self.conn.commit()
        self.backups_dir=self.root/'backups';self.backups_dir.mkdir(exist_ok=True)
        self.images_dir=self.root/'images';self.images_dir.mkdir(exist_ok=True)

    def set_visibility(self,save_id,visibility):
        if visibility not in ('Private','Public'): raise ValueError('Unknown visibility')
        cursor=self.conn.execute('UPDATE saves SET visibility=? WHERE id=?',(visibility,save_id))
        if not cursor.rowcount: raise ValueError('Save not found')
        self.conn.commit()

    def save_details(self, save_id, *, category,label,notes,status,tags,visibility):
        if category not in CATEGORIES or status not in ('Unverified','Verified','Needs fixes'):
            raise ValueError('Invalid category or verification status')
        if visibility not in ('Private','Public'): raise ValueError('Invalid visibility')
        self.update(save_id,category=category,label=label,notes=notes,status=status)
        self.set_tags(save_id,tags)
        self.set_visibility(save_id,visibility)

    def set_tag_color(self,name,color):
        name=' '.join(name.split())[:40]
        if not name or color not in COLORS: raise ValueError('Invalid tag name or color')
        self.conn.execute('INSERT INTO tag_styles(name,color) VALUES (?,?) ON CONFLICT(name) DO UPDATE SET color=excluded.color',(name,color))
        self.conn.commit()

    def tag_styles(self):
        styles={r['name'].casefold():r['color'] for r in self.conn.execute('SELECT name,color FROM tag_styles')}
        return [(tag,styles.get(tag.casefold(),'Violet')) for tag in self.list_tags()]

    def bulk_tag(self,ids,tags):
        clean=[]
        for t in tags:
            t=' '.join(str(t).split())[:40]
            if t and t.casefold() not in [x.casefold() for x in clean]:clean.append(t)
        if len(clean)>24:raise ValueError('Max 24 tags')
        for sid in set(ids):
            r=self.conn.execute('SELECT tags_json FROM saves WHERE id=?',(sid,)).fetchone()
            if r is None:continue
            existing=json.loads(r['tags_json'] or '[]')
            merged=existing+[t for t in clean if t.casefold() not in [x.casefold() for x in existing]]
            if len(merged)>24:raise ValueError('More than 24 tags for a save')
            self.conn.execute('UPDATE saves SET tags_json=? WHERE id=?',(json.dumps(merged),sid))
        self.conn.commit()

    def create_collection(self,name):
        name=' '.join(name.split())[:90]
        if not name:raise ValueError('Enter collection name')
        cid=uuid.uuid4().hex
        self.conn.execute('INSERT INTO collections(id,name) VALUES (?,?)',(cid,name));self.conn.commit()
        return cid

    def collections(self):
        return [dict(r) for r in self.conn.execute('SELECT * FROM collections ORDER BY name COLLATE NOCASE')]

    def add_to_collection(self,cid,platform,game):
        if not self.conn.execute('SELECT 1 FROM collections WHERE id=?',(cid,)).fetchone():raise ValueError('Collection missing')
        if not self.conn.execute('SELECT 1 FROM saves WHERE platform=? AND game=?',(platform,game)).fetchone():raise ValueError('Game not in archive')
        self.conn.execute('INSERT OR IGNORE INTO collection_games VALUES (?,?,?)',(cid,platform,game));self.conn.commit()

    def collection_games(self,cid):
        return [(r['platform'],r['game']) for r in self.conn.execute('SELECT platform,game FROM collection_games WHERE collection_id=?',(cid,))]

    def make_backup(self,save_id):
        """Create a versioned immutable backup under the managed archive."""
        sid=uuid.uuid4().hex
        target=self.backups_dir/f'{sid}.zip'
        self.backup_zip(save_id,target)
        digest=sha256_file(target)
        try:
            self.conn.execute('INSERT INTO backups VALUES (?,?,?,?,?,1)',(sid,save_id,str(target.relative_to(self.root)),now(),digest))
            self.conn.commit()
        except Exception:
            target.unlink(missing_ok=True);raise
        return target

    def backup_many(self,ids):
        results=[]
        for sid in dict.fromkeys(ids):
            try:results.append((sid,str(self.make_backup(sid)),None))
            except Exception as exc:results.append((sid,None,str(exc)))
        return results

    def backup_history(self,save_id=None):
        if save_id is None:
            return [dict(r) for r in self.conn.execute('SELECT * FROM backups ORDER BY created_at DESC')]
        return [dict(r) for r in self.conn.execute('SELECT * FROM backups WHERE save_id=? ORDER BY created_at DESC',(save_id,))]

    def verify_backup(self,bid):
        row=self.conn.execute('SELECT * FROM backups WHERE id=?',(bid,)).fetchone()
        if row is None:raise ValueError('Unknown backup')
        path=(self.root/row['path']).resolve()
        if not path.is_relative_to(self.backups_dir.resolve()):raise ValueError('Unsafe backup path')
        if not path.is_file():return False
        if sha256_file(path)!=row['zip_sha256']:return False
        try:
            with zipfile.ZipFile(path) as z:
                if z.testzip() is not None:return False
                manifest=json.loads(z.read('manifest.json'))
                if not isinstance(manifest,dict):return False
                digest,_,_=zip_save_digest(z)
                return digest==manifest.get('file_hash')
        except (OSError,ValueError,KeyError,zipfile.BadZipFile):return False

    def restore_backup(self,bid,target):
        """Extract to a NEW user-selected directory only. Never overwrite other files."""
        if not self.verify_backup(bid):raise ValueError('Backup integrity check failed')
        row=self.conn.execute('SELECT * FROM backups WHERE id=?',(bid,)).fetchone()
        target=Path(target).expanduser().resolve()
        if target.exists():raise FileExistsError('Select a new, non-existing folder to restore')
        if target==self.root or target.is_relative_to(self.root) or self.root.is_relative_to(target):
            raise ValueError('Restore destination must be separate from the archive')
        path=self.root/row['path'];target.parent.mkdir(parents=True,exist_ok=True)
        tmp=Path(tempfile.mkdtemp(prefix='.restore-',dir=target.parent))
        try:
            with zipfile.ZipFile(path) as z:
                for info in z.infolist():
                    name=info.filename
                    if not name.startswith('save/') or name.endswith('/'):continue
                    rel=Path(name).relative_to('save')
                    if rel.is_absolute() or '..' in rel.parts or not rel.parts:raise ValueError('Unsafe ZIP path')
                    # Reject Unix symlinks in untrusted archive
                    if ((info.external_attr >> 16) & 0o170000) == 0o120000:raise ValueError('Symlink in ZIP')
                    out=tmp/rel;out.parent.mkdir(parents=True,exist_ok=True)
                    with z.open(info) as src,out.open('xb') as dest:shutil.copyfileobj(src,dest)
            digest,size,count=folder_digest(tmp)
            manifest=json.loads(zipfile.ZipFile(path).read('manifest.json'))
            if (digest,size,count)!=(manifest['file_hash'],manifest['size_bytes'],manifest['file_count']):
                raise ValueError('Restored contents do not match backup manifest')
            tmp.rename(target);return target
        finally:
            if tmp.exists():shutil.rmtree(tmp,ignore_errors=True)

    def audit(self):
        issues=[]
        for r in self.list_saves():
            try:
                folder=(self.root/r['stored_path']).resolve()
                if not folder.is_relative_to(self.data_dir.resolve()):raise ValueError('Stored path outside archive')
                if folder_digest(folder)!=(r['file_hash'],r['size_bytes'],r['file_count']):raise ValueError('File contents or size changed')
            except Exception as exc:issues.append(f"{r['game']} / {r['label']}: {exc}")
        for b in self.backup_history():
            if not self.verify_backup(b['id']):issues.append(f"Backup {b['id'][:8]}: missing/corrupt")
        return issues

    def screenshot(self,save_id,path):
        path=Path(path)
        if path.is_symlink() or path.suffix.lower() not in ('.jpg','.jpeg','.png','.webp') or path.stat().st_size>12*1024*1024:
            raise ValueError('Use a PNG/JPEG/WebP image under 12 MiB')
        if not self.conn.execute('SELECT 1 FROM saves WHERE id=?',(save_id,)).fetchone():raise ValueError('Save not found')
        uid=uuid.uuid4().hex;dest=self.images_dir/(uid+path.suffix.lower())
        shutil.copy2(path,dest)
        self.conn.execute('INSERT INTO screenshots VALUES (?,?,?)',(uid,save_id,str(dest.relative_to(self.root))))
        self.conn.commit();return dest

    def screenshots(self,save_id):
        return [dict(r) for r in self.conn.execute('SELECT * FROM screenshots WHERE save_id=?',(save_id,))]

    def export_release(self,save_id,target):
        row=self.conn.execute('SELECT * FROM saves WHERE id=?',(save_id,)).fetchone()
        if row is None:raise ValueError('Save not found')
        if row['visibility']!='Public':raise ValueError('Mark save Public before release export')
        if row['status']!='Verified':raise ValueError('Verify the save before releasing')
        return self.backup_zip(save_id,target)

    def dashboard(self):
        stats=self.stats()
        storage=sum(r['size_bytes'] for r in self.conn.execute('SELECT size_bytes FROM saves'))
        return {'games':stats[0],'saves':stats[1],'verified':stats[2],'bytes':storage,'backups':len(self.backup_history())}


def sha256_file(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def zip_save_digest(z):
    """Match folder_digest: each directory's files sorted, then subdirectories sorted."""
    entries={}
    for info in z.infolist():
        if not info.filename.startswith('save/') or info.is_dir():continue
        rel=info.filename[5:]
        if (not rel or rel.startswith('/') or '\\' in rel or '..' in Path(rel).parts
            or info.file_size>512*1024*1024 or rel in entries):
            raise ValueError('Unsafe or duplicate ZIP save path')
        entries[rel]=info
    ordered=[]
    def walk(prefix):
        files=[];subdirs=set()
        for name in entries:
            if not name.startswith(prefix):continue
            suffix=name[len(prefix):]
            if '/' in suffix:subdirs.add(suffix.split('/',1)[0])
            elif suffix:files.append(name)
        ordered.extend(sorted(files))
        for folder in sorted(subdirs):walk(prefix+folder+'/')
    walk('')
    h=hashlib.sha256();total=count=0
    for rel in ordered:
        relb=rel.encode('utf-8');h.update(len(relb).to_bytes(4,'little'));h.update(relb)
        count+=1
        with z.open(entries[rel]) as f:
            for chunk in iter(lambda:f.read(1024*1024),b''):
                total+=len(chunk)
                if total>512*1024*1024:raise ValueError('Backup too large')
                h.update(chunk)
    return h.hexdigest(),total,count


def discover_pc_locations():
    """Return existing common PC save ROOTS; no invasive full-disk scan."""
    home=Path.home();candidates=[home/'Documents'/'My Games',home/'Saved Games',home/'AppData'/'LocalLow',home/'AppData'/'Roaming',home/'AppData'/'Local',home/'Documents']
    return [p for p in candidates if p.is_dir()]
