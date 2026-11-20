"""v1.4 conservative PS3 console tools. No console writes or automatic re-signing."""
from __future__ import annotations
import ftplib, hashlib, json, re, socket, tempfile, time, uuid, zipfile
from datetime import datetime, timezone
from pathlib import Path
from .upgrade_v13 import ArchiveV13
from .transfer_v06 import PS3FTP, ROOT, SAVE_RE, USER_RE, NAME_RE
from .storage import folder_digest, read_param_sfo, now

PROFILE_PATH=re.compile(r'^/dev_hdd0/home/(\d{8})/savedata$')
MAX_PROFILE_SAVES=200

def profile_path(profile):
    if not re.fullmatch(r'\d{8}',str(profile)):raise ValueError('Invalid PS3 account directory')
    return f'{ROOT}/{profile}/savedata'

def _bounded_files(path):
    folder=Path(path).resolve(strict=True)
    if not folder.is_dir() or folder.is_symlink():raise ValueError('Invalid save directory')
    files=[];total=0
    for p in sorted(folder.iterdir()):
        if p.is_symlink() or not p.is_file():raise ValueError('Nested / linked save data not supported for Apollo export')
        total+=p.stat().st_size
        if total>512*1024*1024 or len(files)>=500:raise ValueError('Save exceeds export limits')
        files.append(p)
    if not any(p.name=='PARAM.SFO' for p in files):raise ValueError('Missing PARAM.SFO')
    return files

