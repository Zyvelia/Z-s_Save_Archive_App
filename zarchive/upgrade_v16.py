"""v1.6 local UI state, bounded notification history, task journal and paged search.
No save file writes, GitHub requests, or PS3 writes occur in these helpers.
"""
from __future__ import annotations
import json, uuid
from .upgrade_v15 import ArchiveV15
from .storage import now

_WIDGETS = ('stats','recent','quick','storage')
_TASK_STATES = ('queued','running','completed','failed','cancelled','interrupted')

class ArchiveV16(ArchiveV15):
    def __init__(self, root):
        super().__init__(root)
        self.conn.executescript('''
        CREATE TABLE IF NOT EXISTS ui_preferences(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS task_journal(id TEXT PRIMARY KEY, kind TEXT NOT NULL,
          label TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '');
        CREATE INDEX IF NOT EXISTS task_journal_recent ON task_journal(updated_at);
        CREATE TABLE IF NOT EXISTS notifications_v16(id TEXT PRIMARY KEY, kind TEXT NOT NULL,
          message TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS notifications_v16_recent ON notifications_v16(created_at);
        ''')
        # Mark tasks interrupted by an app exit; never automatically replay destructive operations.
        with self.conn:
            self.conn.execute("UPDATE task_journal SET state='interrupted', updated_at=? WHERE state='running'",(now(),))

    def set_pref(self, key, value):
        if key not in ('dashboard_widgets','density','last_page','window_geometry'):
            raise ValueError('Unsupported preference')
        if key=='dashboard_widgets':
            if not isinstance(value,list) or len(value)!=len(set(value)) or any(x not in _WIDGETS for x in value):
                raise ValueError('Invalid dashboard widgets')
        if key=='density' and value not in ('compact','standard','comfortable'):
            raise ValueError('Invalid density')
        if key=='last_page' and value not in ('dashboard','games','saves','settings'):
            raise ValueError('Invalid page')
        if key=='window_geometry' and (not isinstance(value,str) or len(value)>512):
            raise ValueError('Invalid geometry')
        with self.conn:
            self.conn.execute('INSERT INTO ui_preferences VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                              (key,json.dumps(value)))

    def get_pref(self, key, default=None):
        row=self.conn.execute('SELECT value FROM ui_preferences WHERE key=?',(key,)).fetchone()
        if row is None:return default
        try:return json.loads(row['value'])
        except (ValueError,TypeError):return default

    def create_task(self,kind,label):
        if kind not in ('ftp','backup','import','verify','export','maintenance','other'):
            raise ValueError('Unsupported task kind')
        if not isinstance(label,str) or not label.strip() or len(label)>240:
            raise ValueError('Invalid task label')
        tid=uuid.uuid4().hex; stamp=now()
        with self.conn:self.conn.execute('INSERT INTO task_journal VALUES (?,?,?,?,?,?,?)',
                                         (tid,kind,label,'queued',stamp,stamp,''))
        return tid

    def task_status(self,tid,state,detail=''):
        if state not in _TASK_STATES:raise ValueError('Invalid task state')
        with self.conn:
            cur=self.conn.execute('UPDATE task_journal SET state=?,updated_at=?,detail=? WHERE id=?',
                                  (state,now(),str(detail)[:2000],tid))
            if not cur.rowcount:raise ValueError('Unknown task')

    def tasks(self,limit=100):
        limit=max(1,min(500,int(limit)))
        return [dict(x) for x in self.conn.execute('SELECT * FROM task_journal ORDER BY rowid DESC LIMIT ?', (limit,))]

    def notify(self,kind,message):
        if kind not in ('info','success','warning','error'):raise ValueError('Invalid notification type')
        if not isinstance(message,str) or not message.strip():raise ValueError('Empty notification')
        with self.conn:
            self.conn.execute('INSERT INTO notifications_v16 VALUES (?,?,?,?)',(uuid.uuid4().hex,kind,message[:1000],now()))
            self.conn.execute('DELETE FROM notifications_v16 WHERE rowid NOT IN (SELECT rowid FROM notifications_v16 ORDER BY rowid DESC LIMIT 1000)')

    def notifications(self,limit=100):
        limit=max(1,min(500,int(limit)))
        return [dict(x) for x in self.conn.execute('SELECT * FROM notifications_v16 ORDER BY rowid DESC LIMIT ?', (limit,))]

    def search_page(self,query='',platform='All',category='All',limit=100,offset=0):
        """Database-level pagination; avoids loading all save rows for search results."""
        limit=max(1,min(250,int(limit)))
        offset=max(0,min(1000000,int(offset)))
        if platform not in ('All','PS3','PC','PS4') or category not in ('All','Legit','Modded','Unsorted'):
            raise ValueError('Invalid filter')
        term='%'+str(query).strip()[:200].replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
        where="(game LIKE ? ESCAPE '\\' OR title_id LIKE ? ESCAPE '\\' OR label LIKE ? ESCAPE '\\' OR notes LIKE ? ESCAPE '\\' OR tags_json LIKE ? ESCAPE '\\') AND (?='All' OR platform=?) AND (?='All' OR category=?)"
        args=(term,)*5+(platform,platform,category,category)
        count=self.conn.execute('SELECT COUNT(*) FROM saves WHERE '+where,args).fetchone()[0]
        rows=[dict(r) for r in self.conn.execute('SELECT * FROM saves WHERE '+where+' ORDER BY imported_at DESC,game COLLATE NOCASE LIMIT ? OFFSET ?',args+(limit,offset))]
        for r in rows:
            try:r['tags']=json.loads(r.get('tags_json') or '[]')
            except (ValueError,TypeError):r['tags']=[]
        return {'total':count,'limit':limit,'offset':offset,'items':rows}
