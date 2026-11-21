"""Conservative v1.2 inspection actions; all save operations remain opt-in."""
from pathlib import Path
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox
from .ui_v11 import Window as BaseWindow
from .upgrade_v12 import WORKFLOW_STATES

class Window(BaseWindow):
    def __init__(self,root):
        super().__init__(root)
        self.setWindowTitle("Z's Save Archive  •  PS3 + PC  v1.2")
        menu=self.tools_btn.menu();menu.addSeparator()
        for title,func in [('Set workflow status',self.workflow_ui),('Archive storage report',self.storage_ui),('Inspect PS3 PARAM.SFO',self.sfo_ui),('Check restore destination',self.conflict_ui)]:
            menu.addAction(title,func)
    def workflow_ui(self):
        sid=self._sid()
        if not sid:return
        def work():
            state,ok=QInputDialog.getItem(self,'Workflow status','Status:',list(WORKFLOW_STATES),0,False)
            if ok:self.archive.set_workflow_state(sid,state);QMessageBox.information(self,'Saved',f'Workflow status: {state}')
        self._safe(work)
    def storage_ui(self):
        self._safe(lambda:QMessageBox.information(self,'Archive storage',str(self.archive.storage_report())[:7000]))
    def sfo_ui(self):
        sid=self._sid()
        if sid:self._safe(lambda:QMessageBox.information(self,'PS3 metadata',str(self.archive.ps3_sfo(sid))[:7000]))
    def conflict_ui(self):
        sid=self._sid()
        if not sid:return
        def work():
            dest=QFileDialog.getExistingDirectory(self,'Choose parent folder to inspect')
            if dest:
                target=Path(dest)/('Restore_'+sid[:8])
                QMessageBox.information(self,'Restore preflight',str(self.archive.restore_conflict_check(sid,target)))
        self._safe(work)


def main():
    import os,sys
    from PySide6.QtWidgets import QApplication
    from .ui_v04 import STYLE
    app=QApplication(sys.argv);app.setStyle('Fusion');app.setStyleSheet(STYLE)
    home=os.environ.get('Z_ARCHIVE_HOME')
    if home:root=Path(home)
    elif (Path(sys.argv[0]).resolve().parent/'portable.flag').is_file():root=Path(sys.argv[0]).resolve().parent/'ArchiveData'
    else:root=Path.home()/'Documents'/'Z PlayStation Save Archive'
    win=Window(root);win.show();sys.exit(app.exec())
