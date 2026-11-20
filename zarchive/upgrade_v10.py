"""v1.0 additive archive tools. Read-only analyses and safe, explicit exports.
No PS3 writes, no binary save editing, no automatic Steam Cloud changes.
"""
from __future__ import annotations
import html, json, os, re, shutil, socket, sqlite3, tempfile, uuid, hashlib, ftplib
from pathlib import Path
from datetime import datetime, timezone
from .library_v05 import LibraryArchive
from .storage import folder_digest
from .enhanced import sha256_file


def _utc(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def _valid_name(v,limit=90):
    v=' '.join(str(v).split())[:limit]
    if not v or any(ord(c)<32 for c in v): raise ValueError('Name is required')
    return v

class ArchiveV10(LibraryArchive):
    def __init__(self,root):
        super().__init__(root)
        self.conn.executescript('''
          CREATE TABLE IF NOT EXISTS save_profiles(id TEXT PRIMARY KEY, platform TEXT NOT NULL, game TEXT NOT NULL, name TEXT NOT NULL, UNIQUE(platform,game,name));
          CREATE TABLE IF NOT EXISTS save_profile_links(save_id TEXT PRIMARY KEY REFERENCES saves(id) ON DELETE CASCADE, profile_id TEXT REFERENCES save_profiles(id) ON DELETE SET NULL);
          CREATE TABLE IF NOT EXISTS pinned_games(platform TEXT NOT NULL, game TEXT NOT NULL, PRIMARY KEY(platform,game));
          CREATE TABLE IF NOT EXISTS pinned_saves(save_id TEXT PRIMARY KEY REFERENCES saves(id) ON DELETE CASCADE);
          CREATE TABLE IF NOT EXISTS console_profiles(id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, host TEXT NOT NULL, port INTEGER NOT NULL);
          CREATE TABLE IF NOT EXISTS recovery_events(id TEXT PRIMARY KEY, happened_at TEXT NOT NULL, operation TEXT NOT NULL, target TEXT NOT NULL, error TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS idx_v10_profile_game ON save_profiles(platform,game);
        ''')
        self.conn.commit()

    def create_profile(self,platform,game,name):
        if platform not in ('PS3','PC'):raise ValueError('Unknown platform')
        name=_valid_name(name)
        if not self.conn.execute('SELECT 1 FROM saves WHERE platform=? AND game=?',(platform,game)).fetchone():
            raise ValueError('Game not in archive')
        pid=uuid.uuid4().hex
        self.conn.execute('INSERT INTO save_profiles VALUES (?,?,?,?)',(pid,platform,game,name));self.conn.commit()
        return pid
    def profiles(self,platform=None,game=None):
        query='SELECT * FROM save_profiles WHERE 1=1';args=[]
        if platform:query+=' AND platform=?';args.append(platform)
        if game:query+=' AND game=?';args.append(game)
        return [dict(r) for r in self.conn.execute(query+' ORDER BY name COLLATE NOCASE',args)]
    def assign_profile(self,save_id,profile_id):
        row=self.conn.execute('SELECT platform,game FROM saves WHERE id=?',(save_id,)).fetchone()
        if row is None:raise ValueError('Save not found')
        if profile_id is not None:
            profile=self.conn.execute('SELECT * FROM save_profiles WHERE id=?',(profile_id,)).fetchone()
            if profile is None or (profile['platform'],profile['game'])!=(row['platform'],row['game']):
                raise ValueError('Profile must belong to the same game and platform')
        self.conn.execute('INSERT INTO save_profile_links VALUES (?,?) ON CONFLICT(save_id) DO UPDATE SET profile_id=excluded.profile_id',(save_id,profile_id))
        self.conn.commit()
    def profile_for(self,save_id):
        row=self.conn.execute('SELECT p.* FROM save_profiles p JOIN save_profile_links l ON l.profile_id=p.id WHERE l.save_id=?',(save_id,)).fetchone()
        return dict(row) if row else None
    def pin_save(self,save_id,pin=True):
        if not self.conn.execute('SELECT 1 FROM saves WHERE id=?',(save_id,)).fetchone():raise ValueError('Save not found')
        if pin:self.conn.execute('INSERT OR IGNORE INTO pinned_saves VALUES (?)',(save_id,))
        else:self.conn.execute('DELETE FROM pinned_saves WHERE save_id=?',(save_id,))
        self.conn.commit()
    def pin_game(self,platform,game,pin=True):
        if not self.conn.execute('SELECT 1 FROM saves WHERE platform=? AND game=?',(platform,game)).fetchone():raise ValueError('Game not found')
        if pin:self.conn.execute('INSERT OR IGNORE INTO pinned_games VALUES (?,?)',(platform,game))
        else:self.conn.execute('DELETE FROM pinned_games WHERE platform=? AND game=?',(platform,game))
        self.conn.commit()
    def pinned(self):
        return {'saves':[dict(r) for r in self.conn.execute('SELECT s.* FROM saves s JOIN pinned_saves p ON p.save_id=s.id ORDER BY s.imported_at DESC')],
                'games':[dict(r) for r in self.conn.execute('SELECT * FROM pinned_games ORDER BY game COLLATE NOCASE')]}
    def log_recovery(self,operation,target,error):
        self.conn.execute('INSERT INTO recovery_events VALUES (?,?,?,?,?)',(uuid.uuid4().hex,_utc(),_valid_name(operation),str(target)[:300],str(error)[:1000]))
        self.conn.commit()
    def recovery(self):
        events=[dict(r) for r in self.conn.execute('SELECT * FROM recovery_events ORDER BY happened_at DESC LIMIT 250')]
        try:issues=self.audit()
        except Exception as exc:issues=['Audit could not complete: '+str(exc)]
        return {'events':events,'archive_issues':issues}
    def recovery_backup(self,save_id):
        try:return self.make_backup(save_id)
        except Exception as exc:self.log_recovery('backup',save_id,exc);raise
    def recovery_restore(self,backup_id,target):
        try:return self.restore_backup(backup_id,target)
        except Exception as exc:self.log_recovery('restore',backup_id,exc);raise
    def external_backup(self,destination,ids=None):
        """Explicit destination; copy verified ZIPs only. No archive overwrite or deletes."""
        target=Path(destination).expanduser().resolve()
        if target==self.root or target.is_relative_to(self.root) or self.root.is_relative_to(target):
            raise ValueError('External destination must be separate from archive')
        if not target.exists() or not target.is_dir():raise ValueError('Choose an existing external destination folder')
        chosen=list(dict.fromkeys(ids if ids is not None else [r['id'] for r in self.list_saves()]))
        if len(chosen)>10000:raise ValueError('Too many saves')
        batch=target/('Z_Save_Archive_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6]);batch.mkdir()
        results=[]
        for sid in chosen:
            try:
                out=batch/(sid+'.zip');self.backup_zip(sid,out)
                results.append({'id':sid,'filename':out.name,'sha256':sha256_file(out),'status':'ok'})
            except Exception as exc:
                results.append({'id':sid,'status':'failed','error':str(exc)[:250]})
                self.log_recovery('external backup',sid,exc)
        (batch/'export_manifest.json').write_text(json.dumps({'created_at':_utc(),'items':results},indent=2),encoding='utf8')
        return batch,results
    def connection_add(self,name,host,port=21):
        from .transfer_v06 import PS3FTP
        host=PS3FTP(host,port=int(port)).host
        if not 1<=int(port)<=65535:raise ValueError('Invalid port')
        name=_valid_name(name)
        pid=uuid.uuid4().hex
        self.conn.execute('INSERT INTO console_profiles VALUES (?,?,?,?)',(pid,name,host,int(port)));self.conn.commit();return pid
    def connections(self):return [dict(r) for r in self.conn.execute('SELECT * FROM console_profiles ORDER BY name')]
    def connection_test(self,profile_id,timeout=4):
        row=self.conn.execute('SELECT * FROM console_profiles WHERE id=?',(profile_id,)).fetchone()
        if row is None:raise ValueError('Unknown console')
        # Test only port reachability, never send credentials or write files.
        with socket.create_connection((row['host'],row['port']),timeout=timeout):pass
        return True
    def compatibility(self,save_id,*,title_id='',region='',game_version='',dlc_notes=''):
        row=self.conn.execute('SELECT * FROM saves WHERE id=?',(save_id,)).fetchone()
        if row is None:raise ValueError('Save not found')
        warnings=[];meta=json.loads(row['metadata_json'] or '{}')
        if row['platform']=='PS3':
            if title_id and title_id.upper()!=row['title_id'].upper():warnings.append('Title ID differs: may be incompatible')
            if region and row['region']!='Unknown' and region.casefold()!=row['region'].casefold():warnings.append('Region differs')
            if not row['title_id'] or row['title_id']=='UNKNOWN':warnings.append('Unknown title ID')
            if game_version and not meta.get('APP_VER'):warnings.append('Save does not establish compatible game patch level')
            if dlc_notes:warnings.append('DLC requirements are user-provided; not automatically verified')
            warnings.append('Account binding, encryption and actual load compatibility require console testing')
        else:
            warnings.append('PC game-specific format and Steam Cloud conflicts are not automatically validated')
        return {'save_id':save_id,'platform':row['platform'],'title_id':row['title_id'],
                'region':row['region'],'metadata':meta,'warnings':warnings}
    def privacy_audit(self,save_id):
        row=self.conn.execute('SELECT * FROM saves WHERE id=?',(save_id,)).fetchone()
        if row is None:raise ValueError('Save not found')
        folder=(self.root/row['stored_path']).resolve()
        if not folder.is_relative_to(self.data_dir.resolve()):raise ValueError('Unsafe save path')
        warnings=[]
        for p in folder.rglob('*'):
            if p.is_symlink():warnings.append('Symbolic link present');continue
            if not p.is_file():continue
            if re.search(r'(account|profile|license|act\.dat|idps|psid|npaccount|token|credential)',p.name,re.I):
                warnings.append('Potentially identifying or secret-bearing file: '+p.relative_to(folder).as_posix()[:120])
        if row['platform']=='PS3':warnings.append('PS3 account/console linkage may exist in binary metadata; manual Apollo review needed')
        if row['platform']=='PC':warnings.append('PC saves may contain names, account IDs or tokens inside binary data; not scanned')
        return warnings
    def steam_cloud_advice(self,save_id):
        row=self.conn.execute('SELECT * FROM saves WHERE id=?',(save_id,)).fetchone()
        if row is None:raise ValueError('Save not found')
        return ('Steam Cloud can overwrite a restored PC save or upload an older state. '
                'Back up first; close the game and verify Steam synchronization status before restoring.' if row['platform']=='PC'
                else 'Steam Cloud is not applicable to PS3 saves.')
    def export_catalog(self,target):
        target=Path(target).expanduser().resolve()
        if target.suffix.lower()!='.html' or target.exists():raise ValueError('Choose a new .html output file')
        rows=[r for r in self.list_saves() if r.get('visibility')=='Public' and r['status']=='Verified']
        cards=[]
        for r in rows:
            tags=', '.join(json.loads(r.get('tags_json') or '[]'))
            def esc(s):return html.escape(str(s),quote=True)
            cards.append('<article><strong>'+esc(r['game'])+'</strong><small>'+esc(r['platform'])+' · '+esc(r['title_id'])+'</small><h3>'+esc(r['label'])+'</h3><p>'+esc(r['category'])+' · '+esc(tags)+'</p><p>'+esc(r['notes'][:240])+'</p></article>')
        doc='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Z's Save Catalog</title><style>body{background:#121019;color:#e9e4f5;font:16px Segoe UI,sans-serif;max-width:1100px;margin:35px auto;padding:20px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:16px}article{background:#211d30;border:1px solid #4c3c68;border-radius:13px;padding:18px}small{display:block;color:#c0acd9;margin-top:7px}p{color:#bcb5ce}</style><h1>Z's Save Catalog</h1><p>Public, verified save descriptions. Downloads distributed separately.</p><main>'''+''.join(cards)+'</main></html>'
        target.parent.mkdir(parents=True,exist_ok=True);target.write_text(doc,encoding='utf8');return len(rows)
    def startup_health(self):
        output={'database':'unknown','archive_exists':self.root.is_dir(),'free_bytes':shutil.disk_usage(self.root).free,'warnings':[]}
        row=self.conn.execute('PRAGMA quick_check').fetchone();output['database']=row[0]
        if row[0]!='ok':output['warnings'].append('Database integrity check failed')
        if output['free_bytes']<1024**3:output['warnings'].append('Less than 1 GiB of free storage')
        if not self.backups_dir.is_dir():output['warnings'].append('Backup directory unavailable')
        return output
