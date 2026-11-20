"""v1.7 additive workflow infrastructure: bounded jobs, recovery and UI layout."""
from __future__ import annotations
import json,uuid,threading
from .upgrade_v16 import ArchiveV16
from .storage import now

JOBS=('backup','verify','export','maintenance','import','ftp','publish')
STATES=('queued','running','completed','failed','cancelled','interrupted')
WIDGETS=('stats','recent','quick','storage')

class ArchiveV17(ArchiveV16):
    def __init__(self,root):
        super().__init__(root)
        self.conn.executescript('''
        CREATE TABLE IF NOT EXISTS jobs_v17(id TEXT PRIMARY KEY, kind TEXT NOT NULL, label TEXT NOT NULL,
            state TEXT NOT NULL, progress_current INTEGER NOT NULL DEFAULT 0,
            progress_total INTEGER NOT NULL DEFAULT 0, detail TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS jobs_v17_recent ON jobs_v17(updated_at);
        CREATE TABLE IF NOT EXISTS ui_v17(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        ''')
    def recover_interrupted_jobs(self):
        """Call exactly once at application startup before new workers begin."""
        with self.conn:
            return self.conn.execute("UPDATE jobs_v17 SET state='interrupted', detail='Previous session ended during operation', updated_at=? WHERE state='running'",(now(),)).rowcount
    def create_job(self,kind,label):
        if kind not in JOBS or not isinstance(label,str) or not label.strip() or len(label)>200:raise ValueError('Invalid job')
        jid=uuid.uuid4().hex;t=now()
        with self.conn:self.conn.execute('INSERT INTO jobs_v17 VALUES (?,?,?,?,?,?,?,?,?)',(jid,kind,label,'queued',0,0,'',t,t))
        return jid
    def update_job(self,jid,state,detail='',current=None,total=None):
        if state not in STATES:raise ValueError('Invalid state')
        with self.conn:
            old=self.conn.execute('SELECT * FROM jobs_v17 WHERE id=?',(jid,)).fetchone()
            if old is None:raise ValueError('Unknown job')
            allowed={'queued':('running','cancelled','interrupted'), 'running':('running','completed','failed','cancelled','interrupted'),
                     'interrupted':('queued','cancelled'), 'failed':('queued',), 'completed':(), 'cancelled':()}
            if state!=old['state'] and state not in allowed[old['state']]:raise ValueError('Unsafe state transition')
            c=old['progress_current'] if current is None else int(current)
            t=old['progress_total'] if total is None else int(total)
            if c<0 or t<0 or (t and c>t):raise ValueError('Invalid progress')
            self.conn.execute('UPDATE jobs_v17 SET state=?,detail=?,progress_current=?,progress_total=?,updated_at=? WHERE id=?',
                              (state,str(detail)[:1000],c,t,now(),jid))
    def jobs(self,limit=100):
        return [dict(r) for r in self.conn.execute('SELECT * FROM jobs_v17 ORDER BY rowid DESC LIMIT ?',(max(1,min(500,int(limit))),))]
    def dashboard_order(self):
        row=self.conn.execute("SELECT value FROM ui_v17 WHERE key='dashboard_order'").fetchone()
        if row:
            try:
                seq=json.loads(row[0]);self._check_order(seq);return seq
            except (ValueError,TypeError):pass
        return list(WIDGETS)
    def _check_order(self,order):
        if not isinstance(order,list) or len(order)!=len(WIDGETS) or set(order)!=set(WIDGETS) or len(set(order))!=len(order):raise ValueError('Invalid widget order')
    def set_dashboard_order(self,order):
        self._check_order(order)
        with self.conn:self.conn.execute("INSERT INTO ui_v17 VALUES ('dashboard_order',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(order),))
    def ui_setting(self,key,default=None):
        if key not in ('library_page_size','notification_filter'):raise ValueError('Invalid setting')
        row=self.conn.execute('SELECT value FROM ui_v17 WHERE key=?',(key,)).fetchone()
        try:return json.loads(row[0]) if row else default
        except (ValueError,TypeError):return default
    def set_ui_setting(self,key,value):
        if key=='library_page_size':
            if type(value)!=int or value not in (50,100,200):raise ValueError('Invalid page size')
        elif key=='notification_filter':
            if value not in ('all','error','warning','success','info'):raise ValueError('Invalid filter')
        else:raise ValueError('Invalid setting')
        with self.conn:self.conn.execute('INSERT INTO ui_v17 VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,json.dumps(value)))

class JobRunner:
    """One job per background worker; each worker opens its own DB connection.
    Cancellation is cooperative. No auto-replay of interrupted jobs.
    """
    def __init__(self,root):self.root=root;self._cancel={};self._lock=threading.Lock()
    def request_cancel(self,jid):
        with self._lock:
            event=self._cancel.get(jid)
            if not event:return False
            event.set();return True
    def submit(self,kind,label,operation,on_done=None):
        archive=ArchiveV17(self.root)
        try:jid=archive.create_job(kind,label)
        finally:archive.close()
        cancel=threading.Event()
        with self._lock:self._cancel[jid]=cancel
        def run():
            db=ArchiveV17(self.root)
            try:
                db.update_job(jid,'running')
                if cancel.is_set():db.update_job(jid,'cancelled','Cancelled before start');return
                # operation must use this worker's Archive instance; never a Qt-owned connection.
                result=operation(db,cancel)
                if cancel.is_set():db.update_job(jid,'cancelled','Cancellation requested')
                else:
                    db.update_job(jid,'completed',str(result)[:1000])
                    db.notify('success',f'{label} completed')
            except Exception as exc:
                try:db.update_job(jid,'failed',f'{type(exc).__name__}: {exc}');db.notify('error',f'{label} failed: {type(exc).__name__}')
                except Exception:pass
            finally:
                db.close()
                with self._lock:self._cancel.pop(jid,None)
                if on_done:on_done(jid)
        thread=threading.Thread(target=run,daemon=True,name='archive-job-'+jid[:8]);thread.start()
        return jid
