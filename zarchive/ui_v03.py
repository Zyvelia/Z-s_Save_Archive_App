"""v0.3 GUI additions layered onto the working v0.2 interface."""
from __future__ import annotations
import json, os, re, sys
from pathlib import Path
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QPixmap, QAction
from PySide6.QtWidgets import (QApplication,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
 QLineEdit,QComboBox,QFileDialog,QInputDialog,QMessageBox,QListWidget,QListWidgetItem,
 QDialog,QFormLayout,QDialogButtonBox,QMenu,QFrame,QListWidget)
from . import ui
from .enhanced import COLORS
from .storage import DEFAULT_TAGS, ORIGIN_KINDS
from .integrations import steam_games,download_steam_cover,ftp_list_ps3,ftp_import_ps3

class Window(ui.MainWindow):
    def __init__(self,root):
        super().__init__(root)
        self.setWindowTitle("Z's Save Archive  •  PS3 + PC  v0.3")
        self.resize(1390,900)
        self.archive_cover=self.archive.root/'covers';self.archive_cover.mkdir(exist_ok=True)
        self.setAcceptDrops(True)
        self._extra_nav=[]
        # Reuse v0.2's central UI, add a compact toolbar below the top navigation.
        body=self.centralWidget().layout().itemAt(1).widget()
        ml=body.layout()
        toolbar=QHBoxLayout()
        self.dashboard_btn=QPushButton('Dashboard');self.dashboard_btn.clicked.connect(self.show_dashboard)
        self.grid_btn=QPushButton('▦  Grid / List');self.grid_btn.clicked.connect(self.toggle_grid)
        self.health_btn=QPushButton('Check Archive');self.health_btn.clicked.connect(self.health_check)
        for b in (self.dashboard_btn,self.grid_btn,self.health_btn):toolbar.addWidget(b)
        toolbar.addStretch();ml.insertLayout(1,toolbar)
        # Reuse save detail form, adding visibility, screenshots, and history controls.
        savepage=self.stack.widget(1)
        detail=savepage.widget(1)
        dl=detail.layout()
        dl.insertWidget(0,ui.label('SAVE INSPECTOR  /  VERSION  /  TAGS',10,True))
        self.visibility=QComboBox();self.visibility.addItems(['Private','Public'])
        dl.insertWidget(dl.indexOf(self.detail_status)+1,ui.label('Release visibility',11,True))
        dl.insertWidget(dl.indexOf(self.detail_status)+2,self.visibility)
        # Keep the inspector compact: detailed provenance lives in a separate dialog.
        self.origin_summary=ui.label('Origin: Unknown',11,True)
        self.origin_btn=QPushButton('Edit Save Origin…')
        self.origin_btn.clicked.connect(self.edit_save_origin)
        dl.insertWidget(dl.indexOf(self.detail_status),self.origin_summary)
        dl.insertWidget(dl.indexOf(self.detail_status),self.origin_btn)
        self.starter_tags=QPushButton('Choose Starter Tags…')
        self.starter_tags.clicked.connect(self.choose_starter_tags)
        dl.insertWidget(dl.indexOf(self.detail_tags)+1,self.starter_tags)
        self.screenshot_btn=QPushButton('Add Screenshot');self.screenshot_btn.clicked.connect(self.add_screenshot)
        self.version_btn=QPushButton('Create Versioned Backup');self.version_btn.clicked.connect(self.backup_version)
        self.restore_btn=QPushButton('Restore Backup to Folder');self.restore_btn.clicked.connect(self.restore_selected)
        self.release_btn=QPushButton('Build Release ZIP');self.release_btn.clicked.connect(self.build_release)
        for b in (self.screenshot_btn,self.version_btn,self.restore_btn,self.release_btn):dl.insertWidget(dl.count()-1,b)
        self.save_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.save_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.save_list.customContextMenuRequested.connect(self.save_menu)
        self.bulk_btn=QPushButton('Bulk ZIP Backups');self.bulk_btn.clicked.connect(self.bulk_backup)
        self.bulk_tag_btn=QPushButton('Bulk Tag');self.bulk_tag_btn.clicked.connect(self.bulk_tags)
        toolbar.insertWidget(2,self.bulk_btn);toolbar.insertWidget(3,self.bulk_tag_btn)
        self.tagcolors_btn=QPushButton('Tag Colors');self.tagcolors_btn.clicked.connect(self.edit_tag_color);toolbar.addWidget(self.tagcolors_btn)
        self.collections_btn=QPushButton('Collections');self.collections_btn.clicked.connect(self.show_collections)
        self.steam_btn=QPushButton('Find PC Saves');self.steam_btn.clicked.connect(self.show_pc_discovery)
        self.theme_btn=QPushButton('Theme');self.theme_btn.clicked.connect(self.choose_theme);toolbar.addWidget(self.theme_btn)
        self.ftp_btn=QPushButton('PS3 FTP');self.ftp_btn.clicked.connect(self.show_ftp)
        for b in (self.collections_btn,self.steam_btn,self.ftp_btn):toolbar.addWidget(b)
        self.game_list.setViewMode(QListWidget.ViewMode.ListMode)
        self.game_list.setIconSize(QSize(116,54))
        self.cover_cache={}
        self.statusBar().showMessage('v0.3 • Local archive and PS3/PC tools ready')
        self.show_dashboard()

    def toggle_grid(self):
        new=(QListWidget.ViewMode.IconMode if self.game_list.viewMode()==QListWidget.ViewMode.ListMode else QListWidget.ViewMode.ListMode)
        self.game_list.setViewMode(new)
        self.game_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.game_list.setSpacing(10)
        self.game_list.setGridSize(QSize(205,145) if new==QListWidget.ViewMode.IconMode else QSize())
        self.game_list.setWordWrap(True)
        self.statusBar().showMessage('Game view: '+('Grid' if new==QListWidget.ViewMode.IconMode else 'List'))

    def refresh(self,*args):
        super().refresh(*args)
        if self.mode=='games' and hasattr(self,'archive_cover'):
            for i in range(self.game_list.count()):
                item=self.game_list.item(i)
                if not item:continue
                tid,game,platform=item.data(Qt.ItemDataRole.UserRole)
                # Covers are cached and never fetched automatically without user action.
                candidates=list(self.archive_cover.glob(re.sub(r'[^A-Za-z0-9_-]','_',game)[:80]+'_*'))
                if candidates:
                    icon=QIcon(str(candidates[0]))
                    if not icon.isNull():item.setIcon(icon)

    def select_save(self,item):
        super().select_save(item)
        if self.current:
            self.visibility.setCurrentText(self.current.get('visibility','Private'))
            kind=self.current.get('origin_kind') or 'Unknown'
            name=self.current.get('origin_name') or ''
            self.origin_summary.setText('Origin: '+kind+(' · '+name if name else ''))

    def save_details(self):
        if not self.current:return
        try:
            self.archive.save_details(self.current['id'],category=self.detail_category.currentText(),
                 label=self.detail_label.text(),notes=self.detail_notes.toPlainText(),
                 status=self.detail_status.currentText(),tags=self.detail_tags.text().split(','),
                 visibility=self.visibility.currentText())
            self.statusBar().showMessage('Save details and origin updated');self.refresh()
        except Exception as e:QMessageBox.warning(self,'Update failed',str(e))

    def edit_save_origin(self):
        if not self.current:
            QMessageBox.information(self,'Select a save','Select an archived save first.');return
        dialog=QDialog(self);dialog.setWindowTitle('Save Origin / Provenance');dialog.resize(530,370)
        layout=QVBoxLayout(dialog)
        layout.addWidget(ui.label('Where did this save come from? These details are user-entered and not independently verified.',12,True))
        form=QFormLayout();layout.addLayout(form)
        kind=QComboBox();kind.addItems(ORIGIN_KINDS)
        kind.setCurrentText(self.current.get('origin_kind') or 'Unknown');form.addRow('Origin type',kind)
        name=QLineEdit(self.current.get('origin_name') or '')
        name.setPlaceholderText('Creator, friend, website, or console')
        form.addRow('Source / creator',name)
        link=QLineEdit(self.current.get('origin_url') or '')
        link.setPlaceholderText('https://... (optional)');form.addRow('Source URL',link)
        notes=QLineEdit(self.current.get('origin_notes') or '')
        notes.setPlaceholderText('Additional context');form.addRow('Notes',notes)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            try:
                self.archive.set_origin(self.current['id'],kind=kind.currentText(),name=name.text(),url=link.text(),notes=notes.text())
                self.current.update(origin_kind=kind.currentText(),origin_name=name.text(),origin_url=link.text(),origin_notes=notes.text())
                self.origin_summary.setText('Origin: '+kind.currentText()+(' · '+name.text().strip() if name.text().strip() else ''))
                self.statusBar().showMessage('Save origin saved')
            except Exception as exc:
                QMessageBox.warning(self,'Invalid origin details',str(exc))

    def choose_starter_tags(self):
        dialog=QDialog(self);dialog.setWindowTitle('Suggested Save Tags');dialog.resize(400,480)
        layout=QVBoxLayout(dialog)
        layout.addWidget(ui.label('Select any suggested tags; your custom tags are preserved.',12,True))
        tags_list=QListWidget();layout.addWidget(tags_list)
        existing=[v.strip() for v in self.detail_tags.text().split(',') if v.strip()]
        for suggestion in DEFAULT_TAGS:
            item=QListWidgetItem(suggestion)
            item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if suggestion.casefold() in [t.casefold() for t in existing] else Qt.CheckState.Unchecked)
            tags_list.addItem(item)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            chosen=[tags_list.item(i).text() for i in range(tags_list.count()) if tags_list.item(i).checkState()==Qt.CheckState.Checked]
            # Preserve any manually typed tags, but reflect changed checks for starter tags.
            manual=[t for t in existing if t.casefold() not in {s.casefold() for s in DEFAULT_TAGS}]
            result=manual+chosen
            if len(result)>24:
                QMessageBox.warning(self,'Too many tags','A save supports up to 24 tags.');return
            self.detail_tags.setText(', '.join(result))

    def selected_ids(self):
        return [it.data(Qt.ItemDataRole.UserRole)['id'] for it in self.save_list.selectedItems()]

    def bulk_backup(self):
        ids=self.selected_ids()
        if not ids:
            QMessageBox.information(self,'Bulk backups','Select one or more saves in All Saves (Ctrl/Shift-click).');return
        if QMessageBox.question(self,'Confirm backups',f'Create {len(ids)} versioned ZIP backups?')!=QMessageBox.StandardButton.Yes:return
        results=self.archive.backup_many(ids)
        successes=sum(not e for _,_,e in results)
        errors='\n'.join(e for _,_,e in results if e)
        QMessageBox.information(self,'Bulk backup complete',f'{successes}/{len(results)} backups created.\n'+errors[:1200])

    def bulk_tags(self):
        ids=self.selected_ids()
        if not ids:QMessageBox.information(self,'Bulk tags','Select saves in All Saves first.');return
        tags,ok=QInputDialog.getText(self,'Add tags to selected saves','Comma-separated tags:')
        if ok and tags.strip():
            try:self.archive.bulk_tag(ids,tags.split(','));self.refresh()
            except Exception as e:QMessageBox.warning(self,'Tagging failed',str(e))

    def backup_version(self):
        if not self.current:return
        try:
            path=self.archive.make_backup(self.current['id']);self.statusBar().showMessage('Verified backup: '+str(path))
            QMessageBox.information(self,'Backup saved','Created versioned backup:\n'+str(path))
        except Exception as e:QMessageBox.warning(self,'Backup failed',str(e))

    def restore_selected(self):
        if not self.current:QMessageBox.information(self,'Restore','Select a save.');return
        versions=self.archive.backup_history(self.current['id'])
        if not versions:QMessageBox.information(self,'Restore','Create a versioned backup first.');return
        choices=[v['created_at']+'   /   '+v['id'][:10] for v in versions]
        choice,ok=QInputDialog.getItem(self,'Choose backup version','Backup',choices,0,False)
        if not ok:return
        bid=versions[choices.index(choice)]['id']
        path=QFileDialog.getExistingDirectory(self,'Choose a parent folder for restored copy')
        if not path:return
        dest=Path(path)/('ZRestore_'+bid[:10])
        if QMessageBox.question(self,'Confirm restore',f'Restore verified backup into a NEW folder?\n{dest}\n\nNo console or game files will be overwritten.')!=QMessageBox.StandardButton.Yes:return
        try:
            self.archive.restore_backup(bid,dest)
            QMessageBox.information(self,'Restored','Verified restore completed:\n'+str(dest))
        except Exception as e:QMessageBox.warning(self,'Restore failed',str(e))

    def add_screenshot(self):
        if not self.current:return
        p=QFileDialog.getOpenFileName(self,'Select screenshot','','Images (*.png *.jpg *.jpeg *.webp)')[0]
        if p:
            try:self.archive.screenshot(self.current['id'],Path(p));self.statusBar().showMessage('Screenshot attached')
            except Exception as e:QMessageBox.warning(self,'Screenshot failed',str(e))

    def build_release(self):
        if not self.current:return
        p=QFileDialog.getSaveFileName(self,'Release save ZIP',str(Path.home()/'Downloads'/'Z_Save_Release.zip'),'ZIP (*.zip)')[0]
        if not p:return
        try:self.archive.export_release(self.current['id'],Path(p));QMessageBox.information(self,'Release ready',p)
        except Exception as e:QMessageBox.warning(self,'Release blocked',str(e))

    def health_check(self):
        self.statusBar().showMessage('Checking source objects and backup ZIPs...')
        try:
            issues=self.archive.audit()
            QMessageBox.information(self,'Archive health', 'All indexed saves and backups passed verification.' if not issues else '\n'.join(issues[:30]))
            self.statusBar().showMessage(f'Archive health: {len(issues)} issues')
        except Exception as e:QMessageBox.warning(self,'Audit failed',str(e))

    def show_dashboard(self):
        d=self.archive.dashboard()
        self.statusBar().showMessage(f"DASHBOARD   •   {d['games']} games   •   {d['saves']} saves   •   {d['verified']} verified   •   {d['backups']} ZIP versions   •   {d['bytes']/1048576:.1f} MiB stored")
        self.show_games()
        self.heading.setText('Your Game Library')
        self.subheading.setText(f"PS3 + PC  ·  {d['saves']} saves  ·  {d['backups']} backup versions  ·  {d['verified']} verified")

    def save_menu(self,pos):
        menu=QMenu(self)
        for name,fn in [('Versioned Backup',self.backup_version),('Restore Backup',self.restore_selected),
                        ('Build Release ZIP',self.build_release),('Bulk Tag',self.bulk_tags),('Open Folder',self.open_selected_folder)]:
            a=menu.addAction(name);a.triggered.connect(fn)
        menu.exec(self.save_list.viewport().mapToGlobal(pos))

    def choose_theme(self):
        themes=['Charcoal / Violet','Charcoal / Blue','Light / Violet','Compact Charcoal']
        t,ok=QInputDialog.getItem(self,'Appearance','Theme / density',themes,0,False)
        if not ok:return
        if t=='Charcoal / Violet':css=ui.QSS
        elif t=='Charcoal / Blue':css=ui.QSS.replace('#b393ff','#79b1ff').replace('#7653cb','#3160a8').replace('#9676e7','#5080ca').replace('#8966e2','#4174c2')
        elif t=='Light / Violet':
            css=(ui.QSS.replace('#111019','#f6f4fa').replace('#171522','#ebe8f3')
                 .replace('#1b1927','#ffffff').replace('#252237','#eeeaf6')
                 .replace('#393449','#d4cde1').replace('#f2efff','#201c30')
                 .replace('#ada6bf','#5c556b').replace('#b393ff','#6547a8')
                 .replace('#302841','#dfd6ee').replace('#292437','#e3ddee')
                 .replace('#38304c','#d8cbea'))
        else:css=ui.QSS+'\nQPushButton {padding:6px 10px} QListWidget::item {padding:8px} QWidget {font-size:12px}\n'
        QApplication.instance().setStyleSheet(css)
        self.statusBar().showMessage('Appearance applied for this session: '+t)

    def edit_tag_color(self):
        tags=self.archive.list_tags()
        tag,ok=QInputDialog.getItem(self,'Tag colors','Select tag',tags,0,False)
        if not ok:return
        color,ok=QInputDialog.getItem(self,'Tag colors','Color',list(COLORS),0,False)
        if ok:
            try:self.archive.set_tag_color(tag,color)
            except Exception as e:QMessageBox.warning(self,'Tag color',str(e))
            else:self.statusBar().showMessage(f'{tag}: {color} saved')

    def show_collections(self):
        names=self.archive.collections()
        actions=['Create collection']+[f"Add game to: {r['name']}" for r in names]
        option,ok=QInputDialog.getItem(self,'Collections','Action',actions,0,False)
        if not ok:return
        try:
            if option=='Create collection':
                name,ok=QInputDialog.getText(self,'New collection','Collection name')
                if ok and name.strip():self.archive.create_collection(name)
            else:
                c=names[actions.index(option)-1]
                games=self.archive.games()
                choices=[f"{g['platform']} | {g['game']}" for g in games]
                if not choices:return
                s,ok=QInputDialog.getItem(self,'Add game','Choose game',choices,0,False)
                if ok:
                    row=games[choices.index(s)];self.archive.add_to_collection(c['id'],row['platform'],row['game'])
                    QMessageBox.information(self,'Collection updated',f"{row['game']} added to {c['name']}")
        except Exception as e:QMessageBox.warning(self,'Collections',str(e))

    def show_pc_discovery(self):
        from .enhanced import discover_pc_locations
        roots=discover_pc_locations();games=steam_games()
        choices=[str(p) for p in roots]+[f"Steam: {g['name']} (App {g['appid']})" for g in games]
        if not choices:QMessageBox.information(self,'PC save locations','No common save roots or Steam manifests found.');return
        selection,ok=QInputDialog.getItem(self,'PC folders and installed Steam games','Select a discovery result',choices,0,False)
        if not ok:return
        if selection.startswith('Steam:'):
            g=games[choices.index(selection)-len(roots)]
            if QMessageBox.question(self,'Download cover?',f"Cache Steam game cover for {g['name']}? Internet required.")==QMessageBox.StandardButton.Yes:
                try:
                    src=download_steam_cover(g['appid'],self.archive_cover)
                    name=re.sub(r'[^A-Za-z0-9_-]','_',g['name'])[:80]
                    dest=self.archive_cover/f'{name}_{g["appid"]}.jpg'
                    if src!=dest:dest.write_bytes(src.read_bytes())
                    self.refresh()
                except Exception as e:QMessageBox.warning(self,'Cover download failed',str(e))
        else:
            QMessageBox.information(self,'Detected directory',selection+'\n\nBrowse this folder using Import PC. Steam installation discovery does not imply a known save location.')

    def show_ftp(self):
        host,ok=QInputDialog.getText(self,'PS3 FTP connection','PS3 IP / host (webMAN MOD FTP)')
        if not ok or not host.strip():return
        user,ok=QInputDialog.getText(self,'FTP username','Username (usually anonymous)',text='anonymous')
        if not ok:return
        # Passwords are never persisted.
        from PySide6.QtWidgets import QLineEdit as Edit
        password,ok=QInputDialog.getText(self,'FTP password','Password (blank if none)',Edit.EchoMode.Password)
        if not ok:return
        try:
            dirs=ftp_list_ps3(host.strip(),user,password)
            QMessageBox.information(self,'PS3 home directories','Found:\n'+'\n'.join(dirs[:30])+'\n\nNo files were changed.')
            path,ok=QInputDialog.getText(self,'Import one PS3 save','Optional: exact path /dev_hdd0/home/00000001/savedata/SAVE_ID')
            if ok and path.strip():
                if QMessageBox.question(self,'Confirm FTP download','Download this save into the local archive? PS3 source remains unchanged.')==QMessageBox.StandardButton.Yes:
                    ftp_import_ps3(host.strip(),user,password,path.strip(),self.archive)
                    self.refresh();QMessageBox.information(self,'Imported','PS3 save imported over FTP.')
        except Exception as e:QMessageBox.warning(self,'FTP operation failed',str(e))

    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls() and all(u.isLocalFile() for u in event.mimeData().urls()):event.acceptProposedAction()
    def dropEvent(self,event):
        paths=[Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        if not paths:return
        pc_paths = [path for path in paths if not (path.is_dir() and (path / 'PARAM.SFO').is_file())]
        game = self.choose_game_title('PC') if pc_paths else ''
        if pc_paths and not game:
            return
        okcount=0;failed=[]
        for p in paths:
            try:
                if p.is_dir() and (p/'PARAM.SFO').is_file():self.archive.import_save(p)
                else:self.archive.import_pc_save(p,game)
                okcount+=1
            except Exception as e:failed.append(f'{p.name}: {e}')
        self.refresh();QMessageBox.information(self,'Import results',f'Imported {okcount} item(s).\n'+'\n'.join(failed[:15]))


def main():
    app=QApplication(sys.argv);app.setStyle('Fusion');app.setStyleSheet(ui.QSS)
    home=os.environ.get('Z_ARCHIVE_HOME')
    if home:root=Path(home)
    elif (Path(sys.argv[0]).resolve().parent/'portable.flag').is_file():root=Path(sys.argv[0]).resolve().parent/'ArchiveData'
    else:root=Path.home()/'Documents'/'Z PlayStation Save Archive'
    w=Window(root);w.show();sys.exit(app.exec())
