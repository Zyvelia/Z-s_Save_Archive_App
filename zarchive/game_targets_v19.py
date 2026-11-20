"""v1.9 game targets: metadata-only, not executable editors.

Never mistake a planned game for a supported save parser.
"""
from __future__ import annotations
from pathlib import Path
import json, hashlib

GAME_TARGETS = (
    {'id':'borderlands-2','name':'Borderlands 2','aliases':('Borderlands 2','Borderlands2','BL2'), 'platform':'PS3','status':'Awaiting decrypted sample','priority':1,'sample':'Two Apollo-decrypted copies from the same character, with only one known change such as money'},
    {'id':'borderlands-1','name':'Borderlands (2009)','aliases':('Borderlands','Borderlands GOTY'), 'platform':'PS3','status':'Planned','priority':2,'sample':'Two decrypted saves of the same character'},
    {'id':'diablo-3','name':'Diablo III','aliases':('Diablo III','Diablo 3'), 'platform':'PS3','status':'Planned','priority':3,'sample':'Decrypted character samples'},
    {'id':'resident-evil-5','name':'Resident Evil 5','aliases':('Resident Evil 5','RE5'), 'platform':'PS3','status':'Planned','priority':4,'sample':'Decrypted save from two checkpoints'},
    {'id':'dead-space-3','name':'Dead Space 3','aliases':('Dead Space 3',), 'platform':'PS3','status':'Planned','priority':5,'sample':'Decrypted save samples'},
    {'id':'gta-v','name':'Grand Theft Auto V','aliases':('Grand Theft Auto V','GTA V','GTA 5'), 'platform':'PS3','status':'Planned','priority':6,'sample':'Decrypted story-mode saves'},
    {'id':'skyrim','name':'The Elder Scrolls V: Skyrim','aliases':('Skyrim','The Elder Scrolls V: Skyrim'), 'platform':'PS3','status':'Planned','priority':7,'sample':'Two decrypted character saves'},
    {'id':'gran-turismo-5','name':'Gran Turismo 5','aliases':('Gran Turismo 5','GT5'), 'platform':'PS3','status':'Planned','priority':8,'sample':'Decrypted save samples'},
)

def target_by_id(game_id):
    return next((dict(g) for g in GAME_TARGETS if g['id']==game_id),None)

def game_matches(target, game, platform):
    return bool(target and platform.upper()==target['platform'] and game.casefold().strip() in {n.casefold() for n in target['aliases']})

def matching_saves(rows,target_id):
    target=target_by_id(target_id)
    return [row for row in rows if game_matches(target,str(row.get('game','')),str(row.get('platform','')))]

def sample_inventory(folder, *, max_files=200, max_bytes=512*1024*1024):
    """Read-only structural listing to help diagnose samples. No game fields assumed.

    Does not read file contents or log metadata values; excludes symbolic links.
    """
    root=Path(folder).expanduser().resolve(strict=True)
    if not root.is_dir():raise ValueError('Sample must be a directory')
    inventory=[];total=0
    for p in sorted(root.rglob('*')):
        if p.is_symlink():raise ValueError('Symbolic links are not accepted')
        if not p.is_file():continue
        if len(inventory)>=max_files:raise ValueError('Too many files')
        size=p.stat().st_size; total+=size
        if total>max_bytes:raise ValueError('Sample exceeds total size limit')
        inventory.append({'relative_path':p.relative_to(root).as_posix(),'size_bytes':size})
    return {'file_count':len(inventory),'total_bytes':total,'files':inventory,
            'warning':'Structural inventory only; no save editing support is inferred.'}
