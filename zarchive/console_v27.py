"""v2.7 opt-in, conservative PS3 diagnostics and conversion preflight.

No credentials are persisted here. No network activity occurs on import, and
all PS3 interactions use limited socket/FTP reads only.
"""
from __future__ import annotations

import concurrent.futures
import ipaddress
import json
import os
import re
import shutil
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from .iso_converter_v20 import inspect_iso, inspect_game, check_cancelled

MAX_LAN_HOSTS = 32
TITLE_ID = re.compile(r'(?:BLUS|BLES|BCUS|BCES|BLJM|BLJS|BCJS|BCAS|BLAS|BLKS)[0-9]{5}', re.I)


def _utc():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def check_ftp(host: str, port: int = 21, timeout: float = 1.5, dial=None) -> dict:
    """TCP reachability, not a guarantee of working FTP authentication."""
    address = ipaddress.ip_address(host)
    if not (address.is_private or address.is_loopback):
        raise ValueError('For safety, PS3 diagnostics only connect to private/LAN IP addresses')
    if address.version != 4:
        raise ValueError('IPv4 required')
    if not 1 <= int(port) <= 65535 or not 0.1 <= timeout <= 10:
        raise ValueError('Invalid port or timeout')
    started = time.monotonic()
    try:
        conn = dial((str(address), int(port)), timeout=timeout) if dial else socket.create_connection((str(address), int(port)), timeout=timeout)
        with conn:
            pass
        state, reason = 'reachable', 'TCP port accepted a connection; FTP login and console identity not verified'
    except (OSError, TimeoutError) as exc:
        state, reason = 'unreachable', f'{type(exc).__name__}: {exc}'[:200]
    return {'host': str(address), 'port': int(port), 'state': state,
            'elapsed_ms': round((time.monotonic()-started)*1000, 1), 'note': reason, 'checked_at': _utc()}


def discover_ps3_hosts(subnet: str, *, max_hosts=MAX_LAN_HOSTS, port=21, timeout=0.35, probe=check_ftp) -> dict:
    """Explicit user-requested search. Restricted to a private IPv4 network and <=32 hosts."""
    network = ipaddress.ip_network(subnet, strict=False)
    if network.version != 4 or not network.is_private or network.prefixlen < 24:
        raise ValueError('Use a private IPv4 /24 or narrower LAN subnet')
    hosts = list(network.hosts())
    if len(hosts) > max_hosts or not 1 <= max_hosts <= MAX_LAN_HOSTS:
        raise ValueError(f'LAN discovery is limited to {MAX_LAN_HOSTS} addresses per scan; use a smaller subnet')
    def one(host):
        try:
            return probe(str(host),port=port,timeout=timeout)
        except (ValueError,OSError) as exc:
            return {'host':str(host),'state':'error','note':str(exc)[:180]}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        all_rows=list(pool.map(one,hosts))
    return {'subnet':str(network),'scanned':len(hosts),'reachable':[row for row in all_rows if row.get('state')=='reachable'],
            'warning':'An open FTP port does not establish that the device is a PS3.'}


def read_ftp_storage(host, *, port=21, user='anonymous', password='', factory=None) -> dict:
    """Use FTP STAT and listing only. Never claim free capacity based on folder sizes."""
    import ftplib
    host = str(ipaddress.ip_address(host))
    if not (ipaddress.ip_address(host).is_private or ipaddress.ip_address(host).is_loopback):
        raise ValueError('Only private PS3 LAN addresses supported')
    f = factory() if factory else ftplib.FTP()
    try:
        f.connect(host,int(port),timeout=4)
        f.login(user,password)
        response = f.sendcmd('SYST')
        try: info = f.sendcmd('STAT')
        except ftplib.all_errors: info = 'FTP STAT unsupported'
        return {'ftp_system':str(response)[:160],'ftp_status':str(info)[:1200],
                'capacity_bytes':None,'free_bytes':None,
                'note':'Standard FTP does not provide reliable console disk-space or temperature telemetry.'}
    finally:
        try:f.quit()
        except Exception:
            try:f.close()
            except Exception:pass


