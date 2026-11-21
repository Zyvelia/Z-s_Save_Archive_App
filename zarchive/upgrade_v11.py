"""v1.1 non-destructive workflows. GitHub actions are explicit, never automatic."""
from __future__ import annotations
import hashlib, html, json, os, re, sqlite3, tempfile, time, uuid, zipfile
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from .upgrade_v10 import ArchiveV10
from .storage import CATEGORIES, folder_digest, now

class ArchiveV11(ArchiveV10):
    def __init__(self, root):
        super().__init__(root)
        self.conn.executescript('''
        CREATE TABLE IF NOT EXISTS save_variants(id TEXT PRIMARY KEY, platform TEXT NOT NULL, game TEXT NOT NULL, name TEXT NOT NULL, UNIQUE(platform,game,name));
        CREATE TABLE IF NOT EXISTS save_variant_links(save_id TEXT PRIMARY KEY REFERENCES saves(id) ON DELETE CASCADE, variant_id TEXT REFERENCES save_variants(id) ON DELETE SET NULL);
        CREATE TABLE IF NOT EXISTS game_progress(platform TEXT NOT NULL, game TEXT NOT NULL, progress TEXT NOT NULL, PRIMARY KEY(platform,game));
        CREATE TABLE IF NOT EXISTS metadata_operations(id TEXT PRIMARY KEY, created_at TEXT NOT NULL, changes_json TEXT NOT NULL, undone INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS task_history(id TEXT PRIMARY KEY, created_at TEXT NOT NULL, action TEXT NOT NULL, status TEXT NOT NULL, detail TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS local_watch_folders(id TEXT PRIMARY KEY, game TEXT NOT NULL, path TEXT NOT NULL UNIQUE, last_digest TEXT, last_checked TEXT);
        CREATE TABLE IF NOT EXISTS archive_preferences(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        ''')
        self.conn.commit()

    def _save(self, sid):
        row=self.conn.execute('SELECT * FROM saves WHERE id=?',(sid,)).fetchone()
        if row is None: raise ValueError('Save not found')
        return row

    def create_variant(self,platform,game,name):
        if platform not in ('PS3','PC','PS4') or not self.conn.execute('SELECT 1 FROM saves WHERE platform=? AND game=?',(platform,game)).fetchone():
            raise ValueError('Game not found')
        name=' '.join(str(name).split())
        if not 1<=len(name)<=90:raise ValueError('Invalid variant name')
        ident=uuid.uuid4().hex
        self.conn.execute('INSERT INTO save_variants VALUES (?,?,?,?)',(ident,platform,game,name));self.conn.commit()
        return ident
    def variants(self,platform=None,game=None):
        q='SELECT * FROM save_variants WHERE 1=1';args=[]
        if platform:q+=' AND platform=?';args.append(platform)
        if game:q+=' AND game=?';args.append(game)
        return [dict(r) for r in self.conn.execute(q+' ORDER BY name',args)]
    def assign_variant(self,save_id,variant_id):
        row=self._save(save_id)
        if variant_id is not None:
            v=self.conn.execute('SELECT * FROM save_variants WHERE id=?',(variant_id,)).fetchone()
            if not v or (v['platform'],v['game'])!=(row['platform'],row['game']):raise ValueError('Variant belongs to another game')
        self.conn.execute('INSERT INTO save_variant_links VALUES (?,?) ON CONFLICT(save_id) DO UPDATE SET variant_id=excluded.variant_id',(save_id,variant_id));self.conn.commit()
    def set_game_progress(self,platform,game,progress):
        if progress not in ('Untouched','In Progress','Completed'):raise ValueError('Invalid completion state')
        if not self.conn.execute('SELECT 1 FROM saves WHERE platform=? AND game=?',(platform,game)).fetchone():raise ValueError('Game not found')
        self.conn.execute('INSERT INTO game_progress VALUES (?,?,?) ON CONFLICT(platform,game) DO UPDATE SET progress=excluded.progress',(platform,game,progress));self.conn.commit()
    def game_progress_list(self):return [dict(r) for r in self.conn.execute('SELECT * FROM game_progress ORDER BY game')]

    def bulk_metadata(self, ids, *, category=None, tags=None, visibility=None):
        ids=list(dict.fromkeys(ids))
        if not ids or len(ids)>500:raise ValueError('Choose 1 to 500 saves')
        if category is not None and category not in CATEGORIES:raise ValueError('Invalid category')
        if visibility is not None and visibility not in ('Public','Private'):raise ValueError('Invalid visibility')
        if tags is not None and (not isinstance(tags,list) or len(tags)>30 or any(not isinstance(t,str) or len(t)>64 or not t.strip() for t in tags)):
            raise ValueError('Invalid tags')
        if category is None and visibility is None and tags is None:raise ValueError('No changes selected')
        changes=[]
        with self.conn:
            for sid in ids:
                old=dict(self._save(sid))
                changes.append({'id':sid,'category':old['category'],'visibility':old['visibility'],'tags_json':old['tags_json']})
                self.conn.execute('UPDATE saves SET category=?,visibility=?,tags_json=? WHERE id=?',(
                    category if category is not None else old['category'],
                    visibility if visibility is not None else old['visibility'],
                    json.dumps(list(dict.fromkeys(t.strip() for t in tags)),ensure_ascii=False) if tags is not None else old['tags_json'],sid))
            operation=uuid.uuid4().hex
            self.conn.execute('INSERT INTO metadata_operations VALUES (?,?,?,0)',(operation,now(),json.dumps(changes)))
        return operation
    def undo_metadata(self,operation_id):
        with self.conn:
            row=self.conn.execute('SELECT * FROM metadata_operations WHERE id=?',(operation_id,)).fetchone()
            if not row or row['undone']:raise ValueError('Operation missing or already undone')
            for item in json.loads(row['changes_json']):
                self.conn.execute('UPDATE saves SET category=?,visibility=?,tags_json=? WHERE id=?',
                                  (item['category'],item['visibility'],item['tags_json'],item['id']))
            self.conn.execute('UPDATE metadata_operations SET undone=1 WHERE id=?',(operation_id,))
    def recent_metadata_operations(self):
        return [dict(r) for r in self.conn.execute('SELECT id,created_at,undone FROM metadata_operations ORDER BY created_at DESC LIMIT 50')]

    def save_diff(self,first,second):
        """Read-only bounded comparison of archived files, not binary semantic interpretation."""
        def index(sid):
            row=self._save(sid);base=(self.root/row['stored_path']).resolve()
            if not base.is_relative_to(self.data_dir.resolve()):raise ValueError('Unsafe path')
            out={}
            for f in base.rglob('*'):
                if f.is_symlink():raise ValueError('Symlinks are not supported')
                if not f.is_file():continue
                if len(out)>=5000:raise ValueError('Too many files')
                rel=f.relative_to(base).as_posix();sha=hashlib.sha256()
                with f.open('rb') as stream:
                    for chunk in iter(lambda:stream.read(1024*1024),b''):sha.update(chunk)
                out[rel]={'sha256':sha.hexdigest(),'bytes':f.stat().st_size}
            return out
        a,b=index(first),index(second)
        return {'added':sorted(b.keys()-a.keys()),'removed':sorted(a.keys()-b.keys()),
                'changed':sorted(k for k in a.keys() & b.keys() if a[k]!=b[k]),
                'unchanged':sum(a[k]==b[k] for k in a.keys()&b.keys())}

    def set_compression(self,preset):
        if preset not in ('Fast','Balanced','Smallest'):raise ValueError('Unknown compression preset')
        self.conn.execute('INSERT INTO archive_preferences VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('compression',preset));self.conn.commit()
    def compression(self):
        r=self.conn.execute("SELECT value FROM archive_preferences WHERE key='compression'").fetchone()
        return r['value'] if r else 'Balanced'
    def compressed_backup(self,save_id,target):
        """Use existing verified ZIP builder for backward-compatible export; recompress to preset in a new ZIP."""
        import os
        row=self._save(save_id)
        target=Path(target).expanduser().resolve()
        if target.exists():raise FileExistsError('Backup exists')
        mode={'Fast':(zipfile.ZIP_DEFLATED,1),'Balanced':(zipfile.ZIP_DEFLATED,6),'Smallest':(zipfile.ZIP_DEFLATED,9)}[self.compression()]
        folder=(self.root/row['stored_path']).resolve()
        if not folder.is_relative_to(self.data_dir.resolve()) or folder_digest(folder)!=(row['file_hash'],row['size_bytes'],row['file_count']):raise ValueError('Archived save integrity failed')
        target.parent.mkdir(parents=True,exist_ok=True)
        fd,temp=tempfile.mkstemp(prefix='.export-',suffix='.zip',dir=target.parent);os.close(fd)
        try:
            manifest={k:row[k] for k in ('platform','game','title_id','category','label','notes','region','status','file_hash','size_bytes','file_count','source_folder','imported_at')}
            manifest['created_at']=now();manifest['tags']=json.loads(row['tags_json'] or '[]')
            with zipfile.ZipFile(temp,'w',mode[0],compresslevel=mode[1]) as z:
                z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False))
                z.writestr('README.txt','Z Save Archive backup; save data is in save/.')
                for f in sorted(folder.rglob('*')):
                    if f.is_file():z.write(f,'save/'+f.relative_to(folder).as_posix())
            with zipfile.ZipFile(temp) as z:
                if z.testzip() is not None:raise ValueError('Corrupt ZIP')
            os.link(temp,target) # atomically create; no accidental overwrite
            return target
        finally:
            if os.path.exists(temp):os.unlink(temp)

    def record_task(self,action,status,detail=''):
        if status not in ('success','failed','cancelled','info'):raise ValueError('Unknown task state')
        self.conn.execute('INSERT INTO task_history VALUES (?,?,?,?,?)',(uuid.uuid4().hex,now(),str(action)[:100],status,str(detail)[:500]));self.conn.commit()
    def tasks(self):return [dict(r) for r in self.conn.execute('SELECT * FROM task_history ORDER BY created_at DESC LIMIT 200')]

    def watch_folder_add(self,game,path):
        """Register explicit PC folder for on-demand safe snapshot scans; no background watcher."""
        src=Path(path).expanduser().resolve()
        if not src.is_dir() or src.is_symlink() or src.is_relative_to(self.root):raise ValueError('Select an external PC save directory')
        folder_digest(src) # validate before accepting
        ident=uuid.uuid4().hex
        self.conn.execute('INSERT INTO local_watch_folders VALUES (?,?,?,?,?)',(ident,str(game)[:150],str(src),None,None));self.conn.commit();return ident
    def scan_watch_folders(self):
        results=[]
        for row in self.conn.execute('SELECT * FROM local_watch_folders').fetchall():
            try:
                folder=Path(row['path'])
                if folder.is_symlink() or not folder.is_dir():raise ValueError('Source missing or symbolic link')
                digest,_,_=folder_digest(folder)
                if digest!=row['last_digest']:
                    # On every detected change, import a new immutable copy. Duplicate content is skipped.
                    try: self.import_pc_save(folder,row['game'],label='Snapshot '+now());state='imported'
                    except ValueError as exc:
                        if 'duplicate' not in str(exc).lower():raise
                        state='duplicate'
                else:state='unchanged'
                self.conn.execute('UPDATE local_watch_folders SET last_digest=?,last_checked=? WHERE id=?',(digest,now(),row['id']));self.conn.commit()
                results.append({'game':row['game'],'state':state})
            except Exception as exc:results.append({'game':row['game'],'state':'error','detail':str(exc)})
        return results

    def github_release_payload(self,tag,name,draft=True):
        """Offline payload validation; publishing deliberately separate."""
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,80}',tag):raise ValueError('Invalid release tag')
        if not name.strip() or len(name)>150:raise ValueError('Invalid release name')
        return {'tag_name':tag,'name':name.strip(),'draft':bool(draft),'prerelease':False}
    def github_publish_draft(self,owner,repo,tag,name,*,token=None):
        """Explicit network call creates a DRAFT GitHub release; never uploads saves automatically."""
        if not all(re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',x) for x in (owner,repo)):raise ValueError('Invalid repository')
        token=token or os.environ.get('GITHUB_TOKEN')
        if not token:raise ValueError('Set GITHUB_TOKEN in your environment; tokens are not saved')
        data=json.dumps(self.github_release_payload(tag,name,True)).encode()
        request=Request(f'https://api.github.com/repos/{owner}/{repo}/releases',data=data,method='POST',headers={
            'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'Z-Save-Archive'})
        with urlopen(request,timeout=20) as response:
            result=json.load(response)
        return {'html_url':result.get('html_url'),'id':result['id'],'draft':result['draft']}

    def github_upload_verified_save(self,owner,repo,release_id,save_id,*,reviewed=False,token=None):
        """Explicitly attach one verified public ZIP to an existing GitHub release.

        This does not publish a draft release. Caller must review metadata and confirm.
        Credentials are never stored. Network errors leave the archive untouched.
        """
        if not reviewed:raise ValueError('Manual privacy review and confirmation are required')
        if not all(re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',x) for x in (owner,repo)):
            raise ValueError('Invalid repository')
        if type(release_id) is not int or release_id<=0:raise ValueError('Invalid release ID')
        row=self._save(save_id)
        if row['status']!='Verified' or row['visibility']!='Public':
            raise ValueError('Save must be Public and Verified')
        token=token or os.environ.get('GITHUB_TOKEN')
        if not token:raise ValueError('GITHUB_TOKEN is required; never stored')
        # Generate archive using the existing hash-checked exporter.
        with tempfile.TemporaryDirectory(prefix='zsave-upload-') as stage:
            filename=re.sub(r'[^A-Za-z0-9_.-]','_',row['game'])[:60]+'_'+save_id[:12]+'.zip'
            archive=Path(stage)/filename
            self.export_release(save_id,archive)
            if archive.stat().st_size>256*1024*1024:
                raise ValueError('ZIP exceeds conservative 256 MiB in-app upload limit')
            headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json',
                     'X-GitHub-Api-Version':'2022-11-28','User-Agent':'Z-Save-Archive'}
            req=Request(f'https://api.github.com/repos/{owner}/{repo}/releases/{release_id}',headers=headers)
            with urlopen(req,timeout=20) as resp: release=json.load(resp)
            upload_url=release.get('upload_url','').split('{',1)[0]
            # GitHub's release asset upload host is fixed; never trust arbitrary API URL.
            if not upload_url.startswith('https://uploads.github.com/repos/'):
                raise ValueError('Untrusted release upload URL')
            from urllib.parse import urlencode
            upload_url+='?'+urlencode({'name':filename})
            req=Request(upload_url,data=archive.read_bytes(),method='POST',headers={
                **headers,'Content-Type':'application/zip'})
            with urlopen(req,timeout=90) as resp: uploaded=json.load(resp)
            self.record_task('GitHub release asset','success',f'{owner}/{repo} release {release_id} save {save_id}')
            return {'name':uploaded.get('name'),'url':uploaded.get('browser_download_url'),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}

    def github_pages_catalog(self,destination):
        """Offline GitHub Pages-ready website; user must deploy it independently."""
        dest=Path(destination).resolve()
        if dest.exists():raise FileExistsError('Choose a new directory')
        if dest.is_relative_to(self.root) or self.root.is_relative_to(dest):raise ValueError('Choose a folder outside archive')
        dest.mkdir(parents=True)
        try:
            self.export_catalog(dest/'index.html')
            (dest/'.nojekyll').write_text('',encoding='utf-8')
            (dest/'README.txt').write_text('Static public save catalog. No save ZIPs are included. Review content before publishing.\n',encoding='utf-8')
            return dest
        except Exception:
            import shutil
            shutil.rmtree(dest,ignore_errors=True);raise
