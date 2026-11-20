"""v2.4 homebrew inventory, release notes, package inspector and installation checklist UI."""
from __future__ import annotations
import os,sys
from pathlib import Path
from PySide6.QtWidgets import (QApplication,QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
 QTableWidget,QTableWidgetItem,QHeaderView,QWidget,QPlainTextEdit,QLineEdit,QCheckBox,QMessageBox,QFileDialog)
from .ui_v23 import Window as V23Window,HomebrewCenter as V23Center
from .ui_v04 import STYLE
from .editor_v18 import ArchiveV18
from .homebrew_v24 import (set_app_record,read_app_records,offline_catalog,batch_inspect_pkgs,
  installation_checklist,release_note_text,update_compatibility_record)
from .homebrew_v23 import catalog_items,select_newest

class HomebrewCenter(V23Center):
    def __init__(self,parent=None,root=None):
        super().__init__(parent,root)
        self.setWindowTitle('PS3 Homebrew Manager • v2.4')
        self.resize(1080,770)
        self.records_file=self.root/'homebrew'/'installed_inventory.json'
        self.catalog_cache=self.root/'homebrew'/'offline_catalog.json'
        offline_catalog(self.catalog_cache,refresh=not self.catalog_cache.exists())
        self._inventory_page();self._inspector_page()
        self._download_controls()
        button=QPushButton('View selected release notes')
        button.clicked.connect(self.show_release_notes)
        self.tabs.widget(1).layout().addWidget(button)

    def _download_controls(self):
        bar=QHBoxLayout()
        bar.addWidget(QLabel("Optional download limit (KiB/s, 0 = unlimited):"))
        self.bandwidth_kib=QLineEdit("0")
        self.bandwidth_kib.setMaximumWidth(100)
        self.bandwidth_kib.setToolTip("Limits the network download; not PS3 FTP upload speed")
        bar.addWidget(self.bandwidth_kib)
        bar.addStretch()
        self.queue_tab.layout().insertLayout(1,bar)

    def _inventory_page(self):
        tab=QWidget();layout=QVBoxLayout(tab)
        layout.addWidget(QLabel('Installed versions are manually entered. No installed PS3 application scan occurs.'))
        self.inventory_table=QTableWidget(0,4)
        self.inventory_table.setHorizontalHeaderLabels(['Homebrew','Installed version (manual)','Favorite','Watch'])
        self.inventory_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.inventory_table)
        row=QHBoxLayout();layout.addLayout(row)
        self.version_entry=QLineEdit();self.version_entry.setPlaceholderText('Version from your PS3, e.g. v1.0.0')
        row.addWidget(self.version_entry)
        self.fav_entry=QCheckBox('Favorite');row.addWidget(self.fav_entry)
        self.watch_entry=QCheckBox('Watch releases');row.addWidget(self.watch_entry)
        save=QPushButton('Save selected app');save.clicked.connect(self.save_inventory);row.addWidget(save)
        refresh=QPushButton('Refresh');refresh.clicked.connect(self.refresh_inventory);row.addWidget(refresh)
        self.inventory_table.itemSelectionChanged.connect(self.select_inventory)
        self.tabs.addTab(tab,'Installed & Watchlist');self.refresh_inventory()

    def refresh_inventory(self):
        self.inventory_names=[x['name'] for x in catalog_items()]
        records=read_app_records(self.records_file)
        self.inventory_table.setRowCount(len(self.inventory_names))
        for i,name in enumerate(self.inventory_names):
            rec=records.get(name,{})
            for j,value in enumerate((name,rec.get('installed_version','Not recorded'),
                                      'Yes' if rec.get('favorite') else 'No','Yes' if rec.get('watch') else 'No')):
                self.inventory_table.setItem(i,j,QTableWidgetItem(value))
        if self.inventory_names and self.inventory_table.currentRow()<0:self.inventory_table.selectRow(0)

    def select_inventory(self):
        row=self.inventory_table.currentRow()
        if row<0 or row>=len(self.inventory_names):return
        rec=read_app_records(self.records_file).get(self.inventory_names[row],{})
        self.version_entry.setText(rec.get('installed_version',''))
        self.fav_entry.setChecked(bool(rec.get('favorite')))
        self.watch_entry.setChecked(bool(rec.get('watch')))

    def save_inventory(self):
        row=self.inventory_table.currentRow()
        if row<0 or row>=len(self.inventory_names):return
        try:set_app_record(self.records_file,self.inventory_names[row],installed_version=self.version_entry.text(),
             favorite=self.fav_entry.isChecked(),watch=self.watch_entry.isChecked())
        except Exception as exc:return QMessageBox.warning(self,'Inventory error',str(exc))
        self.refresh_inventory()

    def _inspector_page(self):
        tab=QWidget();layout=QVBoxLayout(tab)
        layout.addWidget(QLabel('Read-only PKG batch inspector. Header checks do not prove authenticity or PS3 compatibility.'))
        inspect=QPushButton('Select and inspect PKG files');inspect.clicked.connect(self.inspect_packages);layout.addWidget(inspect)
        self.inspection_results=QPlainTextEdit();self.inspection_results.setReadOnly(True);layout.addWidget(self.inspection_results)
        checklist=QPushButton('Show installation checklist for selected homebrew');checklist.clicked.connect(self.show_checklist)
        layout.addWidget(checklist)
        cache=QPushButton('Refresh offline catalog snapshot');cache.clicked.connect(self.refresh_offline_catalog)
        layout.addWidget(cache)
        self.tabs.addTab(tab,'PKG Inspector')

    def inspect_packages(self):
        paths=QFileDialog.getOpenFileNames(self,'Inspect local PS3 PKGs','','PS3 Packages (*.pkg)')[0]
        if not paths:return
        self.inspection_results.clear()
        for row in batch_inspect_pkgs(paths):
            if row['ok']:
                info=row['info'];self.inspection_results.appendPlainText(
                    f"{info['filename']}: {info['bytes']:,} bytes | SHA256 {info['sha256']} | "
                    f"type={info['package_type']} | revision={info['header_revision']} | "
                    f"size_warning={info['size_warning']}")
            else:self.inspection_results.appendPlainText(f"{Path(row['path']).name}: FAILED: {row['error']}")

    def show_checklist(self):
        idx=self.inventory_table.currentRow()
        name=self.inventory_names[idx] if 0<=idx<len(self.inventory_names) else self.inventory_names[0]
        items=installation_checklist(name)
        QMessageBox.information(self,'Manual install checklist',name+'\n\n'+'\n'.join('• '+x['step'] for x in items))

    def refresh_offline_catalog(self):
        snapshot=offline_catalog(self.catalog_cache,refresh=True)
        QMessageBox.information(self,'Offline catalog',f"Cached {len(snapshot['items'])} catalog entries locally.")

    def show_release_notes(self):
        row=self.release_table.currentRow()
        if row<0 or row>=len(self.rows):return QMessageBox.information(self,'Release notes','Select a release.')
        release,_=self.rows[row]
        records=read_app_records(self.records_file)
        rec=records.get(release['app'],{})
        state=update_compatibility_record(rec.get('installed_version',''),release.get('tag'))
        window=QDialog(self);window.setWindowTitle(f"{release['app']} • {release['tag']}");window.resize(730,520)
        layout=QVBoxLayout(window)
        layout.addWidget(QLabel('Installed-version comparison: '+state['message']))
        notes=QPlainTextEdit();notes.setReadOnly(True);notes.setPlainText(release_note_text(release));layout.addWidget(notes)
        window.exec()

class Window(V23Window):
    def __init__(self,root):
        super().__init__(root)
        self.setWindowTitle("Z's Save Archive • PS3 + PC v2.5")
        for action in self.tools_btn.menu().actions():
            if action.text()=='PS3 Homebrew Manager':
                action.triggered.disconnect();action.triggered.connect(lambda:HomebrewCenter(self,root).exec())
        from .tools_menu import reorganize_tools_menu
        reorganize_tools_menu(self.tools_btn, self)

def main():
    from . import ui
    ui.Archive=ArchiveV18
    app=QApplication(sys.argv);app.setStyle('Fusion');app.setStyleSheet(STYLE)
    from PySide6.QtGui import QIcon
    from .app_assets import asset_path
    app.setWindowIcon(QIcon(str(asset_path('ZSaveArchive.png'))))
    home=os.environ.get('Z_ARCHIVE_HOME')
    if home:root=Path(home)
    elif (Path(sys.argv[0]).resolve().parent/'portable.flag').is_file():root=Path(sys.argv[0]).resolve().parent/'ArchiveData'
    else:root=Path.home()/'Documents'/'Z PlayStation Save Archive'
    win=Window(root);win.setWindowIcon(app.windowIcon());win.show();sys.exit(app.exec())
