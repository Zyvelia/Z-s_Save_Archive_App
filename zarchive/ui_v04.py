"""v0.4 interface refresh. Storage schema and v0.3 features are intentionally unchanged."""
from __future__ import annotations
import os, sys, re, hashlib
from pathlib import Path
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QLinearGradient
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
 QLabel, QPushButton, QListWidget, QListWidgetItem, QFrame, QScrollArea,
 QGridLayout, QMenu, QSplitter, QMessageBox)
from . import ui
from .ui_v03 import Window as PreviousWindow

STYLE = ui.QSS + '''
QWidget {font-family:'Segoe UI';}
QMainWindow {background:#100f17}
QFrame#sidebar {background:#171520;border-right:1px solid #343044}
QFrame#card, QFrame#stat {background:#1c1a29;border:1px solid #343044;border-radius:12px}
QPushButton {padding:9px 12px;border-radius:8px}
QPushButton#nav {padding:12px 14px}
QPushButton#nav:checked {background:#322943;border-left:3px solid #b393ff}
QLabel#sectionTitle {font-weight:700;font-size:16px;color:#f5f1ff}
QLabel#muted {color:#aaa4ba}
QListWidget::item {padding:12px;margin:4px 0;border-radius:9px}
QListWidget::item:selected {background:#342946}
QScrollArea {background:transparent;border:0}
QFrame#quickPanel {background:#201e2c;border:1px solid #373147;border-radius:13px}
'''

def section(text):
    l=QLabel(text);l.setObjectName('sectionTitle');return l

def card(title,value,description=''):
    f=QFrame();f.setObjectName('stat');v=QVBoxLayout(f);v.setContentsMargins(18,16,18,16);v.setSpacing(5)
    v.addWidget(ui.label(title.upper(),10,True));num=QLabel(str(value));num.setObjectName('large');v.addWidget(num)
    if description:v.addWidget(ui.label(description,11,True))
    return f,num

def cover_icon(game, platform, photo=None, size=QSize(260,152)):
    """Use cached cover where present; otherwise render a legible branded placeholder offline."""
    pm=QPixmap(size)
    if photo and Path(photo).is_file():
        original=QPixmap(str(photo))
        if not original.isNull():
            fitted=original.scaled(size,Qt.AspectRatioMode.KeepAspectRatioByExpanding,Qt.TransformationMode.SmoothTransformation)
            p=QPainter(pm);p.drawPixmap(0,0,fitted);p.end();return QIcon(pm)
    digest=hashlib.sha256((platform+':'+game).encode('utf-8')).digest()
    base=[('#31244e','#574081'),('#203a4b','#32667d'),('#443044','#75516e'),('#273e38','#3c6860')][digest[0]%4]
    pm.fill(QColor(base[0]));p=QPainter(pm)
    gradient=QLinearGradient(0,0,size.width(),size.height());gradient.setColorAt(0,QColor(base[0]));gradient.setColorAt(1,QColor(base[1]))
    p.fillRect(pm.rect(),gradient)
    p.setPen(QColor('#eae4fa'));font=QFont('Segoe UI',14,QFont.Weight.Bold);p.setFont(font)
    title=game.strip() or 'Untitled game'
    lines=[]; current=''
    for word in title.split():
        candidate=(current+' '+word).strip()
        if len(candidate)>22 and current: lines.append(current);current=word
        else:current=candidate
    if current:lines.append(current)
    p.drawText(pm.rect().adjusted(17,22,-17,-20),Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft,'\n'.join(lines[:3]))
    p.setFont(QFont('Segoe UI',9));p.setPen(QColor('#cfc2ec'))
    p.drawText(pm.rect().adjusted(17,7,-12,-8),Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignRight,platform)
    p.end();return QIcon(pm)

