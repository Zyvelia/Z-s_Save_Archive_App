"""PS3 homebrew package staging and read-only catalog.

No implicit network downloads, installations, or console system file writes.
Local PKGs are verified before being uploaded to /dev_hdd0/packages using
v2.1's no-overwrite FTP uploader.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from .converter_output_v21 import validate_pkg, upload_pkg_ftp

CATALOG = (
    {'name':'Apollo Save Tool','group':'Save management','description':'Back up, patch and re-sign supported PS3 saves.', 'url':'https://github.com/bucanero/apollo-ps3/releases'},
    {'name':'webMAN MOD','group':'Console management','description':'Game mounting, FTP server and console utilities.', 'url':'https://github.com/aldostools/webMAN-MOD'},
    {'name':'IRISMAN','group':'File management','description':'PS3 game and file management.', 'url':'https://github.com/aldostools/IRISMAN/releases'},
    {'name':'Movian','group':'Media','description':'Media playback on PS3.', 'url':'https://github.com/andoma/movian'},
    {'name':'Artemis PS3','group':'Utilities','description':'Game cheat engine; use offline and review compatibility.', 'url':'https://github.com/bucanero/ArtemisPS3/releases'},
    {'name':'RetroArch','group':'Emulation','description':'Emulator front end; check PS3-specific builds and licensing.', 'url':'https://www.retroarch.com/'},

    {'name':'ManaGunZ','group':'Backup & file management','description':'Game backup, file management and mounting tools.', 'url':'https://github.com/zarh/managunz/releases'},
    {'name':'PS3 ezRemote Client','group':'Network & transfers','description':'Browse FTP, SMB, NFS and WebDAV servers from PS3.', 'url':'https://github.com/cy33hc/ps3-ezremote-client/releases'},
    {'name':'OpenPS3FTP','group':'Network & transfers','description':'Alternative standalone FTP server for PS3.', 'url':'https://store.brewology.com/ps3/openps3ftp/'},
    {'name':'PKGi PS3','group':'Package management','description':'Package installer/downloader; use with content you are authorized to obtain.', 'url':'https://github.com/bucanero/pkgi-ps3'},
    {'name':'PS3LoadX','group':'Developer utilities','description':'Launch or receive homebrew during development.', 'url':'https://github.com/bucanero/ps3loadx'},
    {'name':'XMB Manager Plus','group':'XMB customization','description':'Custom XMB menu and package management extensions.', 'url':'https://github.com/XMB-Manager-Plus/xmb-manager-plus'},
    {'name':'Simple File Manager','group':'Backup & file management','description':'Lightweight file manager project for PS3.', 'url':'https://github.com/lmirel/fm_psx'},
    {'name':'prepISO','group':'ISO & storage','description':'Prepare supported NTFS and exFAT ISO content for webMAN MOD.', 'url':'https://store.brewology.com/ps3/webman-mod/'},
    {'name':'multiMAN','group':'Backup & file management','description':'Popular PS3 game and file manager; consult homebrew release listings.', 'url':'https://store.brewology.com/homebrew.php'},
    {'name':'PS3 Cloud Drive','group':'Save management','description':'Cloud save sync utility; review privacy and account requirements.', 'url':'https://github.com/mhaqs/ps3-cloud-drive'},
    {'name':'Rebug Toolbox','group':'System tools','description':'CFW-only console toolbox; firmware compatibility is critical.', 'url':'https://store.brewology.com/homebrew.php'},
    {'name':'PS3HEN','group':'System tools','description':'Homebrew enabler for supported setups; not required on CFW.', 'url':'https://github.com/PS3Xploit/PS3HEN'},
    {'name':'PS3 Pro Homebrew Packages','group':'Catalogs','description':'Community-maintained homebrew catalog; review publishers individually.', 'url':'https://github.com/PS3-Pro/Packages/releases'},
    {'name':'Brewology Homebrew Catalog','group':'Catalogs','description':'Browse additional PS3 homebrew releases and mirrors.', 'url':'https://store.brewology.com/homebrew.php'},
)

MAX_PKG_BYTES=16*1024**3


def inspect_homebrew_pkg(path: str | Path) -> dict:
    """Validate signature, reject symlinks, return checksum. No execution."""
    p=Path(path)
    if p.is_symlink() or not p.is_file() or p.suffix.lower()!='.pkg':
        raise ValueError('Select a regular, non-symlink .pkg file')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._ ()-]{0,180}\.pkg', p.name, re.I):
        raise ValueError('Rename the PKG using a simple safe ASCII filename before uploading')
    info=validate_pkg(p.parent,p)
    if info['bytes']>MAX_PKG_BYTES:raise ValueError('PKG is above configured safety limit')
    sha=hashlib.sha256()
    with p.open('rb') as src:
        for chunk in iter(lambda:src.read(1024*1024),b''):sha.update(chunk)
    return {**info,'sha256':sha.hexdigest(),'warning':'PKG signature and SHA-256 do not establish publisher authenticity, safety, or compatibility.'}


def upload_homebrew_pkg(path: str | Path, host: str, *, port=21,
                        username='anonymous', password='', progress=None, ftp_factory=None) -> dict:
    info=inspect_homebrew_pkg(path)
    result=upload_pkg_ftp(Path(info['path']).parent,info['path'],host,
                          port=port,username=username,password=password,
                          progress=progress,ftp_factory=ftp_factory)
    return {**result,'sha256_local':info['sha256'],'source_name':info['filename']}


def read_history(path: str | Path, limit=300) -> list[dict]:
    p=Path(path)
    if not p.exists():return []
    try:
        data=json.loads(p.read_text(encoding='utf-8'))
    except (ValueError,OSError):return []
    if not isinstance(data,list):return []
    return [x for x in data[-limit:] if isinstance(x,dict)]


def record_history(path: str | Path, *, filename: str, status: str, details: str='', sha256: str='') -> dict:
    if status not in ('uploaded','failed','queued','cancelled'):raise ValueError('Unsupported status')
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    entry={'timestamp':datetime.now(timezone.utc).isoformat(timespec='seconds'), 'filename':Path(filename).name,
           'status':status,'details':str(details)[:400],'sha256':sha256}
    records=read_history(p,limit=999)+[entry]
    temp=p.with_name(p.name+'.tmp')
    try:
        temp.write_text(json.dumps(records[-1000:],indent=2),encoding='utf-8')
        os.replace(temp,p)
    finally:
        if temp.exists():temp.unlink()
    return entry
