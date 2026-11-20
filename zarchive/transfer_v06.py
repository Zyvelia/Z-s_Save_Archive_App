"""PS3 read-only FTP browsing, sequential cancellable downloads and cautious PC save candidates."""
from __future__ import annotations
import ftplib
import os
import re
import socket
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from .storage import MAX_IMPORT_BYTES
from .integrations import steam_games

ROOT='/dev_hdd0/home'
SAVE_RE=re.compile(r'^/dev_hdd0/home/\d{8}/savedata/[A-Za-z0-9_. -]{1,200}$')
USER_RE=re.compile(r'^/dev_hdd0/home/\d{8}(?:/savedata)?$')
NAME_RE=re.compile(r'^[A-Za-z0-9_. -]{1,200}$')
MAX_FILES=500


def validate_host(host):
    host=host.strip()
    if not host or len(host)>253 or any(c in host for c in '/\\@\r\n \t'):
        raise ValueError('Invalid PS3 host/IP')
    return host


def validate_path(path):
    path=path.rstrip('/') or '/'
    if not (path==ROOT or USER_RE.fullmatch(path) or SAVE_RE.fullmatch(path)):
        raise ValueError('Only /dev_hdd0/home/<profile>/savedata/<save> may be browsed')
    return path


def child_path(parent,name):
    parent=validate_path(parent)
    if not NAME_RE.fullmatch(name) or name in ('.','..'):
        raise ValueError('Invalid remote file or folder name')
    path=parent+'/'+name
    validate_path(path)
    return path


@dataclass(frozen=True)
class Entry:
    name:str
    is_dir:bool
    size:int|None=None


class PS3FTP:
    """Single-use FTP connection, default passive mode, no writes to console."""
    def __init__(self,host,user='anonymous',password='',port=21,timeout=12):
        self.host=validate_host(host);self.user=user;self.password=password
        self.port=int(port);self.timeout=int(timeout)
        if not 1<=self.port<=65535 or not 2<=self.timeout<=60:raise ValueError('Invalid port or timeout')

    def connect(self):
        # PS3 homebrew FTP implementations may emit non-UTF-8 bytes (e.g. 0xB0)
        # in directory listings. Latin-1 maps all bytes 1:1 and avoids a fatal
        # UnicodeDecodeError while retaining our strict ASCII path allowlist.
        # Set before connect so both control replies and listings use it.
        ftp=ftplib.FTP()
        ftp.encoding='latin-1'
        ftp.connect(self.host,self.port,timeout=self.timeout)
        ftp.login(self.user,self.password)
        ftp.set_pasv(True)
        return ftp

    def list(self,path=ROOT):
        path=validate_path(path)
        with self.connect() as ftp:
            ftp.cwd(path)
            try:
                rows=[]
                for name,metadata in ftp.mlsd():
                    if name in ('.','..') or not NAME_RE.fullmatch(name):continue
                    typ=metadata.get('type','').lower()
                    if typ not in ('file','dir'):continue
                    size=metadata.get('size')
                    rows.append(Entry(name,typ=='dir',int(size) if size and size.isdigit() else None))
                    if len(rows)>MAX_FILES:raise ValueError('Remote listing exceeds 500 entries')
                return sorted(rows,key=lambda r:(not r.is_dir,r.name.casefold()))
            except (ftplib.error_perm,AttributeError):
                # Older FTP implementations do not support MLSD; inspect by cwd.
                names=ftp.nlst()
                if len(names)>MAX_FILES:raise ValueError('Remote listing exceeds 500 entries')
                rows=[]
                for raw in names:
                    name=raw.rsplit('/',1)[-1]
                    if name in ('.','..') or not NAME_RE.fullmatch(name):continue
                    is_dir=False
                    try:
                        ftp.cwd(path+'/'+name);is_dir=True
                    except ftplib.error_perm:pass
                    finally:ftp.cwd(path)
                    rows.append(Entry(name,is_dir,None))
                return sorted(rows,key=lambda r:(not r.is_dir,r.name.casefold()))

    def download_save(self,path,archive,progress:Callable[[int,str],None]|None=None,cancel:Callable[[],bool]|None=None):
        path=validate_path(path)
        if not SAVE_RE.fullmatch(path):raise ValueError('Select a PS3 save folder, not a parent directory')
        if cancel and cancel():raise InterruptedError('Transfer cancelled')
        with tempfile.TemporaryDirectory(prefix='zarchive-ps3-') as folder:
            target=Path(folder)/path.rsplit('/',1)[-1];target.mkdir()
            total=0
            with self.connect() as ftp:
                ftp.cwd(path)
                # Conservative single-level PS3 save folders; refuse nested content.
                try:
                    rows=[]
                    for name,facts in ftp.mlsd():
                        if not NAME_RE.fullmatch(name) or name in ('.','..'):continue
                        if facts.get('type','').lower()=='dir':raise ValueError('Nested save directories are not supported')
                        if facts.get('type','').lower()=='file':rows.append(name)
                except ftplib.error_perm:
                    rows=[r.rsplit('/',1)[-1] for r in ftp.nlst()]
                if not rows or len(rows)>MAX_FILES or len(set(rows))!=len(rows):raise ValueError('Invalid remote save file list')
                if 'PARAM.SFO' not in rows:raise ValueError('No PARAM.SFO in selected remote folder')
                for name in rows:
                    if not NAME_RE.fullmatch(name) or name in ('.','..'):raise ValueError('Unexpected remote file')
                    if cancel and cancel():raise InterruptedError('Transfer cancelled')
                    with (target/name).open('xb') as out:
                        def write(data):
                            nonlocal total
                            if cancel and cancel():raise InterruptedError('Transfer cancelled')
                            total+=len(data)
                            if total>MAX_IMPORT_BYTES:raise ValueError('Save exceeds archive import size limit')
                            out.write(data)
                            if progress:progress(total,name)
                        ftp.retrbinary('RETR '+name,write,blocksize=65536)
            if cancel and cancel():raise InterruptedError('Transfer cancelled')
            return archive.import_save(target)


def pc_save_candidates(home:Path|None=None,env:dict|None=None,steam:list|None=None):
    """Conservative, bounded list of existing candidate folders; never claims every Steam folder is a save."""
    home=Path(home) if home is not None else Path.home()
    env=os.environ if env is None else env
    roots=[('Saved Games',home/'Saved Games'),('Documents/My Games',home/'Documents'/'My Games'),
           ('Documents',home/'Documents'),('LocalLow',home/'AppData'/'LocalLow')]
    for key,label in [('APPDATA','Roaming AppData'),('LOCALAPPDATA','Local AppData')]:
        if env.get(key):roots.append((label,Path(env[key])))
    steam=steam_games() if steam is None else steam
    results=[];seen=set()
    def add(name,path,source,certainty):
        path=Path(path)
        if path.is_dir() and not path.is_symlink():
            key=str(path.resolve()).casefold()
            if key not in seen:
                seen.add(key);results.append({'name':name,'path':str(path),'source':source,'certainty':certainty})
    for name,path in roots:add(name,path,'Windows','common root (not verified game save)')
    # Dedicated Steam userdata is used by some games, but may contain settings/cloud metadata.
    for lib in {g.get('library','') for g in steam if g.get('library')}:
        add('Steam userdata',Path(lib)/'userdata','Steam','candidate root (game save not confirmed)')
    return results
