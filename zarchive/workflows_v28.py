"""v2.8 conservative desktop utilities: non-destructive PKG checks, ETA, exit watcher.

No firmware compatibility claim is inferred from PKG headers; no PS3 modifications.
"""
from __future__ import annotations
import hashlib, math, os, statistics, time
from pathlib import Path
from .homebrew_v24 import inspect_pkg_metadata


def compare_pkgs(paths, *, max_files=100):
    paths=list(paths)
    if len(paths)>max_files:raise ValueError('Too many PKG files')
    output=[];by_digest={}
    for name in paths:
        p=Path(name)
        try:
            if p.is_symlink():raise ValueError('Symlinked PKG not supported')
            info=inspect_pkg_metadata(p)
            digest=info['sha256']
            first=by_digest.setdefault(digest,str(p))
            output.append({'file':str(p),'valid_header':True,'size':info['bytes'],
                           'sha256':digest,'duplicate_of':first if first!=str(p) else None,
                           'pkg_type':info.get('package_type'),'header_revision':info.get('header_revision'),
                           'size_warning':info.get('size_warning',False)})
        except (OSError,ValueError) as exc:
            output.append({'file':str(p),'valid_header':False,'error':str(exc)[:200]})
    return output


def firmware_compatibility(*, firmware=None, custom_firmware=None, app_requirement=None, region=None):
    """Display-only compatibility record: never infer a package will run from a version string."""
    notes=['PKG headers alone cannot prove firmware, CFW, or game compatibility.',
           'Confirm title ID, region, signed package type, and publisher documentation.']
    if not firmware:notes.append('Console firmware has not been verified.')
    if not app_requirement:notes.append('Minimum compatible firmware for this application is unknown.')
    if region:notes.append('Check that the package and game use compatible regions and title IDs.')
    return {'console_firmware':firmware,'cfw':custom_firmware,'required_firmware':app_requirement,
            'region':region,'compatibility':'unverified','notes':notes}


def estimate_transfer(samples, remaining_bytes, *, min_samples=4):
    """samples: [(monotonic_seconds, cumulative_bytes), ...]. Bounded, robust ETA range."""
    if remaining_bytes is None or remaining_bytes<0:raise ValueError('Nonnegative remaining bytes required')
    points=list(samples)[-40:]
    rates=[]
    for (t1,b1),(t2,b2) in zip(points,points[1:]):
        dt=t2-t1;db=b2-b1
        if dt>0 and db>=0:rates.append(db/dt)
    good=[x for x in rates if x>0]
    if len(good)<min_samples:return {'status':'insufficient_data','eta_seconds':None,'confidence':'unknown','range_seconds':None}
    # Median resists short transfer spikes and scheduling noise.
    rate=statistics.median(good)
    if rate<=0:return {'status':'stalled','eta_seconds':None,'confidence':'unknown','range_seconds':None}
    low=sorted(good)[max(0,int((len(good)-1)*.2))]
    high=sorted(good)[min(len(good)-1,int((len(good)-1)*.8))]
    variability=(high-low)/rate
    confidence='high' if len(good)>=10 and variability<.25 else ('medium' if variability<.65 else 'low')
    return {'status':'running','eta_seconds':round(remaining_bytes/rate),
            'confidence':confidence,'range_seconds':[round(remaining_bytes/max(high,1)),round(remaining_bytes/max(low,1))],
            'bytes_per_second':round(rate)}


def inventory_search(rows, query='', *, key='name'):
    needle=query.strip().casefold()
    return [r for r in rows if needle in str(r.get(key,'')).casefold()]


def cloud_conflict_preview(path, launcher=None, *, exists=None, modified=None):
    p=Path(path)
    present=p.exists() if exists is None else bool(exists)
    warnings=[]
    if launcher in ('Steam','Epic','GOG','Xbox','EA','Ubisoft'):warnings.append('Cloud sync may overwrite a local restore; close the launcher or disable sync before restoring.')
    if 'onedrive' in str(p).casefold():warnings.append('This path may be synchronized by OneDrive.')
    if present:warnings.append('Destination exists: a restore could replace newer progress.')
    return {'safe_for_unattended_restore':False,'destination_exists':present,'warnings':warnings or ['Cloud synchronization cannot be verified automatically.'],'last_modified':modified}


class ExitBackupMonitor:
    """Explicit opt-in poller. No process control, never deletes saves. Caller schedules checks."""
    def __init__(self,process_name,backup_callback,*,minimum_interval=30):
        if not process_name or '/' in process_name or '\\' in process_name:raise ValueError('Use an executable basename')
        if not callable(backup_callback):raise ValueError('Backup callback required')
        self.process_name=process_name.casefold();self.backup_callback=backup_callback
        self.minimum_interval=max(0,minimum_interval);self.was_running=False;self.last_backup=-float('inf')
    def check(self,running_names,*,now=None):
        current=time.monotonic() if now is None else float(now)
        running=self.process_name in {str(x).casefold() for x in running_names}
        exited=self.was_running and not running
        self.was_running=running
        if exited and current-self.last_backup>=self.minimum_interval:
            self.backup_callback();self.last_backup=current
            return 'backup_triggered'
        return 'running' if running else 'idle'