def conversion_preflight(source, helper, target, extractor=None, trueancestor=None, *, free_bytes=None, cancelled=None):
    """Read-only local checks prior to starting ISO staging; no external executables run."""
    check_cancelled(cancelled)
    src=Path(source).expanduser()
    warnings=[]; errors=[]; details={}
    try:
        if src.is_file() and src.suffix.lower()=='.iso':
            details['source_kind']='iso';details['source']=inspect_iso(src)
            warnings.append('ISO9660 signature does not prove this disc image is decrypted or convertible')
            if not extractor or not Path(extractor).is_file():errors.append('Select an existing 7z.exe for ISO input')
        else:
            details['source_kind']='folder';details['source']=inspect_game(src)
    except (ValueError,OSError) as exc:
        errors.append('Source: '+str(exc))
    h=Path(helper).expanduser()
    if not h.is_file() or h.suffix.lower()!='.exe':errors.append('CFW2OFW Helper executable is missing')
    else:details['helper']=str(h.resolve())
    if trueancestor:
        ta=Path(trueancestor).expanduser()
        if not ta.is_file():warnings.append('TrueAncestor tool was specified but does not exist')
        else:details['trueancestor']=str(ta.resolve())
    dst=Path(target).expanduser().resolve()
    if dst.exists():errors.append('Choose a NEW work directory; existing directories are not overwritten')
    if src.exists():
        src_resolved=src.resolve()
        if src_resolved == dst or dst in src_resolved.parents or (src.is_dir() and src_resolved in dst.parents):
            errors.append('Work directory must be separate from source')
        if src.is_file():details['source_bytes']=src.stat().st_size
        elif src.is_dir() and isinstance(details.get('source'), dict):
            total=0;files=0
            for base,dirs,names in os.walk(details['source']['source'],followlinks=False):
                check_cancelled(cancelled)
                if cancelled is None and files>20000:errors.append('Source has too many files for preflight');break
                for name in names:
                    check_cancelled(cancelled)
                    p=Path(base)/name
                    if p.is_symlink():errors.append('Source contains a symbolic link');continue
                    total+=p.stat().st_size;files+=1
            details['source_bytes']=total
    parent=next((p for p in (dst,*dst.parents) if p.exists()),None)
    capacity=free_bytes
    if capacity is None and parent:
        try: capacity=shutil.disk_usage(parent).free
        except OSError:pass
    if capacity is not None:
        details['work_disk_free_bytes']=int(capacity)
        # Extraction + converted data can temporarily require substantially more than source size.
        estimate=details.get('source_bytes',0)*3 + 2*1024**3
        details['conservative_estimated_bytes']=estimate
        if estimate>capacity:warnings.append('Estimated workspace requirement exceeds available disk space; estimate is conservative, not exact')
    details['warnings']=warnings;details['errors']=errors;details['ready_to_stage']=not errors
    return details


def inspect_pkg_title(path):
    """Best-effort filename-only title ID hint; does not decode encrypted PKG metadata."""
    p=Path(path)
    if not p.is_file() or p.suffix.lower()!='.pkg':raise ValueError('Select a PKG')
    with p.open('rb') as f:
        if f.read(4)!=b'\x7fPKG':raise ValueError('Invalid PS3 PKG header')
    match=TITLE_ID.search(p.stem)
    return {'name':p.name,'title_id_hint':match.group(0).upper() if match else None,
            'title_id_verified':False,'bytes':p.stat().st_size,
            'note':'Title ID inferred from filename only; no encrypted PKG metadata has been parsed.'}


def summarize_transfer(samples):
    """Compute conservative completed byte throughput; ETA only with known total."""
    rows=list(samples)
    if len(rows)<2:return {'rate_bytes_per_second':None,'eta_seconds':None}
    first,last=rows[0],rows[-1]
    dt=float(last['time'])-float(first['time'])
    transferred=int(last['bytes'])-int(first['bytes'])
    if dt<=0 or transferred<0:raise ValueError('Invalid transfer samples')
    rate=transferred/dt
    total=last.get('total')
    eta=(max(0,int(total)-int(last['bytes']))/rate) if total is not None and rate>0 else None
    return {'rate_bytes_per_second':round(rate,1),'eta_seconds':round(eta,1) if eta is not None else None,
            'note':'Observed average; network speed can change. ETA unavailable when total bytes are unknown.'}


def save_diagnostic_report(path, data):
    """Only a curated subset is exported: no passwords, FTP banners, or user IDs."""
    p=Path(path)
    if p.suffix.lower()!='.json' or p.exists():raise ValueError('Choose a new .json report')
    allowed=('host','port','state','elapsed_ms','checked_at','source_kind','ready_to_stage','warnings','errors')
    report={k:data[k] for k in allowed if k in data}
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2)
    return str(p)
