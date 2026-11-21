"""v1.3 PC discovery and backup safety. Every write action is explicitly requested.
No console writes, cloud synchronization or background timers.
"""
from __future__ import annotations
import hashlib, json, os, re, shutil, sqlite3, tempfile, uuid
from pathlib import Path
from .upgrade_v12 import ArchiveV12
from .storage import folder_digest, now
from .integrations import steam_games, steam_libraries

DEFAULT_LOCATIONS = {
 'Stardew Valley': ['%APPDATA%/StardewValley/Saves'],
 'Terraria': ['%USERPROFILE%/Documents/My Games/Terraria/Players','%USERPROFILE%/Documents/My Games/Terraria/Worlds'],
 'Minecraft Java Edition':['%APPDATA%/.minecraft/saves'],
 'Skyrim':['%USERPROFILE%/Documents/My Games/Skyrim/Saves'],
 'Fallout 4':['%USERPROFILE%/Documents/My Games/Fallout4/Saves'],
 'The Witcher 3':['%USERPROFILE%/Documents/The Witcher 3/gamesaves'],
 'Cyberpunk 2077':['%USERPROFILE%/Saved Games/CD Projekt Red/Cyberpunk 2077'],
 'Baldurs Gate 3':['%LOCALAPPDATA%/Larian Studios/Baldur’s Gate 3/PlayerProfiles'],
 'Hollow Knight':['%USERPROFILE%/AppData/LocalLow/Team Cherry/Hollow Knight'],
 'Elden Ring':['%APPDATA%/EldenRing'],
 'Subnautica':['%USERPROFILE%/AppData/LocalLow/Unknown Worlds/Subnautica'],
 'Palworld':['%LOCALAPPDATA%/Pal/Saved/SaveGames'],
}
MAX_DEFINITIONS=5000
MAX_FOLDER_BYTES=512*1024*1024

def _sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def _safe_external_path(path,root):
    p=Path(path).expanduser().resolve(strict=True)
    if not p.is_dir() or p.is_symlink() or p==root or root in p.parents or p in root.parents:
        raise ValueError('Choose a normal directory outside the archive')
    return p

def _expand(path,env=None):
    mapping={k.upper():str(v) for k,v in (env or os.environ).items()}
    return re.sub(r'%([A-Za-z_][\w()]*)%',lambda m:mapping.get(m.group(1).upper(),m.group(0)),path)

