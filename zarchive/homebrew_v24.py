"""v2.4 local homebrew intelligence. No console writes, installations or automatic downloads."""
from __future__ import annotations
import json, re, shutil, struct, os, tempfile, hashlib
from pathlib import Path
from datetime import datetime, timezone
from .homebrew_v22 import inspect_homebrew_pkg
from .homebrew_v23 import catalog_items, RELEASE_SOURCES, _atomic_json, _read_json

MAX_LIST = 2000

def _record_store(path):
    value=_read_json(path,{})
    return value if isinstance(value,dict) else {}

def set_app_record(path,app,*,installed_version=None,favorite=None,watch=None,notes=None):
    names={i['name'] for i in catalog_items()}
    if app not in names:raise ValueError('Homebrew is not in official curated catalog')
    data=_record_store(path);item=data.get(app,{})
    if not isinstance(item,dict):item={}
    if installed_version is not None:
        if not isinstance(installed_version,str) or len(installed_version)>96 or any(ord(c)<32 for c in installed_version):raise ValueError('Invalid version')
        item['installed_version']=installed_version.strip() # manually entered, never auto-detected
    if favorite is not None:item['favorite']=bool(favorite)
    if watch is not None:item['watch']=bool(watch)
    if notes is not None:
        if not isinstance(notes,str) or len(notes)>1024:raise ValueError('Invalid notes')
        item['notes']=notes
    item['updated_at']=datetime.now(timezone.utc).isoformat(timespec='seconds')
    data[app]=item;_atomic_json(path,data)
    return item

def read_app_records(path):
    names={i['name'] for i in catalog_items()}
    return {key:value for key,value in _record_store(path).items() if key in names and isinstance(value,dict)}

def offline_catalog(path,*,refresh=False):
    path=Path(path)
    if refresh:
        payload={'schema':1,'saved_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),'items':catalog_items()}
        _atomic_json(path,payload)
        return payload
    data=_read_json(path,{})
    if data.get('schema')==1 and isinstance(data.get('items'),list):return data
    return {'schema':1,'saved_at':None,'items':catalog_items(),'bundled':True}

def inspect_pkg_metadata(path):
    """Reads only documented common PS3 PKG header bytes; unknown fields stay unknown.

    Metadata is not a cryptographic trust/firmware compatibility assessment.
    """
    info=inspect_homebrew_pkg(path)
    p=Path(path)
    with p.open('rb') as fh: header=fh.read(128)
    if len(header)<64:raise ValueError('Truncated PKG header')
    # PS3 package header: magic, revision/type, metadata offset/count, header size,
    # item count, total size, data offset, data size. Values are big-endian.
    revision=struct.unpack_from('>H',header,4)[0]
    pkg_type=struct.unpack_from('>H',header,6)[0]
    declared_total=struct.unpack_from('>Q',header,24)[0]
    return {**info,'header_revision':revision,'package_type':pkg_type,
            'declared_total_size':declared_total if declared_total else None,
            'size_warning':bool(declared_total and declared_total!=info['bytes']),
            'trust_note':'Header fields and file hash cannot establish authenticity, installability, or firmware compatibility.'}

def batch_inspect_pkgs(paths,max_files=150):
    paths=list(paths)
    if len(paths)>max_files:raise ValueError('Too many PKGs for one inspection batch')
    rows=[]
    for raw in paths:
        p=Path(raw)
        try:rows.append({'path':str(p), 'ok':True,'info':inspect_pkg_metadata(p)})
        except (ValueError,OSError) as exc:rows.append({'path':str(p),'ok':False,'error':str(exc)[:250]})
    return rows

def local_upload_space_check(pkg_path,destination,*,reserve_bytes=512*1024*1024):
    """Local staging capacity only; PS3 free space requires a separate trusted server report."""
    p=Path(pkg_path)
    if not p.is_file():raise FileNotFoundError(p)
    dest=Path(destination);dest.mkdir(parents=True,exist_ok=True)
    free=shutil.disk_usage(dest).free
    return {'package_bytes':p.stat().st_size,'local_free_bytes':free,
            'reserve_bytes':reserve_bytes,'local_staging_ok':free>=p.stat().st_size+reserve_bytes,
            'ps3_free_bytes':None,'ps3_capacity_verified':False}

def installation_checklist(app,*,downloaded=False,uploaded=False,installed=False):
    if app not in {i['name'] for i in catalog_items()}:raise ValueError('Unknown homebrew')
    return [
        {'step':'Review official project release notes and firmware compatibility','done':False},
        {'step':'Download intended PKG from official release and inspect hash','done':bool(downloaded)},
        {'step':'Check free space on PS3 and approve FTP upload','done':bool(uploaded)},
        {'step':'Install manually via PS3 Game > Package Manager','done':bool(installed)},
        {'step':'Launch on console and manually record installed version','done':False},
    ]

def release_note_text(release,limit=10000):
    text=release.get('body','')
    return str(text)[:limit] if text else 'No release notes supplied by the publisher.'

def update_compatibility_record(installed_version,latest_tag):
    """Comparison for display only: tags may not follow semantic version conventions."""
    if not installed_version:return {'status':'unknown','message':'Installed version has not been entered.'}
    if not latest_tag:return {'status':'unknown','message':'No published release information.'}
    if installed_version.strip().lower().lstrip('v')==str(latest_tag).strip().lower().lstrip('v'):
        return {'status':'matching_tag','message':'Manual installed version matches published tag; not a firmware compatibility test.'}
    return {'status':'different_tag','message':'Published tag differs from manually entered version. Review changes before updating.'}
