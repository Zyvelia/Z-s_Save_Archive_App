"""v1.2 read-only inspection and conservative save safety workflows."""
from __future__ import annotations
import hashlib, json, os, re, stat, time
from pathlib import Path
from .upgrade_v11 import ArchiveV11
from .storage import read_param_sfo, now

WORKFLOW_STATES = ('Working','Testing','Finished','Archived','Broken')
MAGIC = ((b'\\x00PSF','PS3 PARAM.SFO'),(b'PK\\x03\\x04','ZIP archive'),(b'SQLite format 3\\x00','SQLite database'),(b'\\x1f\\x8b','Gzip data'),(b'\\x89PNG\\r\\n\\x1a\\n','PNG image'))

def inspect_source(path, max_entries=250, max_bytes=16*1024*1024):
    """Inspect without following symlinks or reading the whole save into memory."""
    p=Path(path).expanduser().absolute()
    if not p.exists() or p.is_symlink(): raise ValueError('Missing path or symlink')
    root=p if p.is_dir() else p.parent
    files=[]; total=0
    if p.is_file(): candidates=[p]
    else:
        candidates=[]
        for directory,dirs,names in os.walk(p,followlinks=False):
            dirs[:]=sorted(d for d in dirs if not (Path(directory)/d).is_symlink())
            for name in sorted(names):
                candidate=Path(directory)/name
                if candidate.is_symlink() or not candidate.is_file(): raise ValueError('Unsupported file type')
                candidates.append(candidate)
                if len(candidates)>max_entries: raise ValueError('Too many files for preview')
    if len(candidates)>max_entries: raise ValueError('Too many files for preview')
    sfo=None
    for file in candidates:
        info=file.stat()
        if not stat.S_ISREG(info.st_mode): raise ValueError('Unsupported file type')
        total+=info.st_size
        if total>max_bytes:raise ValueError('Preview exceeds size cap; import remains available separately')
        with file.open('rb') as stream: signature=stream.read(24)
        kind=next((label for magic,label in MAGIC if signature.startswith(magic)), 'Unknown binary/data')
        if file.suffix.lower() in ('.json','.ini','.xml','.txt') and kind=='Unknown binary/data':kind='Text/config (extension hint)'
        rel=file.relative_to(root).as_posix()
        files.append({'path':rel,'bytes':info.st_size,'type':kind})
        if file.name.upper()=='PARAM.SFO':
            try:sfo=read_param_sfo(file)
            except (ValueError,OSError) as exc:sfo={'warning':str(exc)[:200]}
    return {'source':str(p),'file_count':len(files),'total_bytes':total,'platform_hint':'PS3' if sfo is not None else 'Unknown / PC candidate','param_sfo':sfo,'files':files}

