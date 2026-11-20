"""v0.7 cautious local PC detection, retried PS3 downloads, and batch public exports."""
from __future__ import annotations
import json
import re
import time
from pathlib import Path
from typing import Callable
from .transfer_v06 import pc_save_candidates
from .integrations import steam_games
from .enhanced import sha256_file

# Known location *candidates*; never automatically read or archive user files.
GAME_DIR_HINTS = {
    'stardew valley': [('Roaming AppData','StardewValley','Saves')],
    'terraria': [('Documents','My Games','Terraria','Players'),('Documents','My Games','Terraria','Worlds')],
    'minecraft': [('Roaming AppData','.minecraft','saves')],
    'the elder scrolls v: skyrim': [('Documents','My Games','Skyrim','Saves')],
    'fallout 4': [('Documents','My Games','Fallout4','Saves')],
    'the witcher 3: wild hunt': [('Documents','The Witcher 3','gamesaves')],
    'cyberpunk 2077': [('Local AppData','CD Projekt Red','Cyberpunk 2077')],
    "baldur's gate 3": [('Local AppData','Larian Studios',"Baldur's Gate 3",'PlayerProfiles','Public','Savegames','Story')],
    'hollow knight': [('LocalLow','Team Cherry','Hollow Knight')],
    'elden ring': [('Roaming AppData','EldenRing')],
    'subnautica': [('LocalLow','Unknown Worlds','Subnautica')],
    'palworld': [('Local AppData','Pal','Saved','SaveGames')],
}

def discover_game_locations(home:Path|None=None, env:dict|None=None, games:list|None=None):
    """Return existing, user-reviewable paths only; no deep filesystem scans."""
    import os
    home=Path(home) if home is not None else Path.home()
    env=dict(os.environ if env is None else env)
    games=steam_games() if games is None else games
    roots={'Documents':home/'Documents', 'Roaming AppData':Path(env.get('APPDATA') or home/'AppData'/'Roaming'),
           'Local AppData':Path(env.get('LOCALAPPDATA') or home/'AppData'/'Local'),
           'LocalLow':home/'AppData'/'LocalLow'}
    result=[];seen=set()
    for game in games:
        name=str(game.get('name',''))
        for parts in GAME_DIR_HINTS.get(name.casefold(),[]):
            root=roots[parts[0]]
            path=root.joinpath(*parts[1:])
            if path.is_dir() and not path.is_symlink():
                key=(str(path.resolve()).casefold(),name.casefold())
                if key not in seen:
                    seen.add(key)
                    result.append({'name':name,'path':str(path),'source':'Known-location hint',
                                   'certainty':'candidate — inspect contents before import'})
    return sorted(result,key=lambda r:(r['name'].casefold(),r['path'].casefold()))

RETRYABLE=(TimeoutError,ConnectionError,EOFError,OSError)

def download_with_retry(api,path,archive,progress=None,cancel:Callable[[],bool]|None=None,
                        max_attempts:int=3,sleep:Callable[[float],None]=time.sleep,
                        notify:Callable[[int,str],None]|None=None):
    """Reconnect and restart a failed whole-save download; no unsafe partial-file resume."""
    if not 1<=max_attempts<=5:raise ValueError('Retry count must be between 1 and 5')
    for attempt in range(1,max_attempts+1):
        if cancel and cancel():raise InterruptedError('Transfer cancelled')
        try:
            return api.download_save(path,archive,progress=progress,cancel=cancel)
        except (InterruptedError,ValueError):
            # Invalid saves and user cancellation must not be retried.
            raise
        except RETRYABLE as exc:
            if attempt==max_attempts:raise
            if notify:notify(attempt,f'{type(exc).__name__}: {exc}')
            # Small, bounded backoff; check cancellation between sleeps.
            for _ in range(attempt*2):
                if cancel and cancel():raise InterruptedError('Transfer cancelled')
                sleep(0.25)

def safe_slug(s:str):
    return re.sub(r'[^A-Za-z0-9_-]+','_',str(s)).strip('_')[:65] or 'Save'

def export_many(archive,ids,target:Path):
    """Export each eligible save to an individual ZIP. Never overwrite outputs."""
    target=Path(target).expanduser().resolve()
    if target.exists() and not target.is_dir():raise ValueError('Export path is not a folder')
    target.mkdir(parents=True,exist_ok=True)
    results=[]
    for sid in dict.fromkeys(ids):
        row=archive.conn.execute('SELECT * FROM saves WHERE id=?',(sid,)).fetchone()
        if row is None:
            results.append({'id':sid,'status':'skipped','reason':'Save not found'});continue
        filename=f"{safe_slug(row['game'])}_{safe_slug(row['platform'])}_{str(sid)[:10]}.zip"
        dest=target/filename
        try:
            archive.export_release(sid,dest)
            results.append({'id':sid,'game':row['game'],'status':'exported','file':filename,'sha256':sha256_file(dest)})
        except (ValueError,OSError,FileExistsError) as exc:
            results.append({'id':sid,'game':row['game'],'status':'skipped','reason':str(exc)})
    # A manifest is useful for sharing, but never silently overwrite a prior one.
    i=1
    while (target/f'release_batch_{i:03d}.json').exists():i+=1
    manifest=target/f'release_batch_{i:03d}.json'
    with manifest.open('x',encoding='utf-8') as f:
        json.dump({'version':'0.7','results':results},f,indent=2,ensure_ascii=False)
    return results,manifest
