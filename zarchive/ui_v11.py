"""v1.1 UI extension; inherits v1.0 functionality."""
import os,sys
from pathlib import Path
from PySide6.QtWidgets import QApplication,QInputDialog,QMessageBox,QFileDialog
from .ui_v10 import Window as BaseWindow
from .ui_v04 import STYLE

class Window(BaseWindow):
    def __init__(self,root):
        super().__init__(root)
        self.setWindowTitle("Z's Save Archive  •  PS3 + PC  v1.1")
        menu=self.tools_btn.menu();menu.addSeparator()
        for name,action in [('Create save variant',self.variant_ui),('Set game completion',self.completion_ui),('Compare two saves',self.compare_ui),('Bulk metadata editor',self.bulk_ui),('Undo last bulk edit',self.undo_ui),('PC snapshot folders',self.watch_ui),('GitHub Pages catalog',self.pages_ui),('GitHub draft release',self.github_ui),('Upload selected save to GitHub release',self.github_upload_ui)]:
            menu.addAction(name,action)
    def variant_ui(self):
        sid=self._sid()
        if not sid:return
        def work():
            r=self.archive._save(sid)
            name,ok=QInputDialog.getText(self,'New variant','Variant (Starter, 100%, Modified):')
            if ok and name.strip():
                vid=self.archive.create_variant(r['platform'],r['game'],name)
                self.archive.assign_variant(sid,vid)
        self._safe(work)
    def completion_ui(self):
        sid=self._sid()
        if not sid:return
        def work():
            r=self.archive._save(sid)
            val,ok=QInputDialog.getItem(self,'Completion','Progress:', ['Untouched','In Progress','Completed'],0,False)
            if ok:self.archive.set_game_progress(r['platform'],r['game'],val)
        self._safe(work)
    def compare_ui(self):
        sid=self._sid()
        if not sid:return
        def work():
            current=self.archive._save(sid)
            options=[r for r in self.archive.list_saves() if r['id']!=sid and r['game']==current['game'] and r['platform']==current['platform']]
            if not options:return QMessageBox.information(self,'Compare','Import a second save for this game first.')
            labels=[r['label']+' ('+r['id'][:8]+')' for r in options]
            val,ok=QInputDialog.getItem(self,'Compare snapshots','Compare to:',labels,0,False)
            if ok:
                result=self.archive.save_diff(sid,options[labels.index(val)]['id'])
                QMessageBox.information(self,'Save changes',str(result)[:5000])
        self._safe(work)
    def bulk_ui(self):
        sid=self._sid()
        if not sid:return QMessageBox.information(self,'Bulk edit','Select a save first; this tool edits saves from the same game.')
        def work():
            r=self.archive._save(sid)
            ids=[x['id'] for x in self.archive.list_saves() if x['game']==r['game'] and x['platform']==r['platform']]
            cat,ok=QInputDialog.getItem(self,'Bulk edit','Set category for '+str(len(ids))+' saves:', ['Legit','Modded','Unsorted'],0,False)
            if ok and QMessageBox.question(self,'Confirm',f'Change category on {len(ids)} saves?')==QMessageBox.StandardButton.Yes:
                op=self.archive.bulk_metadata(ids,category=cat)
                self.refresh();QMessageBox.information(self,'Done','Recorded reversible operation '+op[:8])
        self._safe(work)
    def undo_ui(self):
        def work():
            opts=[r for r in self.archive.recent_metadata_operations() if not r['undone']]
            if not opts:return
            if QMessageBox.question(self,'Undo','Undo the most recent bulk metadata operation?')==QMessageBox.StandardButton.Yes:
                self.archive.undo_metadata(opts[0]['id']);self.refresh()
        self._safe(work)
    def watch_ui(self):
        def work():
            choices=['Add PC save folder','Scan registered folders now']
            val,ok=QInputDialog.getItem(self,'PC snapshots','Choose action:',choices,0,False)
            if not ok:return
            if val==choices[0]:
                path=QFileDialog.getExistingDirectory(self,'Choose PC save directory')
                if not path:return
                game,ok=QInputDialog.getText(self,'Save game','Game title:')
                if ok and game.strip():self.archive.watch_folder_add(game,path)
            else:
                report=self.archive.scan_watch_folders()
                QMessageBox.information(self,'Snapshot scan',str(report)[:6000]);self.refresh()
        self._safe(work)
    def pages_ui(self):
        def work():
            parent=QFileDialog.getExistingDirectory(self,'Choose an output parent directory')
            if not parent:return
            path=self.archive.github_pages_catalog(Path(parent)/'Z_Save_Public_Catalog')
            QMessageBox.information(self,'Catalog created',f'{path}\nUpload this folder to GitHub Pages manually after review.')
        self._safe(work)
    def github_upload_ui(self):
        sid=self._sid()
        if not sid:return QMessageBox.information(self,'Choose save','Select a verified Public save first.')
        def work():
            repo,ok=QInputDialog.getText(self,'GitHub','Owner/repository:')
            if not ok:return
            rel,ok=QInputDialog.getInt(self,'GitHub','Existing release ID:',1,1,2147483647)
            if not ok:return
            alerts=self.archive.privacy_audit(sid)
            description='\n'.join(alerts[:12]) if alerts else 'No filename warnings detected; inspect the actual save for identifiers.'
            if QMessageBox.question(self,'Privacy review required',description+'\n\nHave you independently reviewed this save and approved uploading it?')!=QMessageBox.StandardButton.Yes:return
            owner,name=repo.split('/',1)
            result=self.archive.github_upload_verified_save(owner,name,rel,sid,reviewed=True)
            QMessageBox.information(self,'GitHub asset uploaded',str(result))
        self._safe(work)
    def github_ui(self):
        def work():
            repo,ok=QInputDialog.getText(self,'GitHub','Owner/repository (e.g. account/save-packs):')
            if not ok:return
            tag,ok=QInputDialog.getText(self,'GitHub','Release tag:')
            if not ok:return
            name,ok=QInputDialog.getText(self,'GitHub','Release name:')
            if not ok:return
            if QMessageBox.question(self,'GitHub draft','Create a DRAFT release online? No files will be uploaded.')!=QMessageBox.StandardButton.Yes:return
            owner,repo=repo.split('/',1)
            result=self.archive.github_publish_draft(owner,repo,tag,name)
            QMessageBox.information(self,'Draft created',str(result))
        self._safe(work)

def main():
    app=QApplication(sys.argv);app.setStyle('Fusion');app.setStyleSheet(STYLE)
    home=os.environ.get('Z_ARCHIVE_HOME')
    if home:root=Path(home)
    elif (Path(sys.argv[0]).resolve().parent/'portable.flag').is_file():root=Path(sys.argv[0]).resolve().parent/'ArchiveData'
    else:root=Path.home()/'Documents'/'Z PlayStation Save Archive'
    win=Window(root);win.show();sys.exit(app.exec())