class ArchiveV12(ArchiveV11):
    def __init__(self,root):
        super().__init__(root)
        self.conn.executescript('''CREATE TABLE IF NOT EXISTS save_workflow_state (
           save_id TEXT PRIMARY KEY REFERENCES saves(id) ON DELETE CASCADE,
           workflow TEXT NOT NULL, modified_at TEXT NOT NULL);
           CREATE INDEX IF NOT EXISTS workflow_state_status ON save_workflow_state(workflow);
        ''')
        self.conn.commit()
    def set_workflow_state(self,save_id,state):
        self._save(save_id)
        if state not in WORKFLOW_STATES:raise ValueError('Unsupported workflow state')
        with self.conn:
            self.conn.execute('INSERT INTO save_workflow_state VALUES (?,?,?) ON CONFLICT(save_id) DO UPDATE SET workflow=excluded.workflow, modified_at=excluded.modified_at',(save_id,state,now()))
    def workflow_state(self,save_id):
        self._save(save_id)
        r=self.conn.execute('SELECT workflow FROM save_workflow_state WHERE save_id=?',(save_id,)).fetchone()
        return r['workflow'] if r else 'Working'
    def inspect_archived(self,save_id):
        row=self._save(save_id)
        path=(self.root/row['stored_path']).resolve()
        if not path.is_relative_to(self.data_dir.resolve()):raise ValueError('Unsafe archived path')
        return inspect_source(path)
    def ps3_sfo(self,save_id):
        row=self._save(save_id)
        if row['platform']!='PS3':raise ValueError('Not a PS3 save')
        path=(self.root/row['stored_path']).resolve()
        if not path.is_relative_to(self.data_dir.resolve()):raise ValueError('Unsafe archived path')
        return read_param_sfo(path/'PARAM.SFO')
    def storage_report(self,limit=100):
        if not isinstance(limit,int) or not 1<=limit<=1000:raise ValueError('Invalid limit')
        rows=self.conn.execute('''SELECT platform, game, COUNT(*) AS saves, SUM(size_bytes) AS bytes FROM saves
                                GROUP BY platform,game ORDER BY bytes DESC LIMIT ?''',(limit,)).fetchall()
        backups=self.conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='backups'").fetchone()
        root_size=0; files=0
        for directory,dirs,names in os.walk(self.root,followlinks=False):
            dirs[:]=[d for d in dirs if not (Path(directory)/d).is_symlink()]
            for name in names:
                f=Path(directory)/name
                if f.is_symlink():continue
                try:root_size+=f.stat().st_size;files+=1
                except OSError:pass
                if files>200000:raise ValueError('Archive too large to scan in a single report')
        return {'games':[dict(x) for x in rows], 'archive_disk_bytes':root_size,'files_scanned':files}
    def restore_conflict_check(self,save_id,target):
        """Checks intended local restore destination; never writes anything."""
        self._save(save_id)
        dest=Path(target).expanduser().absolute()
        if dest.is_symlink():return {'safe':False,'warnings':['Destination is a symlink']}
        if dest.exists():
            if dest.is_file():return {'safe':False,'warnings':['Destination is an existing file']}
            try:
                entries=list(dest.iterdir())
                newer=any(f.stat().st_mtime>time.time()-60 for f in entries if not f.is_symlink())
            except OSError:return {'safe':False,'warnings':['Destination cannot be inspected']}
            warnings=['Destination already exists; choose a new empty folder']
            if newer:warnings.append('Destination contains recently modified files')
            return {'safe':False,'warnings':warnings}
        return {'safe':True,'warnings':[]}
    def hex_difference(self,first,second,relative_path,limit=128):
        """Offset samples only; no writes. Same relative file in two archived saves."""
        if not isinstance(limit,int) or not 1<=limit<=512:raise ValueError('Invalid limit')
        rel=Path(relative_path)
        if rel.is_absolute() or '..' in rel.parts or not rel.parts or '\\\\' in relative_path:raise ValueError('Unsafe relative path')
        def path(sid):
            r=self._save(sid); root=(self.root/r['stored_path']).resolve()
            if not root.is_relative_to(self.data_dir.resolve()):raise ValueError('Unsafe archive path')
            f=root/rel
            if f.is_symlink() or not f.resolve().is_relative_to(root) or not f.is_file():raise ValueError('File not found')
            return f
        a=path(first);b=path(second)
        size_a=a.stat().st_size;size_b=b.stat().st_size
        differences=[];pos=0
        with a.open('rb') as fa,b.open('rb') as fb:
            while True:
                x=fa.read(65536);y=fb.read(65536)
                if not x and not y:break
                for i in range(max(len(x),len(y))):
                    before=x[i] if i<len(x) else None;after=y[i] if i<len(y) else None
                    if before!=after:
                        differences.append({'offset':pos+i,'before':before,'after':after})
                        if len(differences)>=limit:return {'size_a':size_a,'size_b':size_b,'differences':differences,'truncated':True}
                pos+=max(len(x),len(y))
        return {'size_a':size_a,'size_b':size_b,'differences':differences,'truncated':False}