class Window(PreviousWindow):
    def __init__(self,root):
        self._v04_ready=False
        super().__init__(root)
        self.setWindowTitle("Z's Save Archive  •  PS3 + PC  v0.4")
        self.resize(1430,910)
        self.setMinimumSize(1040,690)
        self._game_grid=True
        self._make_dashboard()
        self._tidy_toolbar()
        self._improve_inspector()
        self._update_navigation()
        self._v04_ready=True
        self.show_dashboard()

    def _tidy_toolbar(self):
        # Keep frequent actions visible; group the remainder in a menu instead of 12 cramped buttons.
        for b in (self.health_btn,self.bulk_btn,self.bulk_tag_btn,
                  self.tagcolors_btn,self.theme_btn,self.collections_btn,self.steam_btn,self.ftp_btn):
            b.hide()
        self.grid_btn.setText('▦  Grid / List')
        self.tools_btn=QPushButton('Tools  ▾')
        menu=QMenu(self)
        for label,callback in (
            ('Bulk ZIP backups',self.bulk_backup),
            ('Bulk tagging',self.bulk_tags),('Tag colors',self.edit_tag_color),
            ('Collections',self.show_collections),
            ('PS3 FTP',self.show_ftp),('Archive health',self.health_check),
            ('Appearance',self.choose_theme)):
            action=menu.addAction(label);action.triggered.connect(callback)
        self.tools_btn.setMenu(menu)
        # Visible above whichever content page is active.
        content=self.centralWidget().layout().itemAt(1).widget().layout()
        toolbar=content.itemAt(1).layout()
        toolbar.insertWidget(2,self.tools_btn)

    def _make_dashboard(self):
        self.dashboard_page=QScrollArea();self.dashboard_page.setWidgetResizable(True)
        self.dashboard_body=QWidget();layout=QVBoxLayout(self.dashboard_body)
        layout.setContentsMargins(5,8,8,16);layout.setSpacing(19)
        title=section('Archive overview');layout.addWidget(title)
        self.dashboard_stats=QHBoxLayout();self.dashboard_stats.setSpacing(12)
        self.dashboard_nums=[]
        for name,hint in [('Games','Titles organized'),('Saves','Archived copies'),('Verified','Manually tested'),('Backups','Versioned ZIPs')]:
            frame,num=card(name,'0',hint);self.dashboard_stats.addWidget(frame);self.dashboard_nums.append(num)
        layout.addLayout(self.dashboard_stats)
        columns=QHBoxLayout();columns.setSpacing(15)
        recent=QFrame();recent.setObjectName('quickPanel');rl=QVBoxLayout(recent);rl.setContentsMargins(18,17,18,17)
        rl.addWidget(section('Recent saves'));self.recent_list=QListWidget();self.recent_list.setMinimumHeight(240)
        self.recent_list.itemClicked.connect(self.open_recent)
        rl.addWidget(self.recent_list);columns.addWidget(recent,3)
        quick=QFrame();quick.setObjectName('quickPanel');ql=QVBoxLayout(quick);ql.setContentsMargins(18,17,18,17);ql.setSpacing(11)
        ql.addWidget(section('Quick actions'))
        for text,fn in [('＋  Import PS3 saves',self.import_folder),('＋  Import PC saves',self.import_pc),
                        ('▦  Browse game library',self.show_games),
                        ('✓  Check archive',self.health_check)]:
            b=QPushButton(text);b.clicked.connect(fn);ql.addWidget(b)
        self.disk_label=ui.label('',11,True);ql.addWidget(self.disk_label);ql.addStretch()
        columns.addWidget(quick,2);layout.addLayout(columns)
        explanation=ui.label('Original save files are never modified during import. Restores create a separate local folder; PS3 writes are not supported.',11,True)
        layout.addWidget(explanation);layout.addStretch()
        self.dashboard_page.setWidget(self.dashboard_body)
        self.dashboard_idx=self.stack.addWidget(self.dashboard_page)

    def _improve_inspector(self):
        # Save details has more controls since v0.3. Allow vertical scrolling instead of clipping buttons.
        splitter=self.stack.widget(1)
        detail=splitter.widget(1)
        scroll=QScrollArea();scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(350)
        scroll.setWidget(detail)
        splitter.insertWidget(1,scroll)
        splitter.setStretchFactor(0,3);splitter.setStretchFactor(1,2)
        self.save_list.setSpacing(2)

    def _update_navigation(self):
        self.sidebar=self.centralWidget().layout().itemAt(0).widget()
        sl=self.sidebar.layout()
        # The first navigation button is initially 'Game Library'. Add Dashboard above it.
        self.home_nav=QPushButton('◫  Dashboard');self.home_nav.setObjectName('nav');self.home_nav.setCheckable(True)
        self.home_nav.clicked.connect(self.show_dashboard)
        position=sl.indexOf(self.nav[0]);sl.insertWidget(position,self.home_nav)
        self.nav.insert(0,self.home_nav)
        self.nav[1].setText('▦  Game Library')
        self.nav[2].setText('▤  All Saves')
        self.nav[3].setText('⚙  Settings')
        for i in range(sl.count()):
            w=sl.itemAt(i).widget()
            if isinstance(w,QLabel) and 'v0.2' in w.text():w.setText('v0.4  •  PS3 + PC local archive')

    def activate_nav(self,idx):
        if not getattr(self,'_v04_ready',False):
            return super().activate_nav(idx)
        # v0.2 stack: games=0, saves=1, settings=2; v0.4 dashboard=3.
        mapping={0:self.dashboard_idx,1:0,2:1,3:2}
        self.stack.setCurrentIndex(mapping[idx])
        for i,b in enumerate(self.nav):b.setChecked(i==idx)
        showing_saves=(idx==2)
        self.filter.setVisible(showing_saves);self.tagfilter.setVisible(showing_saves)
        self.search.setVisible(idx in (1,2));self.platform.setVisible(idx in (1,2))
        self.grid_btn.setVisible(idx==1)
        self.bulk_btn.setVisible(False)

    def show_dashboard(self):
        if not getattr(self,'_v04_ready',False):
            return super().show_dashboard()
        self.mode='dashboard';self.activate_nav(0)
        self.heading.setText('Dashboard');self.subheading.setText('Your PS3, PS4 and PC saves, backups, and recent activity')
        d=self.archive.dashboard()
        for widget,value in zip(self.dashboard_nums,(d['games'],d['saves'],d['verified'],d['backups'])): widget.setText(str(value))
        self.disk_label.setText(f"Archived save data: {d['bytes']/1048576:.1f} MiB  •  {d['backups']} backup versions")
        self.recent_list.clear()
        for row in self.archive.list_saves()[:12]:
            item=QListWidgetItem(f"{row['game']}  ·  {row['label']}\n{row['platform']}  •  {row['category']}  •  {row['status']}")
            item.setData(Qt.ItemDataRole.UserRole,row);self.recent_list.addItem(item)
        if not self.recent_list.count():
            item=QListWidgetItem('No archived saves yet.')
            item.setFlags(Qt.ItemFlag.NoItemFlags);self.recent_list.addItem(item)
        self.statusBar().showMessage('Dashboard loaded — local archive ready')

    def open_recent(self,item):
        row=item.data(Qt.ItemDataRole.UserRole)
        if not row:return
        self.show_game_saves(row['game'], row['platform'], row['title_id'])
        for i in range(self.save_list.count()):
            it=self.save_list.item(i)
            if it.data(Qt.ItemDataRole.UserRole)['id']==row['id']:
                self.save_list.setCurrentItem(it);self.select_save(it);break

    def show_games(self):
        if not getattr(self,'_v04_ready',False):return super().show_games()
        self.mode='games';self.activate_nav(1)
        self.heading.setText('Game Library');self.subheading.setText('Browse by cover or switch to a compact list')
        self.refresh()

    def show_saves(self):
        if not getattr(self,'_v04_ready',False):return super().show_saves()
        self.mode='saves';self.activate_nav(2)
        self.heading.setText('All Saves');self.subheading.setText('Inspect, tag, back up, restore, and prepare releases')
        self.refresh()

    def show_settings(self):
        if not getattr(self,'_v04_ready',False):return super().show_settings()
        self.mode='settings';self.activate_nav(3)
        self.heading.setText('Settings');self.subheading.setText('Archive paths, appearance, and supported features')
        self.refresh()

    def toggle_grid(self):
        if not getattr(self,'_v04_ready',False):return super().toggle_grid()
        self._game_grid=not self._game_grid
        self.game_list.setViewMode(QListWidget.ViewMode.IconMode if self._game_grid else QListWidget.ViewMode.ListMode)
        self.refresh()

    def _cover_for(self,name):
        safe=re.sub(r'[^A-Za-z0-9_-]','_',name)[:80]
        found=sorted(self.archive_cover.glob(safe+'_*'))
        return found[0] if found else None

    def refresh(self,*args):
        if not getattr(self,'_v04_ready',False):return super().refresh(*args)
        if self.mode=='dashboard':return self.show_dashboard()
        super().refresh(*args)
        if self.mode=='games':
            grid=self._game_grid
            self.game_list.setViewMode(QListWidget.ViewMode.IconMode if grid else QListWidget.ViewMode.ListMode)
            self.game_list.setResizeMode(QListWidget.ResizeMode.Adjust)
            self.game_list.setMovement(QListWidget.Movement.Static)
            self.game_list.setWordWrap(True)
            self.game_list.setSpacing(12 if grid else 2)
            self.game_list.setIconSize(QSize(230,135) if grid else QSize(88,55))
            self.game_list.setGridSize(QSize(248,205) if grid else QSize())
            self.game_list.setUniformItemSizes(grid)
            for i in range(self.game_list.count()):
                item=self.game_list.item(i)
                tid,game,platform=item.data(Qt.ItemDataRole.UserRole)
                entry=self.archive.games(game,platform)
                matching=next((x for x in entry if x['title_id']==tid and x['game']==game),None)
                count=matching['saves'] if matching else '?'
                item.setIcon(cover_icon(game,platform,self._cover_for(game)))
                item.setText(f'{game}\n{platform} · {count} saves' if grid else f'{game}   |   {platform} · {tid}   |   {count} saves')
                item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter if grid else Qt.AlignmentFlag.AlignVCenter)
                item.setToolTip(f'{game}\nPlatform: {platform}\nTitle ID: {tid}\nSaves: {count}')
        elif self.mode=='saves':
            for i in range(self.save_list.count()):
                item=self.save_list.item(i)
                r=item.data(Qt.ItemDataRole.UserRole)
                visible=r.get('visibility','Private')
                tagtext='  ·  '.join(r.get('tags',[])[:3])
                item.setText(f"{r['game']}  ·  {r['label']}\n{r['platform']}  /  {r['category']}  /  {r['status']}  /  {visible}"+(f'\n{tagtext}' if tagtext else ''))
                item.setToolTip(f"{r['title_id']} • {r['region']}\n{', '.join(r.get('tags',[]))}")

    def select_game(self,item):
        # Clear old filters before opening a selected game. Preserve platform choice.
        title,game,platform=item.data(Qt.ItemDataRole.UserRole)
        self.search.clear();self.platform.setCurrentText(platform)
        self.filter.setCurrentText('All');self.tagfilter.setCurrentText('All')
        self.show_saves();self.search.setText(game if platform=='PC' else title)


def main():
    app=QApplication(sys.argv);app.setStyle('Fusion');app.setStyleSheet(STYLE)
    home=os.environ.get('Z_ARCHIVE_HOME')
    if home:root=Path(home)
    elif (Path(sys.argv[0]).resolve().parent/'portable.flag').is_file():root=Path(sys.argv[0]).resolve().parent/'ArchiveData'
    else:root=Path.home()/'Documents'/'Z PlayStation Save Archive'
    win=Window(root);win.show();sys.exit(app.exec())
