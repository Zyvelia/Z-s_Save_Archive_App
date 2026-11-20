"""v1.3 optional PC tools layered on existing v1.2 interface."""
from __future__ import annotations
import json, os, sys
from pathlib import Path
from PySide6.QtWidgets import QApplication,QFileDialog,QInputDialog,QMessageBox
from .ui_v12 import Window as BaseWindow
from .ui_v04 import STYLE

class Window(BaseWindow):
    def __init__(self,root):
        super().__init__(root)
        self.setWindowTitle("Z's Save Archive  •  PS3 + PC  v1.3")
        menu=self.tools_btn.menu();menu.addSeparator()
        for label,action in [
            ('PC discovery: Steam / Epic / GOG / Xbox',self.discovery_ui),
            ('Find known PC save directories',self.candidates_ui),
            ('Register custom PC game path',self.custom_path_ui),
            ('Import community game path definitions',self.definitions_ui),
            ('Configure PC backup rule',self.rule_ui),
            ('Run enabled PC backup rules once',self.run_rules_ui),
            ('Verify archived saves',self.verify_ui),
            ('Create verified external archive mirror',self.mirror_ui),
            ('Check existing archive mirror',self.check_mirror_ui),
            ('Review cloud restore warnings',self.cloud_ui),
            ('Archive/database health',self.health_v13_ui),
            ('Save timeline',self.timeline_ui),
            ('Find exact duplicate hashes',self.duplicates_ui),
            ('Suggest name for selected save',self.smart_name_ui),
            ('Search all save metadata',self.search_ui),
        ]:menu.addAction(label,action)
    def _report(self,title,data):
        QMessageBox.information(self,title,json.dumps(data,indent=2,ensure_ascii=False,default=str)[:14000])
    def discovery_ui(self):
        def f():
            choice,ok=QInputDialog.getItem(self,'PC game discovery','Source:', ['Steam','Epic Games','GOG Galaxy','Xbox / Microsoft Store'],0,False)
            if not ok:return
            method={'Steam':self.archive.steam_installations,'Epic Games':self.archive.epic_installations,'GOG Galaxy':self.archive.gog_installations,'Xbox / Microsoft Store':self.archive.xbox_candidates}[choice]
            self._report(choice,method())
        self._safe(f)
    def candidates_ui(self):self._safe(lambda:self._report('Known save-location candidates',[r for r in self.archive.candidate_paths() if r['exists']]))
    def custom_path_ui(self):
        def f():
            path=QFileDialog.getExistingDirectory(self,'Choose a game or save folder')
            if not path:return
            game,ok=QInputDialog.getText(self,'Custom game','Game name:')
            if ok and game.strip():self.archive.add_game_path(game,path);self._report('Game path registered',self.archive.game_paths())
        self._safe(f)
    def definitions_ui(self):
        def f():
            path,_=QFileDialog.getOpenFileName(self,'Import local JSON definition file','','JSON Files (*.json)')
            if path:self._report('Definitions',{'definitions_accepted':self.archive.import_location_definitions(path)})
        self._safe(f)
    def rule_ui(self):
        def f():
            choices=list(self.archive.conn.execute('SELECT id,game,path FROM local_watch_folders ORDER BY game'))
            if not choices:return QMessageBox.information(self,'PC backups','Register a PC snapshot folder first under Tools → PC snapshot folders.')
            labels=[str(r['game'])+' — '+str(r['path']) for r in choices]
            choice,ok=QInputDialog.getItem(self,'PC backup rule','Folder:',labels,0,False)
            if not ok:return
            interval,ok=QInputDialog.getInt(self,'Minimum interval','Seconds between snapshots (minimum 60):',300,60,2592000)
            if not ok:return
            if QMessageBox.question(self,'Enable backup rule','Enable this rule? It only runs when you choose Run backup rules.')!=QMessageBox.StandardButton.Yes:return
            watch=choices[labels.index(choice)]
            self.archive.configure_backup_rule(watch['id'],enabled=True,min_interval=interval)
            self._report('Backup rules',self.archive.backup_rules())
        self._safe(f)
    def run_rules_ui(self):
        def f():
            if QMessageBox.question(self,'PC backup rules','Scan enabled folders now and import changed saves?')!=QMessageBox.StandardButton.Yes:return
            self._report('PC backup results',self.archive.run_backup_rules());self.refresh()
        self._safe(f)
    def verify_ui(self):self._safe(lambda:self._report('Archive checksum validation',self.archive.verify_all_saves()))
    def mirror_ui(self):
        def f():
            parent=QFileDialog.getExistingDirectory(self,'Choose destination parent (prefer another drive)')
            if not parent:return
            dest=Path(parent)/('Z_Save_Archive_Mirror_'+__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S'))
            if QMessageBox.question(self,'Create full mirror',f'Copy complete archive to new folder?\n{dest}\nThis may take significant disk space.')!=QMessageBox.StandardButton.Yes:return
            self._report('Archive mirror created',self.archive.mirror_archive(dest))
        self._safe(f)
    def check_mirror_ui(self):
        def f():
            parent=QFileDialog.getExistingDirectory(self,'Choose existing mirror directory')
            if parent:self._report('Mirror validation',self.archive.verify_mirror(parent))
        self._safe(f)
    def cloud_ui(self):
        def f():
            path=QFileDialog.getExistingDirectory(self,'Choose local save restore destination')
            if path:self._report('Cloud warnings',self.archive.cloud_restore_warning(path))
        self._safe(f)
    def timeline_ui(self):self._safe(lambda:self._report('Recent save timeline',self.archive.save_timeline()))
    def duplicates_ui(self):self._safe(lambda:self._report('Exact duplicate hashes',self.archive.duplicate_candidates()))
    def smart_name_ui(self):
        sid=self._sid()
        if sid:self._safe(lambda:self._report('Suggested save label',{'label':self.archive.smart_save_name(sid)}))
    def search_ui(self):
        def f():
            query,ok=QInputDialog.getText(self,'Search archive','Game, ID, label, note or tag:')
            if ok and query.strip():self._report('Search results',self.archive.universal_search(query))
        self._safe(f)
    def health_v13_ui(self):self._safe(lambda:self._report('Archive health',self.archive.archive_health()))

def main():
    app=QApplication(sys.argv);app.setStyle('Fusion');app.setStyleSheet(STYLE)
    home=os.environ.get('Z_ARCHIVE_HOME')
    if home:root=Path(home)
    elif (Path(sys.argv[0]).resolve().parent/'portable.flag').is_file():root=Path(sys.argv[0]).resolve().parent/'ArchiveData'
    else:root=Path.home()/'Documents'/'Z PlayStation Save Archive'
    win=Window(root);win.show();sys.exit(app.exec())