class ArchiveV13(ArchiveV12):
    def __init__(self,root):
        super().__init__(root)
        self.conn.executescript('''
        CREATE TABLE IF NOT EXISTS custom_game_paths(id TEXT PRIMARY KEY, game TEXT NOT NULL, source TEXT NOT NULL, location TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS mirror_runs(id TEXT PRIMARY KEY, destination TEXT NOT NULL, created_at TEXT NOT NULL, sha256 TEXT NOT NULL, files INTEGER NOT NULL, bytes INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS discovery_definitions(game TEXT NOT NULL, platform TEXT NOT NULL, template TEXT NOT NULL, source TEXT NOT NULL, PRIMARY KEY(game,platform,template));
        CREATE TABLE IF NOT EXISTS discovery_events(id TEXT PRIMARY KEY, created_at TEXT NOT NULL, kind TEXT NOT NULL, message TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS discovery_events_time ON discovery_events(created_at);
        ''')
        self.conn.commit()

    def add_game_path(self,game,path,source='Custom'):
        name=' '.join(str(game).split())
        if not 1<=len(name)<=160:raise ValueError('Game name required')
        if source not in ('Custom','Steam','Epic','GOG','Xbox'):raise ValueError('Invalid source')
        p=_safe_external_path(path,self.root)
        ident=uuid.uuid4().hex
        with self.conn:self.conn.execute('INSERT INTO custom_game_paths VALUES (?,?,?,?,?)',(ident,name,source,str(p),now()))
        return ident
    def game_paths(self):
        records=[]
        for row in self.conn.execute('SELECT * FROM custom_game_paths ORDER BY game'):
            r=dict(row);r['available']=Path(r['location']).is_dir();records.append(r)
        return records
    def remove_game_path(self,ident):
        with self.conn:self.conn.execute('DELETE FROM custom_game_paths WHERE id=?',(ident,))

    def import_location_definitions(self,path):
        """Only data definitions. Never execute scripts, glob recursively, or fetch remote URLs."""
        p=Path(path)
        if p.stat().st_size>1024*1024:raise ValueError('Definition file too large')
        data=json.loads(p.read_text(encoding='utf-8'))
        if not isinstance(data,list) or len(data)>MAX_DEFINITIONS:raise ValueError('Expected at most 5000 definitions')
        clean=[]
        for entry in data:
            if not isinstance(entry,dict):raise ValueError('Invalid definition')
            game=entry.get('game');platform=entry.get('platform','PC');template=entry.get('path')
            if not isinstance(game,str) or not 1<=len(game.strip())<=160 or platform!='PC' or not isinstance(template,str) or not 1<=len(template)<=400:
                raise ValueError('Invalid definition fields')
            if any(c in template for c in ('*','?','\0')) or template.startswith(('http:','https:')) or '..' in Path(template).parts:raise ValueError('Unsafe path expression')
            clean.append((game.strip(),'PC',template,'Imported'))
        with self.conn:
            for x in clean:self.conn.execute('INSERT OR IGNORE INTO discovery_definitions VALUES (?,?,?,?)',x)
        return len(clean)

    def candidate_paths(self,env=None):
        definitions=[(game,'PC',path,'Bundled') for game,paths in DEFAULT_LOCATIONS.items() for path in paths]
        definitions+= [tuple(row) for row in self.conn.execute('SELECT game,platform,template,source FROM discovery_definitions')]
        result=[];seen=set()
        for game,platform,template,source in definitions:
            expanded=_expand(template,env)
            if '%' in expanded:continue
            path=Path(expanded).expanduser()
            if not path.is_absolute():continue
            try:resolved=path.resolve()
            except (OSError,RuntimeError):continue
            if str(resolved).casefold() in seen:continue
            seen.add(str(resolved).casefold())
            result.append({'game':game,'path':str(resolved),'source':source,'exists':resolved.is_dir() and not resolved.is_symlink()})
        return result

    def steam_installations(self):
        return {'libraries':[str(x) for x in steam_libraries()], 'games':steam_games()}

    def epic_installations(self,manifest_folder=None):
        folder=Path(manifest_folder) if manifest_folder else Path(os.environ.get('PROGRAMDATA',Path.home()))/'Epic'/'EpicGamesLauncher'/'Data'/'Manifests'
        found=[]
        if not folder.is_dir():return found
        for path in sorted(folder.glob('*.item'))[:2000]:
            if path.is_symlink() or path.stat().st_size>1024*1024:continue
            try:
                data=json.loads(path.read_text(encoding='utf-8-sig'))
                name=data.get('DisplayName');location=data.get('InstallLocation')
                if isinstance(name,str) and isinstance(location,str) and len(name)<=180:
                    found.append({'game':name,'installation':location,'source':'Epic','save_location_confirmed':False})
            except (ValueError,OSError,UnicodeError):continue
        return found

    def gog_installations(self,root=None):
        """Read-only discovery via known installation folders; never claim confirmed saves."""
        roots=[Path(root)] if root else [Path(os.environ.get('PROGRAMFILES','C:/Program Files'))/'GOG Galaxy'/'Games',Path('C:/GOG Games')]
        found=[]
        for base in roots:
            if not base.is_dir():continue
            for p in sorted(base.iterdir())[:1000]:
                if p.is_dir() and not p.is_symlink():found.append({'game':p.name,'installation':str(p),'source':'GOG (folder candidate)','save_location_confirmed':False})
        return found

    def xbox_candidates(self,env=None):
        env=env or os.environ
        base=Path(env.get('LOCALAPPDATA',str(Path.home()/'AppData'/'Local')))/'Packages'
        found=[]
        if base.is_dir():
            for p in sorted(base.iterdir())[:1500]:
                if p.is_symlink() or not p.is_dir():continue
                for child in ('SystemAppData/wgs','LocalState'):
                    q=p/child
                    if q.is_dir() and not q.is_symlink():found.append({'package':p.name,'candidate':str(q),'confirmed_save':False});break
        return found

    def verify_all_saves(self,limit=2000):
        if type(limit)!=int or not 1<=limit<=20000:raise ValueError('Invalid limit')
        results=[]
        for r in self.conn.execute('SELECT id,game,stored_path,file_hash,size_bytes,file_count FROM saves ORDER BY imported_at DESC LIMIT ?',(limit,)).fetchall():
            path=(self.root/r['stored_path']).resolve()
            try:
                if not path.is_relative_to(self.data_dir.resolve()):raise ValueError('Path outside archive')
                digest=folder_digest(path)
                valid=digest==(r['file_hash'],r['size_bytes'],r['file_count'])
                results.append({'id':r['id'],'game':r['game'],'valid':valid})
            except Exception as exc:results.append({'id':r['id'],'game':r['game'],'valid':False,'error':str(exc)[:150]})
        return results

    def mirror_archive(self,destination):
        """Verified full snapshot to an empty destination, no overwrites, no symlinks.
        Copies database using SQLite online backup to avoid inconsistent WAL state.
        """
        dest=Path(destination).expanduser().absolute()
        if dest.exists():raise FileExistsError('Choose a new destination folder')
        parent=dest.parent.resolve(strict=True)
        if parent==self.root or parent.is_relative_to(self.root) or self.root.is_relative_to(parent):raise ValueError('Mirror must live outside archive')
        stage=parent/('.zmirror-'+uuid.uuid4().hex)
        files=0;total=0;items=[]
        stage.mkdir()
        try:
            for root,dirs,names in os.walk(self.root,followlinks=False):
                base=Path(root);dirs[:]=[d for d in dirs if not (base/d).is_symlink()]
                for name in names:
                    src=base/name
                    if src.is_symlink() or not src.is_file():raise ValueError('Unsupported archive file')
                    rel=src.relative_to(self.root)
                    if rel.as_posix() in ('archive.sqlite3','archive.sqlite3-wal','archive.sqlite3-shm'):continue
                    target=stage/rel;target.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(src,target);digest=_sha(src)
                    if _sha(target)!=digest:raise IOError('Mirror integrity mismatch')
                    items.append({'path':rel.as_posix(),'sha256':digest,'bytes':target.stat().st_size});total+=target.stat().st_size;files+=1
                    if files>100000:raise ValueError('Too many archive files')
            db=stage/'archive.sqlite3'
            with sqlite3.connect(db) as backup:self.conn.backup(backup)
            dbsha=_sha(db);items.append({'path':'archive.sqlite3','sha256':dbsha,'bytes':db.stat().st_size})
            total+=db.stat().st_size;files+=1
            manifest=json.dumps({'format':'zsave-mirror-v1','created_at':now(),'files':items},indent=2)
            (stage/'MIRROR_MANIFEST.json').write_text(manifest,encoding='utf-8')
            stage.rename(dest)
            with self.conn:self.conn.execute('INSERT INTO mirror_runs VALUES (?,?,?,?,?,?)',(uuid.uuid4().hex,str(dest),now(),hashlib.sha256(manifest.encode()).hexdigest(),files,total))
            return {'destination':str(dest),'files':files,'bytes':total}
        except Exception:
            shutil.rmtree(stage,ignore_errors=True);raise

    @staticmethod
    def verify_mirror(destination):
        root=Path(destination).resolve(strict=True)
        manifest=json.loads((root/'MIRROR_MANIFEST.json').read_text(encoding='utf-8'))
        if manifest.get('format')!='zsave-mirror-v1':raise ValueError('Unknown mirror manifest')
        issues=[]
        if len(manifest.get('files',[]))>100000:raise ValueError('Manifest too large')
        for item in manifest['files']:
            rel=Path(item['path'])
            if rel.is_absolute() or '..' in rel.parts:raise ValueError('Unsafe manifest path')
            p=root/rel
            if not p.resolve().is_relative_to(root) or p.is_symlink() or not p.is_file() or _sha(p)!=item['sha256']:issues.append(item['path'])
        return {'verified':not issues,'problems':issues}

    def smart_save_name(self,save_id):
        """Suggest a label only; never rename archived data."""
        row=self._save(save_id)
        label=' - '.join((row['game'],row['platform'],row['category'],row['imported_at'][:10]))
        return ''.join('_' if c in '/\\:*?"<>|' or ord(c)<32 else c for c in label)[:180]

    def save_timeline(self,game=None,limit=200):
        if type(limit)!=int or not 1<=limit<=1000:raise ValueError('Invalid limit')
        if game is None:
            rows=self.conn.execute('SELECT id,game,platform,label,category,imported_at FROM saves ORDER BY imported_at DESC LIMIT ?',(limit,)).fetchall()
        else:
            rows=self.conn.execute('SELECT id,game,platform,label,category,imported_at FROM saves WHERE game=? ORDER BY imported_at DESC LIMIT ?',(game,limit)).fetchall()
        return [dict(row) for row in rows]

    def duplicate_candidates(self,limit=100):
        """Report identical hashes, not speculative near-duplicates."""
        if type(limit)!=int or not 1<=limit<=1000:raise ValueError('Invalid limit')
        rows=self.conn.execute('SELECT file_hash,COUNT(*) AS count,GROUP_CONCAT(id) AS save_ids FROM saves GROUP BY file_hash HAVING COUNT(*)>1 ORDER BY count DESC LIMIT ?',(limit,)).fetchall()
        return [dict(row) for row in rows]

    def universal_search(self,query,limit=100):
        if not isinstance(query,str) or not 1<=len(query.strip())<=160:raise ValueError('Search query required')
        if type(limit)!=int or not 1<=limit<=500:raise ValueError('Invalid limit')
        q='%'+query.strip().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
        sql="SELECT id,platform,game,title_id,label,category,status,imported_at FROM saves WHERE game LIKE ? ESCAPE '\\' OR title_id LIKE ? ESCAPE '\\' OR label LIKE ? ESCAPE '\\' OR notes LIKE ? ESCAPE '\\' OR tags_json LIKE ? ESCAPE '\\' ORDER BY imported_at DESC LIMIT ?"
        return [dict(r) for r in self.conn.execute(sql,(q,q,q,q,q,limit)).fetchall()]

    def archive_health(self):
        checks=self.conn.execute('PRAGMA quick_check').fetchone()[0]
        return {'sqlite_ok':checks=='ok','sqlite_result':checks,'archive_path':str(self.root),'mirror_history':[dict(r) for r in self.conn.execute('SELECT * FROM mirror_runs ORDER BY created_at DESC LIMIT 10')]}

    def notification(self,kind,message):
        if kind not in ('info','success','warning','error'):raise ValueError('Invalid notification')
        with self.conn:self.conn.execute('INSERT INTO discovery_events VALUES (?,?,?,?)',(uuid.uuid4().hex,now(),kind,str(message)[:500]))
    def notifications(self,limit=100):
        if not 1<=limit<=500:raise ValueError('Invalid limit')
        return [dict(r) for r in self.conn.execute('SELECT * FROM discovery_events ORDER BY created_at DESC LIMIT ?',(limit,))]