class ArchiveV14(ArchiveV13):
    def __init__(self,root):
        super().__init__(root)
        self.conn.executescript('''
        CREATE TABLE IF NOT EXISTS ps3_console_events(id TEXT PRIMARY KEY, profile_id TEXT, event_at TEXT NOT NULL, kind TEXT NOT NULL, status TEXT NOT NULL, detail TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS ps3_compatibility_notes(id TEXT PRIMARY KEY, save_id TEXT NOT NULL REFERENCES saves(id) ON DELETE CASCADE, title_id TEXT NOT NULL, region TEXT NOT NULL, game_version TEXT NOT NULL, dlc TEXT NOT NULL, result TEXT NOT NULL, notes TEXT NOT NULL, tested_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS ps3_compatibility_by_save ON ps3_compatibility_notes(save_id);
        ''');self.conn.commit()

    def record_console_event(self,profile_id,kind,status,detail=''):
        if kind not in ('connect','browse','download','profile_backup'):raise ValueError('Invalid event kind')
        if status not in ('ok','failed','cancelled'):raise ValueError('Invalid event status')
        with self.conn:self.conn.execute('INSERT INTO ps3_console_events VALUES (?,?,?,?,?,?)',
            (uuid.uuid4().hex,profile_id,now(),kind,status,str(detail)[:500]))

    def console_history(self,profile_id=None,limit=50):
        limit=max(1,min(int(limit),200))
        if profile_id:
            rows=self.conn.execute('SELECT * FROM ps3_console_events WHERE profile_id=? ORDER BY event_at DESC LIMIT ?', (profile_id,limit))
        else:rows=self.conn.execute('SELECT * FROM ps3_console_events ORDER BY event_at DESC LIMIT ?', (limit,))
        return [dict(r) for r in rows]

    def _connection(self,profile_id):
        r=self.conn.execute('SELECT * FROM console_profiles WHERE id=?',(profile_id,)).fetchone()
        if r is None:raise ValueError('Unknown PS3 connection profile')
        return dict(r)

    def ps3_dashboard(self,profile_id,ftp_factory=PS3FTP):
        profile=self._connection(profile_id)
        started=time.monotonic()
        api=ftp_factory(profile['host'],port=profile['port'])
        try:
            users=self.ps3_users(profile_id,ftp_factory=ftp_factory,log=False)
            elapsed=round((time.monotonic()-started)*1000,1)
            result={'connection':'connected','host':profile['host'],'port':profile['port'],
                    'round_trip_ms':elapsed,'user_profiles':users,'free_space_bytes':None,
                    'free_space_note':'Not available from standard FTP; no free-space estimate made'}
            self.record_console_event(profile_id,'connect','ok',f'{len(users)} profile(s) listed')
            return result
        except Exception as exc:
            self.record_console_event(profile_id,'connect','failed',exc)
            raise

    def ps3_users(self,profile_id,ftp_factory=PS3FTP,log=True):
        profile=self._connection(profile_id)
        entries=ftp_factory(profile['host'],port=profile['port']).list(ROOT)
        names=sorted({e.name for e in entries if e.is_dir and re.fullmatch(r'\d{8}',e.name)})
        if log:self.record_console_event(profile_id,'browse','ok',f'{len(names)} user(s)')
        return names

    def ps3_profile_saves(self,profile_id,user_id,ftp_factory=PS3FTP):
        profile=self._connection(profile_id)
        path=profile_path(user_id)
        rows=ftp_factory(profile['host'],port=profile['port']).list(path)
        paths=[path+'/'+r.name for r in rows if r.is_dir and NAME_RE.fullmatch(r.name) and r.name not in ('.','..')]
        if len(paths)>MAX_PROFILE_SAVES:raise ValueError('Profile contains too many saves for one batch; select a smaller batch')
        return paths

    def profile_backup(self,profile_id,user_id,ftp_factory=PS3FTP,progress=None,cancel=None):
        """Read-only remote, imports each save independently, continues on per-save failures."""
        profile=self._connection(profile_id)
        paths=self.ps3_profile_saves(profile_id,user_id,ftp_factory=ftp_factory)
        if not paths:raise ValueError('No accessible PS3 saves found')
        output={'user':str(user_id),'total':len(paths),'imported':[],'failed':[],'cancelled':False}
        for index,path in enumerate(paths):
            if cancel and cancel():output['cancelled']=True;break
            try:
                api=ftp_factory(profile['host'],port=profile['port'])
                row=api.download_save(path,self,cancel=cancel)
                output['imported'].append({'path':path,'id':row['id']})
            except InterruptedError:
                output['cancelled']=True;break
            except Exception as exc:
                output['failed'].append({'path':path,'error':str(exc)[:250]})
            if progress:progress(index+1,len(paths),path)
        status='cancelled' if output['cancelled'] else ('failed' if output['failed'] else 'ok')
        self.record_console_event(profile_id,'profile_backup',status,f"{len(output['imported'])}/{len(paths)} imported")
        return output

    def ps3_sync_preview(self,profile_id,user_id,ftp_factory=PS3FTP):
        """Compare folder names, not remote content hashes; never claims equality."""
        remote=self.ps3_profile_saves(profile_id,user_id,ftp_factory=ftp_factory)
        local={r['source_folder'] for r in self.list_saves(platform='PS3')}
        return [{'remote_path':path,'name':path.rsplit('/',1)[-1],
                 'status':'same name locally; content not compared' if path.rsplit('/',1)[-1] in local else 'not present by folder name'} for path in remote]

    def ps3_readonly_folder(self,profile_id,user_id,save_name=None,ftp_factory=PS3FTP):
        profile=self._connection(profile_id)
        path=profile_path(user_id)
        if save_name is not None:
            if not NAME_RE.fullmatch(save_name) or save_name in ('.','..'):raise ValueError('Invalid save folder')
            path+='/'+save_name
        return {'path':path,'entries':[{'name':e.name,'is_dir':e.is_dir,'bytes':e.size} for e in ftp_factory(profile['host'],port=profile['port']).list(path)]}

    def apollo_export(self,save_id,output_zip):
        """Preserve encrypted save contents unchanged; archive ZIP is NOT an Apollo re-signed save."""
        row=self._save(save_id)
        if row['platform']!='PS3':raise ValueError('Apollo export only supports PS3 saves')
        source=(self.root/row['stored_path']).resolve(strict=True)
        if not source.is_relative_to(self.data_dir.resolve()):raise ValueError('Unsafe archived save path')
        files=_bounded_files(source)
        dest=Path(output_zip).expanduser().absolute()
        if dest.suffix.lower()!='.zip' or dest.exists() or dest.is_symlink():raise ValueError('Choose a new .zip destination')
        if source in dest.parents or self.root in dest.parents:raise ValueError('Choose a destination outside the archive')
        dest.parent.mkdir(parents=True,exist_ok=True)
        try:
            with zipfile.ZipFile(dest,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as zipf:
                for f in files:zipf.write(f,arcname=f'{row["source_folder"]}/{f.name}')
                zipf.writestr('APOLLO_IMPORT_GUIDE.txt',
                    'Copy the save folder to USB/PS3 as appropriate. Use Apollo Save Tool to inspect, unlock or re-sign for your own account if needed.\n'
                    'This archive does not decrypt, modify or re-sign savedata. Check title ID/region/DLC and test on your console.\n')
            with zipfile.ZipFile(dest) as z:
                if z.testzip() is not None:raise ValueError('Damaged export')
            with dest.open('rb') as f: checksum=hashlib.file_digest(f,'sha256').hexdigest()
            return {'path':str(dest),'files':len(files),'sha256':checksum}
        except BaseException:
            dest.unlink(missing_ok=True);raise

    def add_ps3_compatibility(self,save_id,title_id,region,game_version='',dlc='',result='Unknown',notes=''):
        r=self._save(save_id)
        if r['platform']!='PS3':raise ValueError('PS3 only')
        if result not in ('Unknown','Confirmed','Incompatible','Needs testing'):raise ValueError('Invalid compatibility result')
        title_id=str(title_id).strip().upper()[:40]
        if not re.fullmatch('[A-Z0-9_-]{3,40}',title_id):raise ValueError('Invalid title ID')
        ident=uuid.uuid4().hex
        with self.conn:self.conn.execute('INSERT INTO ps3_compatibility_notes VALUES (?,?,?,?,?,?,?,?,?)',
            (ident,save_id,title_id,str(region)[:50],str(game_version)[:40],str(dlc)[:500],result,str(notes)[:1500],now()))
        return ident

    def ps3_compatibility_history(self,save_id):
        self._save(save_id)
        return [dict(r) for r in self.conn.execute('SELECT * FROM ps3_compatibility_notes WHERE save_id=? ORDER BY tested_at DESC',(save_id,))]
