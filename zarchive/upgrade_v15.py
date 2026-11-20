"""v1.5: opt-in publication workflow, offline catalog, privacy and release checks.
No network action occurs on archive startup, preflight, or catalog export.
"""
from __future__ import annotations
import hashlib, html, json, os, re, tempfile, uuid, zipfile
from pathlib import Path
from .upgrade_v14 import ArchiveV14
from .storage import folder_digest, now

_REPO=re.compile(r'^[A-Za-z0-9_.-]{1,100}$')

class ArchiveV15(ArchiveV14):
    def __init__(self,root):
        super().__init__(root)
        self.conn.executescript('''
        CREATE TABLE IF NOT EXISTS publisher_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS published_assets(
          id TEXT PRIMARY KEY, save_id TEXT, repository TEXT NOT NULL, release_id INTEGER,
          tag TEXT NOT NULL, asset_name TEXT NOT NULL, download_url TEXT NOT NULL,
          sha256 TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS published_assets_save ON published_assets(save_id);
        ''')
        self.conn.commit()

    def set_publishing_repo(self,owner,repo):
        if not _REPO.fullmatch(str(owner)) or not _REPO.fullmatch(str(repo)) or owner in ('.','..') or repo in ('.','..'):
            raise ValueError('Invalid GitHub owner/repository')
        with self.conn:
            self.conn.execute("INSERT INTO publisher_settings VALUES ('repository',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(f'{owner}/{repo}',))
        return f'{owner}/{repo}'

    def publishing_repo(self):
        r=self.conn.execute("SELECT value FROM publisher_settings WHERE key='repository'").fetchone()
        return r['value'] if r else ''

    def publication_preflight(self,save_id,*,privacy_reviewed=False):
        row=self._save(save_id)
        errors=[];warnings=[]
        if row['visibility']!='Public':errors.append('Save is not marked Public')
        if row['status']!='Verified':errors.append('Save is not marked Verified')
        folder=(self.root/row['stored_path']).resolve()
        try:
            if not folder.is_relative_to(self.data_dir.resolve()) or folder.is_symlink():raise ValueError('Unsafe archive path')
            if folder_digest(folder)!=(row['file_hash'],row['size_bytes'],row['file_count']):raise ValueError('Archived file hash mismatch')
        except (ValueError,OSError) as exc:errors.append('Archive integrity: '+str(exc))
        if row['platform']=='PS3' and row['title_id'] in ('','UNKNOWN'):warnings.append('PS3 title ID is unknown')
        if row['region'] in ('','Unknown'):warnings.append('Region not established')
        warnings.extend(self.privacy_audit(save_id))
        if not privacy_reviewed:errors.append('Explicit privacy review required')
        return {'save_id':save_id,'game':row['game'],'platform':row['platform'],
                'category':row['category'],'label':row['label'],
                'errors':errors,'warnings':warnings,'ready':not errors,
                'review_required':True,'compatibility_verified':False}

    def publication_history(self,limit=100):
        limit=max(1,min(int(limit),500))
        return [dict(r) for r in self.conn.execute('SELECT * FROM published_assets ORDER BY rowid DESC LIMIT ?', (limit,))]

    def create_publisher_draft(self,owner,repo,tag,name,*,token=None):
        self.set_publishing_repo(owner,repo)
        result=self.github_publish_draft(owner,repo,tag,name,token=token)
        with self.conn:self.conn.execute('INSERT INTO published_assets VALUES (?,?,?,?,?,?,?,?,?,?)',
          (uuid.uuid4().hex,None,f'{owner}/{repo}',result['id'],tag,'',str(result.get('html_url') or ''),'','draft',now()))
        return result

    def upload_publisher_save(self,owner,repo,release_id,save_id,*,tag='',privacy_reviewed=False,token=None):
        report=self.publication_preflight(save_id,privacy_reviewed=privacy_reviewed)
        if not report['ready']:raise ValueError('; '.join(report['errors']))
        if not _REPO.fullmatch(owner) or not _REPO.fullmatch(repo):raise ValueError('Invalid GitHub repository')
        result=self.github_upload_verified_save(owner,repo,release_id,save_id,reviewed=True,token=token)
        with self.conn:self.conn.execute('INSERT INTO published_assets VALUES (?,?,?,?,?,?,?,?,?,?)',
          (uuid.uuid4().hex,save_id,f'{owner}/{repo}',release_id,str(tag)[:80],result.get('name') or '',
           result.get('url') or '',result.get('sha256') or '','uploaded',now()))
        return result

    def publishable_saves(self):
        return [r for r in self.list_saves() if r['visibility']=='Public' and r['status']=='Verified']

    def export_public_site(self,destination,*,site_title="Z's Save Archive",description='Public verified PS3 and PC game saves'):
        dest=Path(destination).expanduser().resolve()
        if dest.exists() or dest.is_relative_to(self.root.resolve()) or self.root.resolve().is_relative_to(dest):
            raise ValueError('Choose a NEW output directory outside the archive')
        if not 1<=len(site_title.strip())<=100:raise ValueError('Invalid site title')
        if len(description)>300:raise ValueError('Site description too long')
        rows=self.publishable_saves()
        cards=[]
        esc=lambda s:html.escape(str(s),quote=True)
        for row in rows:
            tags=json.loads(row.get('tags_json') or '[]')
            latest=self.conn.execute("SELECT download_url FROM published_assets WHERE save_id=? AND state='uploaded' ORDER BY rowid DESC LIMIT 1",(row['id'],)).fetchone()
            url=latest['download_url'] if latest else ''
            if not url.startswith('https://github.com/'):
                url=''
            cards.append({'game':row['game'],'platform':row['platform'],'title_id':row['title_id'],
                'label':row['label'],'category':row['category'],'tags':tags,
                'notes':row['notes'][:700],'region':row['region'],'url':url})
        payload=json.dumps(cards,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
        css='''*{box-sizing:border-box}body{background:#110f19;color:#f1ebff;font:15px system-ui,sans-serif;margin:0}header{padding:45px max(24px,calc((100vw - 1180px)/2));background:#1b1728;border-bottom:1px solid #40354f}h1{margin:0 0 10px;font-size:2rem}p{color:#c3b9d2}main{max-width:1180px;margin:24px auto;padding:0 20px}.tools{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:24px}input,select{min-width:180px;flex:1;background:#272235;color:white;border:1px solid #514264;padding:12px;border-radius:9px}#cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:15px}article{background:#211b2d;border:1px solid #453850;padding:18px;border-radius:13px;min-width:0}small{color:#b9a8dc}.pill{border:1px solid #654e87;border-radius:30px;padding:3px 8px;display:inline-block;margin:2px;font-size:12px}a{color:#cfbaff}button{cursor:pointer}footer{padding:24px;color:#a99cbd;text-align:center}'''
        document='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'''+esc(site_title)+'''</title><style>'''+css+'''</style></head><body><header><h1>'''+esc(site_title)+'''</h1><p>'''+esc(description)+'''</p></header><main><div class="tools"><input id="q" type="search" aria-label="Search saves" placeholder="Search games, titles, tags..."><select id="platform" aria-label="Platform"><option value="">All platforms</option><option>PS3</option><option>PC</option></select><select id="category" aria-label="Category"><option value="">All categories</option><option>Legit</option><option>Modded</option><option>Unsorted</option></select></div><p id="count" aria-live="polite"></p><div id="cards"></div></main><footer>Only Public + Verified archive entries are shown. Compatibility and ownership remain the user's responsibility.</footer><script id="data" type="application/json">'''+payload+'''</script><script>
const data=JSON.parse(document.getElementById('data').textContent);const cards=document.getElementById('cards'),q=document.getElementById('q'),p=document.getElementById('platform'),c=document.getElementById('category');
function node(tag,text,cls){const e=document.createElement(tag);e.textContent=text;if(cls)e.className=cls;return e}
function render(){cards.replaceChildren();const term=q.value.trim().toLowerCase();const rows=data.filter(r=>(!p.value||r.platform===p.value)&&(!c.value||r.category===c.value)&&[r.game,r.label,r.title_id,r.region,r.notes,...r.tags].join(' ').toLowerCase().includes(term));document.getElementById('count').textContent=rows.length+' saves';for(const r of rows){const a=node('article','');a.append(node('small',r.platform+' · '+r.title_id+' · '+r.region));a.append(node('h2',r.game));a.append(node('h3',r.label));a.append(node('p',r.notes));a.append(node('small',r.category));for(const t of r.tags)a.append(node('span',t,'pill'));if(r.url){const link=node('a','Download on GitHub');link.href=r.url;link.target='_blank';link.rel='noopener noreferrer';a.append(node('p',''));a.append(link)}else a.append(node('p','No download link published yet'));cards.append(a)}}[q,p,c].forEach(x=>x.addEventListener('input',render));render();
</script></body></html>'''
        dest.mkdir(parents=True)
        try:
            (dest/'index.html').write_text(document,encoding='utf-8')
            (dest/'.nojekyll').write_text('',encoding='utf-8')
            (dest/'README.txt').write_text('Offline generated static website. Upload to GitHub Pages yourself after reviewing public metadata. No save files, credentials, or private entries are included.\n',encoding='utf-8')
            return {'directory':str(dest),'pages':1,'entries':len(rows),'download_links':sum(bool(r['url']) for r in cards)}
        except Exception:
            import shutil
            shutil.rmtree(dest,ignore_errors=True)
            raise
