"""Safe, opt-in conversion-result inspection and package upload.

Never writes to /dev_hdd0/game or attempts installation; uploads to packages only.
"""
from __future__ import annotations
import ftplib
import hashlib
import json
import re
import shlex
import socket
import subprocess
from pathlib import Path
from typing import Callable

TITLE = re.compile(r'^(?:BLUS|BLES|BCUS|BCES|BLJM|BLJS|BCJS|BCAS|BLAS|BLKS|BCKS|NPUB|NPEB|NPJB|NPHB|NPUA|NPEA)[A-Z0-9]{5}$', re.I)
PKG_ROOT = '/dev_hdd0/packages'


def _is_inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def inspect_conversion_output(workspace: str | Path, *, max_entries: int = 12000) -> dict:
    """Discover game directories and package candidates; never claim XMB compatibility."""
    root = Path(workspace).resolve(strict=True)
    if not root.is_dir() or not (root / 'conversion_manifest.json').is_file():
        raise ValueError('Select a staged conversion workspace with conversion_manifest.json')
    meta = json.loads((root / 'conversion_manifest.json').read_text(encoding='utf-8'))
    folders, packages, inspected = [], [], 0
    for p in sorted(root.rglob('*')):
        inspected += 1
        if inspected > max_entries:
            raise ValueError('Workspace is too large to inspect safely')
        if p.is_symlink():
            raise ValueError('Symlinks are not permitted in conversion output')
        rel = p.relative_to(root)
        if p.is_dir() and TITLE.fullmatch(p.name) and (p / 'PARAM.SFO').is_file():
            folders.append({'name':p.name, 'relative_path':str(rel), 'kind':'game-folder'})
        if p.is_file() and p.suffix.lower() == '.pkg' and p.stat().st_size >= 64:
            packages.append({'name':p.name, 'relative_path':str(rel), 'size':p.stat().st_size})
    return {'title':meta.get('title','Unknown'), 'title_id':meta.get('title_id','Unknown'),
            'folders':folders, 'packages':packages, 'scanned_entries':inspected,
            'status':'packages_found' if packages else 'folders_found' if folders else 'no_installable_output',
            'warning':'Detected files are not proof of package validity or game compatibility.'}


def validate_pkg(workspace: str | Path, package: str | Path) -> dict:
    """Validate an existing PKG's location and signature before transfer."""
    root = Path(workspace).resolve(strict=True)
    p = Path(package).resolve(strict=True)
    if not _is_inside(p,root) or not p.is_file() or p.is_symlink() or p.suffix.lower() != '.pkg':
        raise ValueError('PKG must be a regular file inside the conversion workspace')
    with p.open('rb') as f:
        header=f.read(4)
    if header != b'\x7fPKG':
        raise ValueError('Invalid PKG header: expected PS3 PKG magic')
    if p.stat().st_size < 64: raise ValueError('Package is too small')
    return {'path':str(p), 'filename':p.name, 'bytes':p.stat().st_size}


def builder_command(workspace: str | Path, exe: str | Path, arguments: str = '') -> tuple[list[str],Path]:
    """Construct an explicitly selected local executable command, no shell."""
    root = Path(workspace).resolve(strict=True)
    if not root.is_dir() or not (root / 'conversion_manifest.json').is_file():
        raise ValueError('Not a conversion workspace')
    binary=Path(exe).resolve(strict=True)
    if not binary.is_file() or binary.suffix.lower() not in ('.exe','.bat','.cmd'):
        raise ValueError('Select a trusted PKG builder executable or batch script')
    if binary.suffix.lower() in ('.bat','.cmd'):
        # shell scripts require cmd.exe and additional quoting hazards; deliberately not supported
        raise ValueError('Batch/script builders are not supported; select an .exe builder')
    if '\n' in arguments or '\r' in arguments:raise ValueError('Arguments must be on one line')
    args=shlex.split(arguments, posix=False)
    if len(args)>32 or sum(map(len,args))>4096: raise ValueError('Too many builder arguments')
    return [str(binary), *args], root


def run_builder(workspace: str | Path, exe: str | Path, arguments: str = '', *, timeout: int=3600) -> dict:
    """Only run on direct user confirmation in UI; no shell and no file mutations here."""
    command, root=builder_command(workspace,exe,arguments)
    result=subprocess.run(command,cwd=root,stdin=subprocess.DEVNULL,
                          capture_output=True,text=True,errors='replace',timeout=timeout,check=False)
    log=(result.stdout+'\n'+result.stderr)[-30000:]
    return {'exit_code':result.returncode,'log':log,'success':result.returncode==0}


def upload_pkg_ftp(workspace: str | Path, pkg: str | Path, host: str, *,
                   port:int=21, username:str='anonymous', password:str='', timeout:float=20,
                   progress: Callable[[int,int],None]|None=None,
                   ftp_factory=None) -> dict:
    """Upload to package staging only, using temporary remote name and atomic rename.

    Never installs games, never overwrites existing remote files, never saves credentials.
    """
    info=validate_pkg(workspace,pkg)
    if not host or any(ch in host for ch in '/\\@ \t\r\n'):
        raise ValueError('Invalid console hostname or IP')
    if not 1 <= int(port) <= 65535:raise ValueError('Invalid FTP port')
    p=Path(info['path']); size=info['bytes']
    factory=ftp_factory or ftplib.FTP
    ftp=factory()
    temporary='.'+p.name+'.uploading'
    bytes_sent=0; uploaded=False
    try:
        ftp.connect(host,int(port),timeout=timeout)
        ftp.login(username,password)
        ftp.cwd(PKG_ROOT)
        existing=set(ftp.nlst())
        existing={name.rsplit('/',1)[-1] for name in existing}
        if p.name in existing or temporary in existing:
            raise FileExistsError('Remote package or unfinished transfer already exists; refusing overwrite')
        with p.open('rb') as src:
            def callback(data):
                nonlocal bytes_sent
                bytes_sent+=len(data)
                if progress:progress(bytes_sent,size)
            ftp.storbinary('STOR '+temporary,src,blocksize=256*1024,callback=callback)
        uploaded=True
        try:
            remote_size = ftp.size(temporary)
        except ftplib.error_perm as exc:
            raise IOError('The PS3 FTP server refused the SIZE check. The package was not finalized.') from exc
        if remote_size is None:
            raise IOError('The PS3 FTP server did not report a size. The package was not finalized.')
        if int(remote_size) != size or bytes_sent != size:
            raise IOError(f'FTP size mismatch: expected {size:,} bytes, sent {bytes_sent:,}, '
                          f'and the server reported {int(remote_size):,}. The package was not finalized.')
        ftp.rename(temporary,p.name)
        return {'remote_path':PKG_ROOT+'/'+p.name,'bytes':bytes_sent,'verified':'size only',
                'instruction':'On your PS3, use Game > Package Manager to install the uploaded PKG manually.'}
    except Exception:
        if uploaded or bytes_sent:
            try:ftp.delete(temporary)
            except Exception:pass
        raise
    finally:
        try:ftp.quit()
        except Exception:
            try:ftp.close()
            except Exception:pass
