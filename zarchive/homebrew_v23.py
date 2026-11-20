"""v2.3 Homebrew releases and opt-in verified download queue.

No installation or FTP action. Only public GitHub release assets from curated
repository identities are eligible for direct download. Catalog links for other
sites remain manual. GitHub PKG assets are not inherently trusted.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import tempfile
import threading
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, quote
from .homebrew_v22 import CATALOG, inspect_homebrew_pkg

MAX_BYTES = 2 * 1024**3
# Only public release assets. CDN host is GitHub-controlled; do not accept arbitrary HTTP redirects.
TRUSTED_DOWNLOAD_HOSTS = {'github.com','release-assets.githubusercontent.com','objects.githubusercontent.com','github-releases.githubusercontent.com'}
API_HOST='api.github.com'
USER_AGENT='ZSaveArchive-Homebrew/2.3'

RELEASE_SOURCES = {
    'Apollo Save Tool': 'bucanero/apollo-ps3',
    'webMAN MOD': 'aldostools/webMAN-MOD',
    'IRISMAN': 'aldostools/IRISMAN',
    'Artemis PS3': 'bucanero/ArtemisPS3',
    'ManaGunZ': 'zarh/managunz',
    'PS3 ezRemote Client': 'cy33hc/ps3-ezremote-client',
}

class DownloadCancelled(Exception): pass


def catalog_items():
    """A curated category catalog; source information is not an endorsement."""
    return [{**app,'source':RELEASE_SOURCES.get(app['name']),
             'auto_release':app['name'] in RELEASE_SOURCES,
             'tags': ['PS3','Homebrew',app['group']]} for app in CATALOG]


def _iso_now():return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _atomic_json(path,data):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.homebrew-',suffix='.tmp',dir=str(path.parent))
    try:
        with os.fdopen(fd,'w',encoding='utf8') as f:
            json.dump(data,f,indent=2)
            f.flush();os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def _read_json(path,default):
    try:
        value=json.loads(Path(path).read_text(encoding='utf8'))
    except (OSError,ValueError):return default
    return value if isinstance(value,type(default)) else default


def validate_asset_url(url):
    parsed=urlparse(str(url))
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.port:
        raise ValueError('Only public HTTPS release asset URLs are allowed')
    if parsed.hostname not in TRUSTED_DOWNLOAD_HOSTS or parsed.fragment:
        raise ValueError('Release asset URL is not hosted by an approved GitHub host')
    return url


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        validate_asset_url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def default_opener():return urllib.request.build_opener(SafeRedirect())


def list_releases(app_name, *, opener=None, timeout=15, per_page=10):
    repo=RELEASE_SOURCES.get(app_name)
    if not repo:raise ValueError('This app has no supported GitHub release source; use its official project page')
    if not 1 <= per_page <= 30:raise ValueError('Invalid release page size')
    url=f'https://api.github.com/repos/{repo}/releases?per_page={per_page}'
    request=urllib.request.Request(url,headers={'Accept':'application/vnd.github+json','User-Agent':USER_AGENT})
    opener=opener or default_opener()
    with opener.open(request,timeout=timeout) as r:
        body=r.read(2*1024*1024+1)
    if len(body)>2*1024*1024:raise ValueError('Release response too large')
    raw=json.loads(body.decode('utf8'))
    if not isinstance(raw,list):raise ValueError('Invalid GitHub release response')
    releases=[]
    for item in raw:
        if not isinstance(item,dict) or item.get('draft') or not item.get('tag_name'):continue
        assets=[]
        for asset in item.get('assets',[]):
            if not isinstance(asset,dict):continue
            name=asset.get('name','');url=asset.get('browser_download_url','')
            size=asset.get('size',0)
            if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._ ()-]{0,180}\.pkg',name,re.I):continue
            if not isinstance(size,int) or size<4 or size>MAX_BYTES:continue
            try:validate_asset_url(url)
            except ValueError:continue
            assets.append({'name':name,'url':url,'size':size,'digest':asset.get('digest') or '',
                           'download_count':asset.get('download_count',0)})
        releases.append({'app':app_name,'repo':repo,'tag':str(item['tag_name'])[:120],
                         'published_at':item.get('published_at'),'prerelease':bool(item.get('prerelease')),
                         'page':item.get('html_url',''),'body':str(item.get('body') or '')[:10000],'assets':assets})
    return releases


def select_newest(releases,include_prerelease=False):
    """GitHub API returns newest-first. No attempt to compare non-semver tags."""
    return next((r for r in releases if (include_prerelease or not r['prerelease']) and r['assets']),None)


def load_queue(path):
    value=_read_json(path,[])
    return [x for x in value if isinstance(x,dict) and isinstance(x.get('id'),str)]


def queue_asset(path,app,tag,asset):
    if app not in RELEASE_SOURCES:raise ValueError('Unrecognized release project')
    if not isinstance(tag,str) or len(tag)>120 or not tag:raise ValueError('Invalid release tag')
    if not isinstance(asset,dict):raise ValueError('Invalid release asset')
    name=asset.get('name','');url=asset.get('url','');size=asset.get('size',0)
    validate_asset_url(url)
    expected_repo=RELEASE_SOURCES[app]
    parsed=urlparse(url)
    if parsed.hostname!='github.com' or not parsed.path.lower().startswith('/'+expected_repo.lower()+'/releases/download/'):
        raise ValueError('Download URL does not match the selected official release repository')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._ ()-]{0,180}\.pkg',name,re.I):raise ValueError('Not a safe PS3 PKG filename')
    if not isinstance(size,int) or not 4<=size<=MAX_BYTES:raise ValueError('Invalid asset size')
    digest=asset.get('digest','')
    if digest and not re.fullmatch(r'sha256:[a-fA-F0-9]{64}',digest):raise ValueError('Unsupported asset digest')
    items=load_queue(path)
    identity=hashlib.sha256((app+'\0'+tag+'\0'+url).encode()).hexdigest()[:20]
    existing=next((x for x in items if x['id']==identity),None)
    if existing:return existing
    job={'id':identity,'app':app,'tag':tag,'name':name,'url':url,'size':size,'digest':digest,
         'status':'pending','downloaded':0,'error':'','created_at':_iso_now()}
    items.append(job);_atomic_json(path,items);return job


def update_job(path,job_id,**changes):
    allowed={'status','downloaded','error','sha256','local_path','finished_at'}
    if not set(changes)<=allowed:raise ValueError('Unsupported queue mutation')
    items=load_queue(path);target=next((x for x in items if x['id']==job_id),None)
    if not target:raise KeyError('Unknown job')
    target.update(changes);_atomic_json(path,items);return target


def recover_queue(path):
    items=load_queue(path); changed=False
    for item in items:
        if item.get('status')=='downloading':
            item['status']='interrupted';item['error']='App closed during transfer; retry from beginning';changed=True
    if changed:_atomic_json(path,items)
    return items


def download_queued_asset(path,job_id,destination,*,opener=None,progress=None,cancel=None,timeout=30,bandwidth_limit=None):
    """Explicitly requested download; no overwrite; streams to .part and verifies size/hash/header.

    The caller must run this outside of the main GUI thread. No automatic FTP upload.
    """
    if bandwidth_limit is not None and (not isinstance(bandwidth_limit,int) or bandwidth_limit < 1024 or bandwidth_limit > 200*1024*1024):
        raise ValueError("Bandwidth limit must be 1 KiB/s to 200 MiB/s")
    job=next((x for x in load_queue(path) if x['id']==job_id),None)
    if not job:raise KeyError('Job not found')
    if job.get('status') not in ('pending','failed','interrupted','cancelled'):
        raise ValueError('Job is not pending or retryable')
    validate_asset_url(job['url'])
    target_dir=Path(destination);target_dir.mkdir(parents=True,exist_ok=True)
    target=target_dir/job['name']
    if target.exists() or target.is_symlink():raise FileExistsError(f'File exists: {target.name}')
    staging=target_dir/(f'.{job["id"]}.part')
    if staging.exists() or staging.is_symlink():raise FileExistsError('Staging file already exists; inspect before retrying')
    update_job(path,job_id,status='downloading',downloaded=0,error='')
    sha=hashlib.sha256(); received=0; started=time.monotonic()
    opener=opener or default_opener()
    req=urllib.request.Request(job['url'],headers={'User-Agent':USER_AGENT})
    try:
        with opener.open(req,timeout=timeout) as response:
            # Check final URL as well as redirects where supported by the injected client.
            if hasattr(response,'geturl'):validate_asset_url(response.geturl())
            reported=response.headers.get('Content-Length') if hasattr(response,'headers') else None
            if reported is not None and (not str(reported).isdigit() or int(reported)>MAX_BYTES):
                raise ValueError('Invalid or excessive download length')
            with staging.open('xb') as output:
                while True:
                    if cancel is not None and cancel.is_set():raise DownloadCancelled('Download cancelled')
                    block=response.read(256*1024)
                    if not block:break
                    received+=len(block)
                    if received>MAX_BYTES or received>job['size']:raise ValueError('Download exceeded advertised asset size')
                    output.write(block);sha.update(block)
                    if bandwidth_limit is not None:
                        remaining=received/bandwidth_limit-(time.monotonic()-started)
                        while remaining>0:
                            if cancel is not None and cancel.is_set():raise DownloadCancelled("Download cancelled")
                            time.sleep(min(remaining,0.1))
                            remaining=received/bandwidth_limit-(time.monotonic()-started)
                    if progress:progress(received,job['size'])
        if received!=job['size']:raise ValueError('Download size differs from release asset metadata')
        digest=sha.hexdigest()
        if job.get('digest') and job['digest'].lower()!=f'sha256:{digest}':raise ValueError('Publisher SHA-256 digest mismatch')
        with staging.open('rb') as check:
            if check.read(4)!=b'\x7fPKG':raise ValueError('Downloaded file has no PS3 PKG header')
        # temporary validation path is removed in the helper; publish with atomic rename after all checks
        if target.exists():raise FileExistsError('Destination appeared during download')
        os.replace(staging,target)
        return update_job(path,job_id,status='downloaded',downloaded=received,sha256=digest,local_path=str(target),finished_at=_iso_now(),error='')
    except Exception as exc:
        try:staging.unlink(missing_ok=True)
        except OSError:pass
        update_job(path,job_id,status='cancelled' if isinstance(exc,DownloadCancelled) else 'failed',downloaded=received,error=str(exc)[:350])
        raise


