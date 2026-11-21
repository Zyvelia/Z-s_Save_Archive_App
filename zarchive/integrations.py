"""Optional, explicitly initiated external discovery and transfer helpers."""
from __future__ import annotations
import ftplib, io, os, re, shutil, tempfile, urllib.request, uuid
from pathlib import Path
from .storage import discover_saves, MAX_IMPORT_BYTES


def steam_libraries():
    """Find installed Steam library directories on Windows, best effort, without registry edits."""
    candidates=[]
    if os.name == 'nt':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as key:
                steam_path, _ = winreg.QueryValueEx(key, 'SteamPath')
            if steam_path:
                candidates.append(Path(steam_path))
        except OSError:
            pass
    for env in ('PROGRAMFILES(X86)','PROGRAMFILES'):
        p=os.environ.get(env)
        if p:candidates.append(Path(p)/'Steam')
    candidates.append(Path.home()/'AppData'/'Local'/'Steam')
    result=[]
    for root in candidates:
        vdf=root/'steamapps'/'libraryfolders.vdf'
        roots=[root]
        if vdf.is_file():
            try:
                txt=vdf.read_text(encoding='utf-8-sig',errors='replace')
                roots += [Path(s.replace('\\\\','\\')) for s in re.findall(r'"path"\s+"([^"]+)"',txt)]
            except OSError:pass
        for lib in roots:
            if lib.is_dir() and lib not in result:result.append(lib)
    return result


def steam_games():
    games=[]
    for lib in steam_libraries():
        appdir=lib/'steamapps'
        for acf in appdir.glob('appmanifest_*.acf') if appdir.is_dir() else []:
            try:
                txt=acf.read_text(encoding='utf-8-sig',errors='replace')
                name=re.search(r'"name"\s+"([^"]+)"',txt)
                appid=re.search(r'"appid"\s+"(\d+)"',txt)
                if name and appid:
                    row = {'name': name.group(1), 'appid': appid.group(1), 'library': str(lib)}
                    install = re.search(r'"installdir"\s+"([^"]+)"', txt)
                    if install and re.fullmatch(r'[^/\\:]+', install[1]) and install[1] not in ('.', '..'):
                        row['installation'] = str(appdir / 'common' / install[1])
                    games.append(row)
            except OSError:pass
    return sorted(games,key=lambda r:r['name'].casefold())


def download_steam_cover(appid: str, cache: Path):
    """Fetch a public Steam CDN game header on explicit user request. No API key."""
    if not re.fullmatch(r'\d{1,12}',appid):raise ValueError('Invalid Steam App ID')
    cache=Path(cache);cache.mkdir(parents=True,exist_ok=True)
    out=cache/f'steam_{appid}.jpg'
    if out.is_file():return out
    url=f'https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg'
    req=urllib.request.Request(url,headers={'User-Agent':'ZSaveArchive/0.3'})
    with urllib.request.urlopen(req,timeout=10) as response:
        if response.status!=200 or 'image/' not in response.headers.get('Content-Type',''):raise ValueError('Steam cover unavailable')
        data=response.read(2_000_001)
        if len(data)>2_000_000:raise ValueError('Cover too large')
    if not data.startswith(b'\xff\xd8'):raise ValueError('Unexpected image data')
    temp=cache/f'.{uuid.uuid4().hex}.jpg'
    temp.write_bytes(data);temp.replace(out)
    return out


def ftp_list_ps3(host,user='anonymous',password='',port=21,timeout=12):
    """Read directory listing only, no upload, deletion, or PS3 changes."""
    if not host or '/' in host or '@' in host:raise ValueError('Enter a host/IP')
    with ftplib.FTP() as ftp:
        ftp.connect(host,int(port),timeout=timeout);ftp.login(user,password);ftp.set_pasv(True)
        ftp.cwd('/dev_hdd0/home')
        return ftp.nlst()


def ftp_import_ps3(host,user,password,remote_save_folder,archive,port=21):
    """Explicit download of one save; bounded path, bounded byte count; source remains untouched."""
    if not host or '/' in host or '@' in host:raise ValueError('Invalid host')
    remote=remote_save_folder.rstrip('/')
    # A single save under PS3 user profile, never arbitrary remote directories
    if not re.fullmatch(r'/dev_hdd0/home/\d{8}/savedata/[A-Za-z0-9_.-]+',remote):
        raise ValueError('Choose a save path under /dev_hdd0/home/XXXXXXXX/savedata/SAVE_ID')
    with tempfile.TemporaryDirectory(prefix='zps3ftp-') as tmp:
        dest=Path(tmp)/remote.split('/')[-1];dest.mkdir()
        total=0
        with ftplib.FTP() as ftp:
            ftp.connect(host,int(port),timeout=12);ftp.login(user,password);ftp.set_pasv(True)
            ftp.cwd(remote)
            names=ftp.nlst()
            if len(names)>500:raise ValueError('Too many files in save folder')
            for name in names:
                short=name.rsplit('/',1)[-1]
                if short in ('.','..') or not re.fullmatch(r'[A-Za-z0-9_. -]{1,200}',short):
                    raise ValueError('Unexpected remote entry: '+name)
                with (dest/short).open('xb') as f:
                    def write(chunk):
                        nonlocal total
                        total+=len(chunk)
                        if total>MAX_IMPORT_BYTES:raise ValueError('FTP download over limit')
                        f.write(chunk)
                    ftp.retrbinary('RETR '+short,write,blocksize=65536)
        if not (dest/'PARAM.SFO').is_file():raise ValueError('No PARAM.SFO in downloaded folder')
        return archive.import_save(dest)
