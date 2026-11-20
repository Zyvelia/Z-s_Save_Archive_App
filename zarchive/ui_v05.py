"""v0.5 visual-library improvements on the unchanged v0.4 application."""
from __future__ import annotations
import os, sys
from pathlib import Path
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
 QPushButton, QLabel, QComboBox, QDialog, QInputDialog, QMessageBox, QFileDialog,
 QListWidget, QListWidgetItem, QScrollArea, QFrame, QMenu)
from . import ui
from .ui_v04 import Window as PreviousWindow, cover_icon, STYLE
from .enhanced import COLORS

COLOR_HEX=dict(COLORS)

class Window(PreviousWindow):
    def __init__(self,root):
        self._v05_ready=False
        super().__init__(root)
        self.setWindowTitle("Z's Save Archive  •  PS3 + PC  v0.5")
        self._init_collections()
        self._init_inspector()
        self._init_game_actions()
        self._v05_ready=True
        self.show_dashboard()

    def _init_collections(self):
        sidebar=self.sidebar.layout()
        insert=sidebar.indexOf(self.home_nav)+4
        self.collection_nav=QPushButton('▤  Collections')
        self.collection_nav.setObjectName('nav')
        self.collection_nav.clicked.connect(self.open_collections)
        sidebar.insertWidget(insert,self.collection_nav)
        # Compact collection selector on the Games page; one click to filter the cards.
        self.collection_filter=QComboBox()
        self.collection_filter.setMinimumWidth(175)
        self.collection_filter.setToolTip('Filter the game library by collection')
        self.collection_filter.currentIndexChanged.connect(self.refresh)
        self._reload_collections()
        content=self.centralWidget().layout().itemAt(1).widget().layout()
        toolbar=content.itemAt(1).layout()
        toolbar.insertWidget(3,self.collection_filter)
        self.collection_filter.hide()

    def _reload_collections(self):
        old=self.collection_filter.currentData() if self.collection_filter.count() else None
        self.collection_filter.blockSignals(True)
        self.collection_filter.clear();self.collection_filter.addItem('All collections',None)
        for r in self.archive.collections():self.collection_filter.addItem(r['name'],r['id'])
        idx=self.collection_filter.findData(old)
        self.collection_filter.setCurrentIndex(max(idx,0))
        self.collection_filter.blockSignals(False)

    def _init_inspector(self):
        # Inspector is inside the v0.4 scroll area. Insert our visual helpers after its metadata header.
        detail_scroll=self.stack.widget(1).widget(1)
        detail=detail_scroll.widget()
        dl=detail.layout()
        self.chips_title=QLabel('QUICK TAG FILTERS');dl.insertWidget(2,self.chips_title)
        self.chips_widget=QWidget();self.chips_layout=QGridLayout(self.chips_widget)
        self.chips_layout.setContentsMargins(0,0,0,0);self.chips_layout.setHorizontalSpacing(5);self.chips_layout.setVerticalSpacing(5)
        dl.insertWidget(3,self.chips_widget)
        self.shots_title=QLabel('SCREENSHOTS');self.shots_title.setStyleSheet('font-weight:700;color:#d5c3fb')
        pos=dl.indexOf(self.screenshot_btn)
        dl.insertWidget(pos,self.shots_title)
        self.gallery=QListWidget();self.gallery.setViewMode(QListWidget.ViewMode.IconMode)
        self.gallery.setIconSize(QSize(140,90));self.gallery.setGridSize(QSize(158,116))
        self.gallery.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.gallery.setFixedHeight(145);self.gallery.itemDoubleClicked.connect(self.open_screenshot)
        dl.insertWidget(dl.indexOf(self.screenshot_btn),self.gallery)
        self.gallery_note=QLabel('Double-click an image to view the original.')
        dl.insertWidget(dl.indexOf(self.screenshot_btn),self.gallery_note)
        self.gallery.hide();self.gallery_note.hide()
        self._update_chips([])

    def _init_game_actions(self):
        self.game_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.game_list.customContextMenuRequested.connect(self.game_context_menu)
        self.change_cover_btn=QPushButton('Cover Art')
        menu=QMenu(self)
        menu.addAction('Choose local cover image',self.choose_cover)
        menu.addAction('Find matching Steam cover (PC)',self.fetch_cover)
        self.change_cover_btn.setMenu(menu)
        content=self.centralWidget().layout().itemAt(1).widget().layout()
        toolbar=content.itemAt(1).layout();toolbar.insertWidget(4,self.change_cover_btn)
        self.change_cover_btn.hide()

    def _selected_game(self):
        item=self.game_list.currentItem()
        if not item:
            QMessageBox.information(self,'Select game','Select a game card first.');return None
        tid,game,platform=item.data(Qt.ItemDataRole.UserRole)
        return (platform,game)

    def choose_cover(self):
        entry=self._selected_game()
        if not entry:return
        image=QFileDialog.getOpenFileName(self,'Choose cover art','','Images (*.png *.jpg *.jpeg *.webp)')[0]
        if not image:return
        try:
            self.archive.add_cover(*entry,Path(image));self.refresh()
            self.statusBar().showMessage('Cover copied to the local cache')
        except Exception as exc:QMessageBox.warning(self,'Cover not saved',str(exc))

    def fetch_cover(self):
        entry=self._selected_game()
        if not entry:return
        platform,game=entry
        matches=self.archive.steam_matches(game) if platform=='PC' else []
        if not matches:
            QMessageBox.information(self,'Cover discovery','No exact installed Steam title match found. For PS3 or non-Steam games, use Choose local cover image.');return
        choices=[f"{r['name']}  (Steam App {r['appid']})" for r in matches]
        selected,ok=QInputDialog.getItem(self,'Steam cover','Download a cover from the Steam CDN:',choices,0,False)
        if not ok:return
        try:
            self.archive.steam_cover(platform,game,matches[choices.index(selected)]['appid'])
            self.refresh();self.statusBar().showMessage('Cover downloaded and cached')
        except Exception as exc:QMessageBox.warning(self,'Download failed',str(exc))

    def game_context_menu(self,pos):
        item=self.game_list.itemAt(pos)
        if item:self.game_list.setCurrentItem(item)
        else:return
        menu=QMenu(self)
        menu.addAction('Choose cover art',self.choose_cover)
        menu.addAction('Find Steam cover',self.fetch_cover)
        menu.addSeparator();menu.addAction('Add to collection',self.add_selected_to_collection)
        menu.exec(self.game_list.mapToGlobal(pos))

    def add_selected_to_collection(self):
        entry=self._selected_game()
        if not entry:return
        rows=self.archive.collections()
        if not rows:
            QMessageBox.information(self,'Collections','Create a collection first from Collections.');return
        names=[r['name'] for r in rows]
        choice,ok=QInputDialog.getItem(self,'Add game to collection','Collection',names,0,False)
        if ok:
            self.archive.add_to_collection(rows[names.index(choice)]['id'],*entry)
            self.refresh();self.statusBar().showMessage('Game added to collection')

    def open_collections(self):
        dlg=QDialog(self);dlg.setWindowTitle('Collections');dlg.resize(570,470)
        outer=QVBoxLayout(dlg)
        title=QLabel('Organize games into collections');title.setStyleSheet('font-size:19px;font-weight:700')
        outer.addWidget(title)
        selector=QComboBox();outer.addWidget(selector)
        games=QListWidget();outer.addWidget(games)
        actions=QHBoxLayout()
        for text,cb in [('New',None),('Rename',None),('Remove game',None),('Delete',None)]:
            b=QPushButton(text);actions.addWidget(b)
            if text=='New':b.clicked.connect(lambda:self._collection_new(selector,games))
            elif text=='Rename':b.clicked.connect(lambda:self._collection_rename(selector,games))
            elif text=='Remove game':b.clicked.connect(lambda:self._collection_remove(selector,games))
            else:b.clicked.connect(lambda:self._collection_delete(selector,games))
        outer.addLayout(actions)
        hint=QLabel('To add a game, right-click it in Game Library → Add to collection.')
        hint.setWordWrap(True);outer.addWidget(hint)
        selector.currentIndexChanged.connect(lambda:self._fill_collection_games(selector,games))
        self._fill_collections_dialog(selector,games)
        dlg.exec();self._reload_collections();self.refresh()

    def _fill_collections_dialog(self,selector,games):
        selector.blockSignals(True);selector.clear()
        for r in self.archive.collections():selector.addItem(r['name'],r['id'])
        selector.blockSignals(False);self._fill_collection_games(selector,games)

    def _fill_collection_games(self,selector,games):
        games.clear();cid=selector.currentData()
        if cid:
            for platform,game in self.archive.collection_games(cid):
                it=QListWidgetItem(f'{game}  ·  {platform}');it.setData(Qt.ItemDataRole.UserRole,(platform,game));games.addItem(it)

    def _collection_new(self,selector,games):
        name,ok=QInputDialog.getText(self,'Create collection','Name')
        if ok and name.strip():
            try:self.archive.create_collection(name);self._fill_collections_dialog(selector,games)
            except Exception as e:QMessageBox.warning(self,'Collection error',str(e))

    def _collection_rename(self,selector,games):
        cid=selector.currentData()
        if cid is None:return
        name,ok=QInputDialog.getText(self,'Rename collection','New name',text=selector.currentText())
        if ok and name.strip():
            try:self.archive.rename_collection(cid,name);self._fill_collections_dialog(selector,games)
            except Exception as e:QMessageBox.warning(self,'Rename failed',str(e))

    def _collection_remove(self,selector,games):
        cid=selector.currentData();item=games.currentItem()
        if cid and item:
            self.archive.remove_from_collection(cid,*item.data(Qt.ItemDataRole.UserRole))
            self._fill_collection_games(selector,games)

    def _collection_delete(self,selector,games):
        cid=selector.currentData()
        if cid and QMessageBox.question(self,'Delete collection',f'Delete collection "{selector.currentText()}"?\nGames and saves will not be deleted.')==QMessageBox.StandardButton.Yes:
            self.archive.delete_collection(cid);self._fill_collections_dialog(selector,games)

    def _update_chips(self,tags):
        while self.chips_layout.count():
            item=self.chips_layout.takeAt(0)
            if item.widget():item.widget().deleteLater()
        style={n.casefold():c for n,c in self.archive.tag_styles()}
        for i,tag in enumerate(tags[:24]):
            color=COLOR_HEX.get(style.get(tag.casefold(),'Violet'),'#aa8af3')
            b=QPushButton(tag);b.setToolTip('Click to filter All Saves by this tag')
            b.setStyleSheet(f'QPushButton {{background:#241f31;border:1px solid {color};color:{color};padding:5px 8px;border-radius:12px;}}')
            b.clicked.connect(lambda checked=False,t=tag:self.filter_by_tag(t))
            self.chips_layout.addWidget(b,i//3,i%3)
        self.chips_title.setVisible(bool(tags));self.chips_widget.setVisible(bool(tags))

    def filter_by_tag(self,tag):
        self.show_saves();idx=self.tagfilter.findText(tag)
        if idx>=0:self.tagfilter.setCurrentIndex(idx)

    def _populate_gallery(self,save_id):
        self.gallery.clear()
        for row in self.archive.screenshots(save_id):
            path=self.archive.root/row['path']
            if not path.is_file():continue
            pm=QPixmap(str(path))
            if pm.isNull():continue
            item=QListWidgetItem(QIcon(pm),path.name)
            item.setData(Qt.ItemDataRole.UserRole,str(path));self.gallery.addItem(item)
        visible=self.gallery.count()>0
        self.gallery.setVisible(visible);self.gallery_note.setVisible(visible)
        self.shots_title.setVisible(visible)

    def open_screenshot(self,item):
        path=Path(item.data(Qt.ItemDataRole.UserRole))
        if not path.is_file():return
        dlg=QDialog(self);dlg.setWindowTitle(path.name);dlg.resize(850,620)
        v=QVBoxLayout(dlg);scroll=QScrollArea();scroll.setWidgetResizable(True)
        lbl=QLabel();lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pix=QPixmap(str(path))
        lbl.setPixmap(pix.scaled(QSize(1050,760),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
        scroll.setWidget(lbl);v.addWidget(scroll);dlg.exec()

    def select_save(self,item):
        super().select_save(item)
        if self.current:
            self._update_chips(self.current.get('tags',[]))
            self._populate_gallery(self.current['id'])

    def add_screenshot(self):
        super().add_screenshot()
        if self.current:self._populate_gallery(self.current['id'])

    def show_games(self):
        super().show_games()
        if getattr(self,'_v05_ready',False):
            self.collection_filter.show();self.change_cover_btn.show()

    def activate_nav(self,idx):
        super().activate_nav(idx)
        if getattr(self,'_v05_ready',False):
            self.collection_filter.setVisible(idx==1)
            self.change_cover_btn.setVisible(idx==1)

    def refresh(self,*args):
        super().refresh(*args)
        if not getattr(self,'_v05_ready',False):return
        if self.mode=='games':
            cid=self.collection_filter.currentData()
            allowed=set(self.archive.collection_games(cid)) if cid else None
            for i in reversed(range(self.game_list.count())):
                item=self.game_list.item(i)
                tid,game,platform=item.data(Qt.ItemDataRole.UserRole)
                if allowed is not None and (platform,game) not in allowed:
                    self.game_list.takeItem(i);continue
                item.setIcon(cover_icon(game,platform,self.archive.cover_for(platform,game)))


def main():
    app=QApplication(sys.argv);app.setStyle('Fusion');app.setStyleSheet(STYLE)
    home=os.environ.get('Z_ARCHIVE_HOME')
    if home:root=Path(home)
    elif (Path(sys.argv[0]).resolve().parent/'portable.flag').is_file():root=Path(sys.argv[0]).resolve().parent/'ArchiveData'
    else:root=Path.home()/'Documents'/'Z PlayStation Save Archive'
    win=Window(root);win.show();sys.exit(app.exec())
