"""Universal save editing workspace; original archive is immutable."""
from __future__ import annotations
import os,sys,json
from pathlib import Path
from PySide6.QtWidgets import (QApplication,QDialog,QVBoxLayout,QHBoxLayout,QLabel,QListWidget,
    QPushButton,QFileDialog,QMessageBox,QComboBox,QLineEdit,QFormLayout,QInputDialog,QScrollArea,QWidget)
from .ui_v17 import Window as BaseWindow
from .ui_v04 import STYLE
from .editor_v18 import ArchiveV18
from .game_targets_v19 import GAME_TARGETS, matching_saves, target_by_id, builtin_target
from .ui_bl3_native import BL3NativeDialog

class EditorWorkspace(QDialog):
    def __init__(self,archive,parent=None):
        super().__init__(parent);self.archive=archive;self.setWindowTitle('Universal Save Editor');self.resize(1050,740)
        outer=QVBoxLayout(self)
        self.legacy_container=QWidget(self)
        layout=QVBoxLayout(self.legacy_container)
        outer.addWidget(self.legacy_container,1)
        layout.addWidget(QLabel('Select a game target and an archived save. Planned game placeholders cannot edit files. Decrypt PS3 payloads with Apollo first.'))
        targets=QHBoxLayout();layout.addLayout(targets);targets.addWidget(QLabel('Game target:'))
        self.game_target=QComboBox();self.game_target.addItem('All archived games / installed definitions',None)
        for g in GAME_TARGETS:self.game_target.addItem(f"{g['name']} · {g['status']}",g['id'])
        targets.addWidget(self.game_target,1)
        self.target_info=QLabel('Only installed, validated editor definitions enable editing.');self.target_info.setWordWrap(True)
        layout.addWidget(self.target_info)
        bar=QHBoxLayout();layout.addLayout(bar)
        self.query=QLineEdit();self.query.setPlaceholderText('Search archived games and saves');bar.addWidget(self.query)
        self.import_btn=QPushButton('Import editor definition…');bar.addWidget(self.import_btn)
        self.saves=QListWidget();layout.addWidget(self.saves)
        opts=QHBoxLayout();layout.addLayout(opts)
        opts.addWidget(QLabel('Game-specific editor:'))
        self.plugin=QComboBox();opts.addWidget(self.plugin,1)
        self.inspect=QPushButton('Inspect fields');opts.addWidget(self.inspect)
        self.folder=QLineEdit();self.folder.setPlaceholderText('Optional: decrypted PS3 save folder, or external PC working copy');layout.addWidget(self.folder)
        row=QHBoxLayout();layout.addLayout(row);btn=QPushButton('Choose decrypted folder…');row.addWidget(btn)
        btn.clicked.connect(self.choose_folder)
        row.addWidget(QLabel('Blank = archived save (read-only source)'));row.addStretch()
        self.container=QWidget();self.form=QFormLayout(self.container)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(self.container);layout.addWidget(scroll,1)
        self.fields={};self.current_inspection=None
        footer=QHBoxLayout();layout.addLayout(footer)
        self.export=QPushButton('Create verified backup + export edited copy…');self.export.setEnabled(False);footer.addWidget(self.export)
        footer.addStretch();close=QPushButton('Close');close.clicked.connect(self.reject);footer.addWidget(close)
        self.game_target.currentIndexChanged.connect(self.refresh_saves);self.query.textChanged.connect(self.refresh_saves);self.saves.currentRowChanged.connect(self.refresh_editors)
        self.import_btn.clicked.connect(self.import_editor);self.inspect.clicked.connect(self.inspect_fields);self.export.clicked.connect(self.export_copy)
        # Functional built-in game editors share this same workspace.
        # The legacy declarative editor remains available for other games.
        self.native = BL3NativeDialog(self.archive.root, self, embedded=True)
        outer.addWidget(self.native, 1)
        self.native.hide()
        self.builtin_footer = QWidget(self)
        builtin_actions=QHBoxLayout(self.builtin_footer)
        builtin_actions.addStretch()
        builtin_close=QPushButton('Close')
        builtin_close.clicked.connect(self.reject)
        builtin_actions.addWidget(builtin_close)
        outer.addWidget(self.builtin_footer)
        self.builtin_footer.hide()
        self._shown_builtin = None
        self.refresh_saves()

    def refresh_mode(self):
        target_id=self.game_target.currentData()
        builtin=builtin_target(target_id)
        if builtin and self._shown_builtin != target_id:
            self.native.set_target(*builtin)
        self._shown_builtin=target_id if builtin else None
        self.native.setVisible(bool(builtin))
        self.builtin_footer.setVisible(bool(builtin))
        self.legacy_container.setVisible(not bool(builtin))

    def selected(self):
        item=self.saves.currentItem();return item.data(0x0100) if item else None
    def refresh_saves(self):
        selected=self.selected();self.saves.clear()
        rows=self.archive.list_saves(query=self.query.text())[:2000]
        target_id=self.game_target.currentData()
        if target_id:rows=matching_saves(rows,target_id)
        for row in rows:
            from PySide6.QtWidgets import QListWidgetItem
            item=QListWidgetItem(f"{row['game']}  ·  {row['label']}  [{row['platform']}]  {row['title_id']}")
            item.setData(0x0100,row);self.saves.addItem(item)
            if selected and row['id']==selected['id']:self.saves.setCurrentItem(item)
        if self.saves.count() and self.saves.currentRow()<0:self.saves.setCurrentRow(0)
        self.refresh_editors()
        target=target_by_id(target_id)
        if target and builtin_target(target_id):
            self.target_info.setText(f"{target['name']} · {target['platform']} · Built-in editor available.")
        elif target:
            self.target_info.setText(f"{target['name']} · {target['status']}. Needed: {target['sample']}. This is a placeholder, NOT a functional game editor.")
        else:self.target_info.setText('Select an archived save and a matching installed definition. No PS3 game editor is bundled.')
        self.refresh_mode()
    def refresh_editors(self,*_):
        self.plugin.clear();self.clear_fields()
        r=self.selected()
        if r:
            for p in self.archive.editors(r['game'],r['platform']):self.plugin.addItem(p['name'],p['id'])
    def clear_fields(self):
        while self.form.rowCount():self.form.removeRow(0)
        self.fields={};self.current_inspection=None;self.export.setEnabled(False)
    def choose_folder(self):
        path=QFileDialog.getExistingDirectory(self,'Select decrypted save working folder')
        if path:self.folder.setText(path)
    def import_editor(self):
        path=QFileDialog.getOpenFileName(self,'Select declarative editor definition','','JSON (*.json)')[0]
        if not path:return
        try:
            if Path(path).stat().st_size>65536:raise ValueError('Definition too large')
            plugin=json.loads(Path(path).read_text(encoding='utf-8'))
            self.archive.install_editor(plugin);self.refresh_editors()
            QMessageBox.information(self,'Editor registered','Definition registered. No external code was executed.')
        except Exception as ex:QMessageBox.warning(self,'Editor rejected',str(ex))
    def inspect_fields(self):
        self.clear_fields();r=self.selected();pid=self.plugin.currentData()
        if not r or not pid:return QMessageBox.information(self,'No editor','Select a save and a matching editor definition first.')
        try:
            inspected=self.archive.inspect_editor(r['id'],pid,self.folder.text().strip() or None)
            self.current_inspection=inspected
            for spec in inspected['plugin']['fields']:
                current=inspected['values'][spec['key']]
                edit=QLineEdit('true' if current is True else 'false' if current is False else str(current))
                self.form.addRow(f"{spec['key']} ({spec['type']})",edit);self.fields[spec['key']]=(edit,spec)
            self.export.setEnabled(True)
        except Exception as ex:QMessageBox.warning(self,'Cannot inspect save',str(ex))
    def export_copy(self):
        if not self.current_inspection:return
        i=self.current_inspection;changes={}
        try:
            for key,(widget,spec) in self.fields.items():
                raw=widget.text()
                if spec['type']=='integer':v=int(raw)
                elif spec['type']=='boolean':
                    if raw.lower() not in ('true','false'):raise ValueError(key+' must be true or false')
                    v=raw.lower()=='true'
                else:v=raw
                if v!=i['values'][key]:changes[key]=v
            if not changes:raise ValueError('No changes to export')
            path=QFileDialog.getExistingDirectory(self,'Select parent folder for NEW edited save')
            if not path:return
            name,ok=QInputDialog.getText(self,'Output directory name','New folder name:',text='Edited_Save')
            if not ok:return
            if not name or name in ('.','..') or '/' in name or '\\' in name:raise ValueError('Invalid output name')
            target=Path(path)/name
            if QMessageBox.question(self,'Confirm safe edit',f"Create a verified original backup and export a NEW edited copy to:\n{target}\n\nThe archived save will not be changed.")!=QMessageBox.StandardButton.Yes:return
            result=self.archive.edit_copy(i['save_id'],i['plugin']['id'],changes,target,self.folder.text().strip() or None)
            QMessageBox.information(self,'Edited copy exported',f"Backup: {result['backup']}\nEdited copy: {result['output']}\n\nFor PS3, test the copy and re-sign or encrypt using Apollo when required.")
        except Exception as ex:QMessageBox.warning(self,'Export failed',str(ex))

class Window(BaseWindow):
    def __init__(self,root):
        super().__init__(root);self.setWindowTitle("Z's Save Archive  •  PS3 + PC  v1.9")
        self.tools_btn.menu().addSeparator();self.tools_btn.menu().addAction('Universal Save Editor (game targets + safe copy)',self.editor_ui)
    def editor_ui(self):EditorWorkspace(self.archive,self).exec()

def main():
    from . import ui
    ui.Archive=ArchiveV18
    app=QApplication(sys.argv);app.setStyle('Fusion');app.setStyleSheet(STYLE)
    home=os.environ.get('Z_ARCHIVE_HOME')
    if home:root=Path(home)
    elif (Path(sys.argv[0]).resolve().parent/'portable.flag').is_file():root=Path(sys.argv[0]).resolve().parent/'ArchiveData'
    else:root=Path.home()/'Documents'/'Z PlayStation Save Archive'
    window=Window(root);window.show();sys.exit(app.exec())
