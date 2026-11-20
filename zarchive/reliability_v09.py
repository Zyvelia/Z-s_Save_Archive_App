"""Read-only PC save candidate validation and persistent PS3 job recovery helpers.

Never follow symlinks, traverse an entire profile root, or modify candidate files.
"""
from __future__ import annotations
import os
from pathlib import Path
from .transfers_v08 import TransferQueue

KNOWN_EXTENSIONS={'.sav','.save','.dat','.ess','.skse','.sl2','.sl3','.player','.wld','.twld','.plr','.bak','.json','.bin'}
IGNORE_NAMES={'desktop.ini','thumbs.db','.ds_store'}


def inspect_pc_candidate(path, *, max_files=350, max_depth=3):
    """Bounded metadata-only scan; returns observations, never a compatibility claim."""
    root=Path(path)
    if root.is_symlink() or not root.is_dir():raise ValueError('Candidate must be a real directory')
    if not 1<=max_files<=1000 or not 0<=max_depth<=6:raise ValueError('Unsafe scan limits')
    found=[];files_seen=0;total_bytes=0;truncated=False
    pending=[(root,0)]
    while pending:
        folder,depth=pending.pop()
        try:
            with os.scandir(folder) as it:
                entries=sorted(it,key=lambda x:x.name.casefold())
        except OSError as exc:
            return {'path':str(root),'status':'unreadable','file_count':files_seen,
                    'bytes':total_bytes,'samples':found,'truncated':True,'detail':str(exc)[:150]}
        for entry in entries:
            if entry.is_symlink():continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    if depth<max_depth:pending.append((Path(entry.path),depth+1))
                    continue
                if not entry.is_file(follow_symlinks=False):continue
                if entry.name.casefold() in IGNORE_NAMES:continue
                files_seen+=1
                total_bytes+=entry.stat(follow_symlinks=False).st_size
                if Path(entry.name).suffix.casefold() in KNOWN_EXTENSIONS and len(found)<12:
                    found.append(str(Path(entry.path).relative_to(root)))
                if files_seen>=max_files:
                    truncated=True;pending.clear();break
            except OSError:continue
    status='candidate-files-found' if found else 'unconfirmed'
    return {'path':str(root),'status':status,'file_count':files_seen,
            'bytes':total_bytes,'samples':found,'truncated':truncated,
            'detail':'Filename hints do not verify save compatibility'}


def recoverable_jobs(queue:TransferQueue,host,port):
    return [dict(j) for j in queue.jobs if j['host']==host and j['port']==port and j['status'] in ('pending','failed')]


def retry_failed(queue:TransferQueue,host,port,paths):
    """Requeue failed jobs only after explicit user selection; no credentials stored."""
    count=0
    with queue.lock:
        for path in dict.fromkeys(paths):
            matches=[j for j in queue.jobs if j['host']==host and j['port']==port and j['path']==path and j['status']=='failed']
            if not matches:continue
            # Avoid duplicate pending rows, keep historical failure entry for audit.
            if queue.add(host,port,path):count+=1
    return count
