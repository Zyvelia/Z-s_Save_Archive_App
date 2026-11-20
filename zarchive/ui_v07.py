"""v0.7 workflow improvements with all previous GUI functions retained."""
from __future__ import annotations
import os,sys
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication,QFileDialog,QMessageBox,QDialog,QVBoxLayout,QListWidget,
    QListWidgetItem,QPushButton,QLabel,QHBoxLayout)
from .ui_v06 import Window as PreviousWindow,FTPBrowser as PreviousFTPBrowser,TransferWorker as PreviousWorker
from .ui_v04 import STYLE
from .workflows_v07 import discover_game_locations,download_with_retry,export_many
from .transfer_v06 import pc_save_candidates
from .integrations import steam_games

class TransferWorker(PreviousWorker):
    def run(self):
        try:
            for path in self.paths:
                if self.cancelled:break
                try:
                    result=download_with_retry(self.api,path,self.archive,
                        progress=lambda size,name:self.progress.emit(path,size,name),
                        cancel=lambda:self.cancelled, max_attempts=3,
                        notify=lambda attempt,reason:self.progress.emit(path,0,f'Retrying {attempt}/2 after {reason[:60]}'))
                    self.complete.emit(path,result,'')
                except Exception as exc:self.complete.emit(path,None,str(exc))
        finally:self.finished.emit()

# Replace worker in existing dialog's module globals; original connection handling is preserved.
from . import ui_v06
ui_v06.TransferWorker=TransferWorker

class Window(PreviousWindow):
    def __init__(self,root):
        super().__init__(root)
        self.setWindowTitle("Z's Save Archive  •  PS3 + PC  v0.7")
        self.statusBar().showMessage('v0.7 · safer batch releases, PC hints, FTP retry')
        self.tools_btn.menu().addAction('Batch Release ZIPs',self.batch_release)

    def batch_release(self):
        ids=self.selected_ids()
        if not ids:
            QMessageBox.information(self,'Batch release','Select saves in All Saves first (Ctrl/Shift-click).');return
        dest=QFileDialog.getExistingDirectory(self,'Select release output folder')
        if not dest:return
        if QMessageBox.question(self,'Batch release',f'Export {len(ids)} selected saves? Only Public + Verified saves will export. Existing ZIPs will not be overwritten.')!=QMessageBox.StandardButton.Yes:return
        try:
            results,manifest=export_many(self.archive,ids,Path(dest))
            ok=sum(r['status']=='exported' for r in results)
            QMessageBox.information(self,'Batch release result',f'{ok}/{len(results)} exported.\nManifest: {manifest}\nSkipped: '+', '.join(r.get('game',r['id'][:8]) for r in results if r['status']!='exported')[:450])
        except Exception as exc:QMessageBox.warning(self,'Batch export failed',str(exc))

    def show_pc_discovery(self):
        dialog=QDialog(self);dialog.resize(780,520);dialog.setWindowTitle('Discover PC Save Locations')
        lay=QVBoxLayout(dialog)
        lay.addWidget(QLabel('Game-specific hints are candidates, not verified saves. Select an individual game folder before importing.'))
        rows=QListWidget();lay.addWidget(rows)
        candidates=discover_game_locations(games=steam_games())
        roots=pc_save_candidates()
        for entry in candidates+roots:
            item=QListWidgetItem(f"{entry['name']}  ·  {entry['path']}  [{entry['certainty']}]")
            item.setData(Qt.ItemDataRole.UserRole,entry['path']);rows.addItem(item)
        lay.addWidget(QLabel(f'{len(candidates)} game-specific candidates · {len(roots)} common roots'))
        bar=QHBoxLayout();openbtn=QPushButton('Open in Explorer');closebtn=QPushButton('Close')
        bar.addWidget(openbtn);bar.addWidget(closebtn);lay.addLayout(bar)
        def open_folder():
            it=rows.currentItem()
            if it:
                from PySide6.QtGui import QDesktopServices
                from PySide6.QtCore import QUrl
                QDesktopServices.openUrl(QUrl.fromLocalFile(it.data(Qt.ItemDataRole.UserRole)))
        openbtn.clicked.connect(open_folder);closebtn.clicked.connect(dialog.accept)
        dialog.exec()

def main():
    app=QApplication(sys.argv);app.setStyle('Fusion');app.setStyleSheet(STYLE)
    home=os.environ.get('Z_ARCHIVE_HOME')
    if home:root=Path(home)
    elif (Path(sys.argv[0]).resolve().parent/'portable.flag').is_file():root=Path(sys.argv[0]).resolve().parent/'ArchiveData'
    else:root=Path.home()/'Documents'/'Z PlayStation Save Archive'
    win=Window(root);win.show();sys.exit(app.exec())
