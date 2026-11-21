"""Optional desktop publishing center. Every GitHub write needs confirmation."""
from __future__ import annotations
import json,os,sys
from pathlib import Path
from PySide6.QtWidgets import (QApplication,QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
 QLineEdit,QTextEdit,QInputDialog,QMessageBox,QFileDialog,QCheckBox)
from .ui_v14 import Window as BaseWindow
from .ui_v04 import STYLE

class PublisherDialog(QDialog):
    def __init__(self,archive,parent=None):
        super().__init__(parent);self.archive=archive;self.setWindowTitle('GitHub Publishing Center — Manual approvals');self.resize(780,580)
        layout=QVBoxLayout(self);layout.addWidget(QLabel('GitHub publishing is optional. Drafts and uploads require separate confirmation.'))
        row=QHBoxLayout();layout.addLayout(row)
        self.owner=QLineEdit();self.owner.setPlaceholderText('GitHub owner');row.addWidget(self.owner)
        self.repo=QLineEdit();self.repo.setPlaceholderText('Repository');row.addWidget(self.repo)
        previous=self.archive.publishing_repo()
        if '/' in previous:a,b=previous.split('/',1);self.owner.setText(a);self.repo.setText(b)
        self.tag=QLineEdit();self.tag.setPlaceholderText('Release tag, e.g. savepack-v1');layout.addWidget(self.tag)
        self.name=QLineEdit();self.name.setPlaceholderText('Release display name');layout.addWidget(self.name)
        self.release=QLineEdit();self.release.setPlaceholderText('Existing GitHub release numeric ID (for uploading)');layout.addWidget(self.release)
        self.approved=QCheckBox('I reviewed the selected save for private or account-linked data');layout.addWidget(self.approved)
        bar=QHBoxLayout();layout.addLayout(bar)
        for title,method in [('Save repository',self.set_repo),('Create DRAFT',self.draft),('Upload selected save',self.upload),('Export website',self.website),('History',self.history)]:
            button=QPushButton(title);button.clicked.connect(method);bar.addWidget(button)
        self.log=QTextEdit();self.log.setReadOnly(True);layout.addWidget(self.log)
        layout.addWidget(QLabel('GitHub token: set GITHUB_TOKEN in your Windows environment; the app never saves it.'))
    def run_safe(self,fn):
        try:result=fn();self.log.setPlainText(json.dumps(result,indent=2,default=str,ensure_ascii=False)[:16000]);return result
        except Exception as exc:QMessageBox.warning(self,'Publisher error',str(exc));return None
    def owner_repo(self):return self.owner.text().strip(),self.repo.text().strip()
    def set_repo(self):return self.run_safe(lambda:{'repository':self.archive.set_publishing_repo(*self.owner_repo())})
    def draft(self):
        def go():
            owner,repo=self.owner_repo();tag=self.tag.text().strip();name=self.name.text().strip()
            self.archive.github_release_payload(tag,name)
            if QMessageBox.question(self,'Create GitHub draft',f'Create a draft release in {owner}/{repo}? No files will be uploaded.')!=QMessageBox.StandardButton.Yes:return {'cancelled':True}
            result=self.archive.create_publisher_draft(owner,repo,tag,name)
            self.release.setText(str(result['id']));return result
        return self.run_safe(go)
    def upload(self):
        def go():
            sid=getattr(self.parent(),'_sid')()
            if not sid:raise ValueError('Select a save in All Saves before opening the publisher')
            report=self.archive.publication_preflight(sid,privacy_reviewed=self.approved.isChecked())
            if not report['ready']:raise ValueError('; '.join(report['errors']))
            owner,repo=self.owner_repo();rid=int(self.release.text().strip())
            message=f"Upload {report['game']} — {report['label']} to {owner}/{repo} release {rid}?\n\n"+('\n'.join(report['warnings']) or 'No additional warnings')
            if QMessageBox.question(self,'Final upload confirmation',message)!=QMessageBox.StandardButton.Yes:return {'cancelled':True}
            return self.archive.upload_publisher_save(owner,repo,rid,sid,tag=self.tag.text().strip(),privacy_reviewed=True)
        return self.run_safe(go)
    def website(self):
        def go():
            dest=QFileDialog.getExistingDirectory(self,'Choose a parent folder for NEW website directory')
            if not dest:return {'cancelled':True}
            folder=Path(dest)/'Z_Save_Public_Catalog'
            return self.archive.export_public_site(folder)
        return self.run_safe(go)
    def history(self):return self.run_safe(self.archive.publication_history)

class Window(BaseWindow):
    def __init__(self,root):
        super().__init__(root);self.setWindowTitle("Z's Save Archive  •  PS3 + PC  v1.5")
        menu=self.tools_btn.menu();menu.addSeparator()
        menu.addAction('GitHub Publishing Center',self.publisher_ui)
        menu.addAction('GitHub Manager', self.github_manager_ui)
        menu.addAction('Pre-release validation for selected save',self.preflight_ui)
        menu.addAction('Generate public website',self.website_ui)
    def github_manager_ui(self):
        from .ui_github_manager import GitHubManagerDialog
        GitHubManagerDialog(self.archive, self).exec()
    def publisher_ui(self):self._safe(lambda:PublisherDialog(self.archive,self).exec())
    def preflight_ui(self):
        sid=self._sid()
        if not sid:return QMessageBox.information(self,'Select a save','Select a save in All Saves')
        self._safe(lambda:self._report('Pre-release validation',self.archive.publication_preflight(sid)))
    def website_ui(self):
        def go():
            directory=QFileDialog.getExistingDirectory(self,'Select parent folder for new public catalog')
            if directory:self._report('Public website',self.archive.export_public_site(Path(directory)/'Z_Save_Public_Catalog'))
        self._safe(go)

def main():
    app=QApplication(sys.argv);app.setStyle('Fusion');app.setStyleSheet(STYLE)
    home=os.environ.get('Z_ARCHIVE_HOME')
    if home:root=Path(home)
    elif (Path(sys.argv[0]).resolve().parent/'portable.flag').is_file():root=Path(sys.argv[0]).resolve().parent/'ArchiveData'
    else:root=Path.home()/'Documents'/'Z PlayStation Save Archive'
    win=Window(root);win.show();sys.exit(app.exec())
