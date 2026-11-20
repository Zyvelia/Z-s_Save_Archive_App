"""v0.8 durable non-secret queue and conservative FTP per-file resume.

No console writes. Resume only when remote SIZE and MDTM both match a stored
snapshot; if unavailable, partial data is discarded and full download begins.
"""
from __future__ import annotations
import hashlib
import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from .transfer_v06 import PS3FTP, SAVE_RE, NAME_RE, MAX_FILES
from .storage import MAX_IMPORT_BYTES


def _atomic_json(path: Path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd, tmp=tempfile.mkstemp(prefix='.queue-',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf8') as f:
            json.dump(data,f,indent=2);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


class TransferQueue:
    """Persistent save-folder work queue. Credentials are never persisted."""
    STATUSES={'pending','interrupted','completed','failed'}
    def __init__(self,path):
        self.path=Path(path);self.lock=threading.RLock()
        self.jobs=[]
        if self.path.exists():
            raw=json.loads(self.path.read_text(encoding='utf8'))
            if not isinstance(raw,dict) or not isinstance(raw.get('jobs'),list) or len(raw['jobs'])>2000:
                raise ValueError('Invalid transfer queue')
            for row in raw['jobs']:
                if not isinstance(row,dict):raise ValueError('Invalid transfer queue row')
                host=PS3FTP(str(row['host'])).host
                remote=str(row['path'])
                if not SAVE_RE.fullmatch(remote):raise ValueError('Invalid queued path')
                status=str(row.get('status','pending'))
                if status not in self.STATUSES:raise ValueError('Invalid queue status')
                if status=='interrupted' or status=='pending':status='pending'
                self.jobs.append({'host':host,'port':int(row.get('port',21)), 'path':remote,'status':status,
                                  'detail':str(row.get('detail',''))[:250]})
    def _save(self):_atomic_json(self.path,{'schema':1,'jobs':self.jobs})
    def add(self,host,port,path):
        host=PS3FTP(host,port=port).host
        if not SAVE_RE.fullmatch(path):raise ValueError('Queue a save folder')
        with self.lock:
            if len(self.jobs)>=2000:raise ValueError('Queue full')
            if any(x['host']==host and x['port']==port and x['path']==path and x['status']=='pending' for x in self.jobs):return False
            self.jobs.append({'host':host,'port':port,'path':path,'status':'pending','detail':''});self._save();return True
    def update(self,host,port,path,status,detail=''):
        if status not in self.STATUSES:raise ValueError('Invalid status')
        with self.lock:
            for job in reversed(self.jobs):
                if (job['host'],job['port'],job['path'])==(host,port,path) and job['status']=='pending':
                    job['status']=status;job['detail']=str(detail)[:250];self._save();return True
        return False
    def clear_completed(self):
        with self.lock:
            self.jobs=[j for j in self.jobs if j['status'] not in ('completed','failed')];self._save()


def _remote_meta(ftp,name):
    """Return stable (size, modification timestamp) or no reliable resume metadata."""
    try:
        size=ftp.size(name)
        mdtm=ftp.sendcmd('MDTM '+name)
        if size is None or not mdtm.startswith('213 ') or not mdtm[4:18].isdigit():return None
        size=int(size)
        if not 0<=size<=MAX_IMPORT_BYTES:return None
        return {'size':size,'modified':mdtm[4:18]}
    except (OSError,ValueError,AttributeError,Exception):return None


class ResumablePS3FTP(PS3FTP):
    """FTP download with durable staging; accepts REST only with stable remote metadata."""
    def __init__(self,*args,staging_root,**kwargs):
        super().__init__(*args,**kwargs)
        self.staging_root=Path(staging_root)

    def download_save(self,path,archive,progress=None,cancel=None):
        if not SAVE_RE.fullmatch(path):raise ValueError('Select a save folder')
        if cancel and cancel():raise InterruptedError('Transfer cancelled')
        key=hashlib.sha256(f'{self.host}:{self.port}:{path}'.encode()).hexdigest()
        stage=self.staging_root/key
        if stage.is_symlink():raise ValueError('Unsafe staging directory')
        stage.mkdir(parents=True,exist_ok=True)
        target=stage/'save'
        if target.is_symlink():raise ValueError('Unsafe staging directory')
        target.mkdir(exist_ok=True)
        total=0
        with self.connect() as ftp:
            ftp.cwd(path)
            try:
                rows=[]
                for name,facts in ftp.mlsd():
                    if not NAME_RE.fullmatch(name) or name in ('.','..'):continue
                    typ=facts.get('type','').lower()
                    if typ=='dir':raise ValueError('Nested PS3 save folders are not supported')
                    if typ=='file':rows.append(name)
            except Exception as ex:
                if isinstance(ex,ValueError):raise
                rows=[r.rsplit('/',1)[-1] for r in ftp.nlst()]
            if not rows or len(rows)>MAX_FILES or len(set(rows))!=len(rows) or 'PARAM.SFO' not in rows:
                raise ValueError('Invalid remote save listing')
            if any(not NAME_RE.fullmatch(name) or name in ('.','..') for name in rows):raise ValueError('Unsafe remote filename')
            for old in target.iterdir():
                if old.is_symlink() or not old.is_file():raise ValueError('Unsafe staging contents')
                if old.name not in rows:old.unlink()
            for name in rows:
                if cancel and cancel():raise InterruptedError('Transfer cancelled')
                dest=target/name;meta_path=stage/(hashlib.sha256(name.encode()).hexdigest()+'.json')
                metadata=_remote_meta(ftp,name)
                previous=None
                if meta_path.is_file():
                    try:previous=json.loads(meta_path.read_text(encoding='utf8'))
                    except (OSError,ValueError):pass
                if dest.is_symlink() or meta_path.is_symlink():raise ValueError('Unsafe staging file')
                existing=dest.stat().st_size if dest.exists() else 0
                safe_resume=bool(metadata and metadata==previous and 0<existing<=metadata['size'])
                if not safe_resume:
                    dest.write_bytes(b'');existing=0
                    if metadata:_atomic_json(meta_path,metadata)
                    elif meta_path.exists():meta_path.unlink()
                if metadata and existing==metadata['size']:
                    total+=existing
                    if progress:progress(total,name)
                    continue
                total+=existing
                if total>MAX_IMPORT_BYTES:raise ValueError('Save exceeds size limit')
                with dest.open('ab' if safe_resume else 'wb') as out:
                    def write(chunk):
                        nonlocal total
                        if cancel and cancel():raise InterruptedError('Transfer cancelled')
                        if total+len(chunk)>MAX_IMPORT_BYTES:raise ValueError('Save exceeds size limit')
                        out.write(chunk);total+=len(chunk)
                        if progress:progress(total,name)
                    # REST failures invalidate continuation; caller may retry from scratch.
                    try:ftp.retrbinary('RETR '+name,write,blocksize=65536,rest=existing if safe_resume else None)
                    except Exception:
                        if safe_resume:
                            dest.unlink(missing_ok=True)
                            meta_path.unlink(missing_ok=True)
                        raise
                if metadata and dest.stat().st_size!=metadata['size']:
                    raise OSError('Remote file size mismatch; staged bytes kept for recovery')
        if cancel and cancel():raise InterruptedError('Transfer cancelled')
        result=archive.import_save(target)
        # Successful import only: remove private temporary files; archive owns its own copy.
        import shutil
        shutil.rmtree(stage)
        return result
