"""v1.0 tools integrated into inherited PS3+PC desktop interface."""
from __future__ import annotations
import os,sys,json
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QShortcut,QKeySequence
from PySide6.QtWidgets import QApplication,QDialog,QVBoxLayout,QHBoxLayout,QPushButton,QLabel,QListWidget,QInputDialog,QMessageBox,QFileDialog
from .ui_v09 import Window as BaseWindow
from .ui_v04 import STYLE

class Window(BaseWindow):
    def __init__(self,root):
        super().__init__(root)
        self.setWindowTitle("Z's Save Archive  •  PS3 + PC  v1.0")
        self.resize(1450,900)
        menu=self.tools_btn.menu()
        menu.addSeparator()
        for name,callback in [
            ('Save profiles / characters',self.manage_profiles),
            ('Pin / unpin selected save',self.pin_current),
            ('Pinned items',self.show_pinned),
            ('Recovery Center',self.show_recovery_center),
            ('External drive ZIP backup',self.external_export),
            ('PS3 connection profiles',self.connections_dialog),
            ('Compatibility / privacy check',self.audit_selected),
            ('Export public HTML catalog',self.export_catalog),
            ('Startup health',self.show_health),
            ('Steam Cloud restore guidance',self.cloud_guidance),
        ]:menu.addAction(name,callback)
        self.shortcuts=[]
        for keys,fn in [('Ctrl+F',self.focus_search),('Ctrl+B',self.backup_version),
                        ('Ctrl+I',self.import_pc_shortcut),('Ctrl+Shift+H',self.show_health),
                        ('Ctrl+Shift+P',self.pin_current)]:
            short=QShortcut(QKeySequence(keys),self);short.activated.connect(fn);self.shortcuts.append(short)
        self.statusBar().showMessage('v1.0 · Save profiles · Pinned saves · Recovery · PS3 connection profiles')
    def focus_search(self):
        for key in ('search','search_edit','search_box'):
            item=getattr(self,key,None)
            if item is not None and hasattr(item,'setFocus'):item.setFocus();return
        self.show_saves() if hasattr(self,'show_saves') else None
    def import_pc_shortcut(self):
        for key in ('import_pc','show_pc_import','show_pc_discovery'):
            fn=getattr(self,key,None)
            if callable(fn):fn();return
    def _sid(self):
        return self.current['id'] if self.current else None
    def _safe(self,fn):
        try:return fn()
        except Exception as exc:QMessageBox.warning(self,'Operation failed',str(exc));return None
    def pin_current(self):
        sid=self._sid()
        if not sid:return QMessageBox.information(self,'Select a save','Select a save in All Saves first.')
        def work():
            present=any(r['id']==sid for r in self.archive.pinned()['saves'])
            self.archive.pin_save(sid,not present)
            QMessageBox.information(self,'Pinned items','Save '+('unpinned' if present else 'pinned')+'.')
        self._safe(work)
    def show_pinned(self):
        def work():
            p=self.archive.pinned()
            lines=['PINNED SAVES']+[f"{r['platform']} · {r['game']} · {r['label']}" for r in p['saves']]
            lines+=['','PINNED GAMES']+[f"{r['platform']} · {r['game']}" for r in p['games']]
            QMessageBox.information(self,'Pinned library','\n'.join(lines)[:6000])
        self._safe(work)
    def manage_profiles(self):
        sid=self._sid()
        if not sid:return QMessageBox.information(self,'Select a save','Select a save to create or assign its profile.')
        def work():
            r=self.current;platform=r['platform'];game=r['game']
            profiles=self.archive.profiles(platform,game)
            options=['<Create new profile>','<No profile>']+[p['name'] for p in profiles]
            choice,ok=QInputDialog.getItem(self,'Save profiles',f'{platform} · {game}\nSelect a profile:',options,0,False)
            if not ok:return
            if choice=='<Create new profile>':
                name,ok=QInputDialog.getText(self,'New save profile','Name (character or playthrough):')
                if not ok:return
                pid=self.archive.create_profile(platform,game,name)
            elif choice=='<No profile>':pid=None
            else:pid=next(p['id'] for p in profiles if p['name']==choice)
            self.archive.assign_profile(sid,pid)
            QMessageBox.information(self,'Save profile','Profile assignment saved.')
        self._safe(work)
    def show_recovery_center(self):
        def work():
            report=self.archive.recovery()
            lines=[f"Archive issues: {len(report['archive_issues'])}"]+report['archive_issues'][:18]
            lines+=['',f"Recorded operation errors: {len(report['events'])}"]
            lines += [f"{e['happened_at']} · {e['operation']} · {e['error']}" for e in report['events'][:18]]
            QMessageBox.information(self,'Recovery Center','\n'.join(lines)[:8000] or 'No issues')
        self._safe(work)
    def external_export(self):
        folder=QFileDialog.getExistingDirectory(self,'Choose external / destination folder')
        if not folder:return
        if QMessageBox.question(self,'External backup','Create separate ZIP backups for every archived save in this folder?')!=QMessageBox.StandardButton.Yes:return
        def work():
            dest,results=self.archive.external_backup(folder)
            good=sum(r['status']=='ok' for r in results)
            QMessageBox.information(self,'External backup',f'{good}/{len(results)} saves exported to:\n{dest}\nFailures recorded in manifest and Recovery Center.')
        self._safe(work)
    def connections_dialog(self):
        def work():
            connections=self.archive.connections()
            choices=['Add a PS3 connection']+[f"{r['name']} · {r['host']}:{r['port']}" for r in connections]
            selection,ok=QInputDialog.getItem(self,'PS3 Connection Manager','Choose a saved connection:',choices,0,False)
            if not ok:return
            if selection==choices[0]:
                name,ok=QInputDialog.getText(self,'New PS3 connection','Friendly name:')
                if not ok:return
                host,ok=QInputDialog.getText(self,'PS3 address','Local IP or host:')
                if not ok:return
                self.archive.connection_add(name,host)
                return QMessageBox.information(self,'Saved','Connection profile saved without a password.')
            selected=connections[choices.index(selection)-1]
            self.archive.connection_test(selected['id'])
            QMessageBox.information(self,'PS3 connectivity','FTP port is reachable. This does not confirm login or save access.')
        self._safe(work)
    def audit_selected(self):
        sid=self._sid()
        if not sid:return QMessageBox.information(self,'Select save','Select a save first.')
        def work():
            c=self.archive.compatibility(sid);p=self.archive.privacy_audit(sid)
            lines=['Compatibility:']+c['warnings']+['','Potential privacy concerns:']+p
            QMessageBox.information(self,'Compatibility & Privacy Audit','\n• '.join(lines)[:6500])
        self._safe(work)
    def export_catalog(self):
        path,_=QFileDialog.getSaveFileName(self,'Export public verified save catalog','Z_Save_Catalog.html','HTML (*.html)')
        if not path:return
        def work():
            n=self.archive.export_catalog(path)
            QMessageBox.information(self,'Catalog created',f'{n} public verified saves included.\n{path}')
        self._safe(work)
    def show_health(self):
        def work():
            health=self.archive.startup_health()
            QMessageBox.information(self,'Archive health',f"Database: {health['database']}\nFree storage: {health['free_bytes']/1024**3:.1f} GiB\n"+'\n'.join(health['warnings'] or ['No startup warnings']))
        self._safe(work)
    def cloud_guidance(self):
        sid=self._sid()
        if sid:self._safe(lambda:QMessageBox.information(self,'Cloud restore guidance',self.archive.steam_cloud_advice(sid)))

def main():
    app=QApplication(sys.argv);app.setStyle('Fusion');app.setStyleSheet(STYLE)
    home=os.environ.get('Z_ARCHIVE_HOME')
    if home:root=Path(home)
    elif (Path(sys.argv[0]).resolve().parent/'portable.flag').is_file():root=Path(sys.argv[0]).resolve().parent/'ArchiveData'
    else:root=Path.home()/'Documents'/'Z PlayStation Save Archive'
    win=Window(root);win.show();sys.exit(app.exec())
