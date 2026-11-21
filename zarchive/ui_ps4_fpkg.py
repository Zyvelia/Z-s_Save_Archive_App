"""Save Archive's PS4 dump scanning and package build panel."""
from pathlib import Path
from threading import Event

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .ps4_fpkg import CATEGORIES, build_packages, scan_build_inputs, validate_tool
from .ui_preferences import choose_sort, sorted_by, valid_sort

PACKAGE_SORT_FIELDS = ('Game', 'Title ID', 'Version', 'Package type', 'GP4', 'Dump path')


class PackageRow(QTreeWidgetItem):
    def __init__(self, labels, values):
        super().__init__(labels)
        self.sort_values = values
        self.sort_rank = 0

    def __lt__(self, other):
        return self.sort_rank < other.sort_rank


class DirectoryInput(QLineEdit):
    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        if len(urls) == 1 and urls[0].isLocalFile() and Path(urls[0].toLocalFile()).is_dir():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if len(urls) == 1 and urls[0].isLocalFile() and Path(urls[0].toLocalFile()).is_dir():
            self.setText(urls[0].toLocalFile())
            event.acceptProposedAction()
        else:
            event.ignore()


class PackageWorker(QThread):
    result = Signal(object)
    failed = Signal(str)
    log = Signal(str)
    progress = Signal(int)

    def __init__(self, operation, *args, **options):
        super().__init__()
        self.operation = operation
        self.args = args
        self.options = options
        self.cancelled = Event()

    def run(self):
        try:
            result = self.operation(*self.args, **self.options, cancelled=self.cancelled.is_set)
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.result.emit(result)


class FpkgPanel(QWidget):
    def __init__(self, archive, settings, parent=None):
        super().__init__(parent)
        self.archive, self.settings = archive, settings
        self.worker = None
        self.dump_items = []
        self.scan_path = None
        self.nearby_gp4s = {}
        self.package_sort = valid_sort(settings.load_settings().get('package_sort'),
                                       PACKAGE_SORT_FIELDS, [('Game', False)])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 23, 25, 19)
        layout.setSpacing(12)
        heading = QLabel('Dump to FPKG Builder')
        heading.setObjectName('newTitle')
        heading.setStyleSheet('font-size: 24px; font-weight: 700')
        layout.addWidget(heading)
        form = QFormLayout()
        layout.addLayout(form)

        def add(label, field, browse):
            row = QHBoxLayout()
            row.addWidget(field, 1)
            button = QPushButton('Browse…')
            button.clicked.connect(browse)
            row.addWidget(button)
            form.addRow(label, row)
            return button

        self.tool = QLineEdit(settings.path('orbis_pub_cmd'))
        self.tool.setPlaceholderText('orbis-pub-cmd.exe')
        self.tool_button = add('Package tool', self.tool, self.choose_tool)
        self.tool.editingFinished.connect(self.save_tool)
        self.source = DirectoryInput()
        self.source.setPlaceholderText('Choose or drop a PS4 dumps folder')
        self.source_button = add('Dumps input', self.source, lambda: self.choose_folder(self.source))
        self.output = DirectoryInput()
        self.output.setPlaceholderText('Choose or drop an output folder')
        self.output_button = add('Save packages to', self.output, lambda: self.choose_folder(self.output))
        self.existing_base = QLineEdit()
        self.existing_base.setPlaceholderText('Optional · for a patch-only build')
        self.base_button = add('Existing base PKG', self.existing_base, lambda: self.choose_file(
            self.existing_base, 'Choose an existing base package', 'PS4 package (*.pkg)'))
        self.existing_gp4 = QLineEdit()
        self.existing_gp4.setPlaceholderText('Optional · override the project for one selected dump')
        self.gp4_button = add('GP4 override', self.existing_gp4, lambda: self.choose_file(
            self.existing_gp4, 'Choose a build GP4', 'PS4 build project (*.gp4)'))
        options = QHBoxLayout()
        self.keystone = QCheckBox('Preserve sce_sys/keystone')
        self.keystone.setChecked(True)
        options.addWidget(self.keystone)
        self.storage = QComboBox()
        self.storage.addItems(['digital50', 'bd50'])
        options.addWidget(QLabel('Storage'))
        options.addWidget(self.storage)
        self.sort_button = QPushButton('Sort Packages…')
        self.sort_button.clicked.connect(self.configure_sort)
        options.addWidget(self.sort_button)
        options.addStretch()
        layout.addLayout(options)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['Game / package', 'Version', 'GP4', 'Archived saves / dump path'])
        self.tree.setAlternatingRowColors(True)
        self.tree.setColumnWidth(0, 410)
        self.tree.setColumnWidth(1, 95)
        self.tree.setColumnWidth(2, 175)
        self.tree.setMinimumHeight(155)
        layout.addWidget(self.tree, 2)
        self.status = QLabel('Choose a dumps folder and scan it.')
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        self.bar = QProgressBar()
        self.bar.setFormat('Current package: %p%')
        self.bar.setValue(0)
        layout.addWidget(self.bar)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        self.log.setStyleSheet('QPlainTextEdit { font-family: Consolas, monospace; }')
        self.log.hide()
        self.log_toggle = QPushButton('Show build log')
        self.log_toggle.setCheckable(True)
        self.log_toggle.toggled.connect(self.toggle_log)
        layout.addWidget(self.log, 1)
        actions = QHBoxLayout()
        self.scan_button = QPushButton('Scan dumps')
        self.scan_button.clicked.connect(self.scan)
        self.build_button = QPushButton('Build selected')
        self.build_button.setObjectName('newAction')
        self.build_button.clicked.connect(self.build)
        self.cancel_button = QPushButton('Cancel build')
        self.cancel_button.clicked.connect(self.cancel)
        for button in (self.scan_button, self.build_button, self.cancel_button, self.log_toggle):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.source.textChanged.connect(self.invalidate_scan)
        self.tree.itemChanged.connect(self.update_buttons)
        self.update_buttons()

    def toggle_log(self, shown):
        self.log.setVisible(shown)
        self.log_toggle.setText('Hide build log' if shown else 'Show build log')

    def choose_folder(self, field):
        chosen = QFileDialog.getExistingDirectory(self, 'Choose folder', field.text())
        if chosen:
            field.setText(chosen)

    def choose_file(self, field, title, file_filter):
        chosen, _ = QFileDialog.getOpenFileName(self, title, field.text(), file_filter)
        if chosen:
            field.setText(chosen)

    def choose_tool(self):
        chosen, _ = QFileDialog.getOpenFileName(self, 'Choose orbis-pub-cmd.exe', self.tool.text(),
                                                'Package tool (orbis-pub-cmd.exe)')
        if chosen:
            self.tool.setText(chosen)
            self.save_tool()

    def save_tool(self):
        value = self.tool.text().strip()
        try:
            tool = validate_tool(value) if value else ''
            self.settings.remember_path('orbis_pub_cmd', tool)
        except (OSError, ValueError) as exc:
            self.status.setText(str(exc))
            return False
        if tool:
            self.status.setText('Package tool path saved.')
        return True

    def invalidate_scan(self):
        self.scan_path = None
        self.nearby_gp4s = {}
        self.tree.clear()
        self.dump_items.clear()
        self.update_buttons()

    def selected(self):
        return [dump for item, dump in self.dump_items if item.checkState(0) == Qt.CheckState.Checked]

    def update_buttons(self, *_):
        active = self.worker is not None
        for widget in (self.tool, self.tool_button, self.source, self.source_button,
                       self.output, self.output_button, self.existing_base, self.base_button,
                       self.existing_gp4, self.gp4_button, self.tree, self.keystone, self.storage, self.sort_button):
            widget.setEnabled(not active)
        self.scan_button.setEnabled(not active and bool(self.source.text().strip()))
        self.build_button.setEnabled(not active and self.scan_path is not None and bool(self.selected()))
        self.cancel_button.setEnabled(active)

    def start(self, worker, result_handler):
        self.worker = worker
        self.cancel_button.setText('Cancel scan' if worker.operation is scan_build_inputs else 'Cancel build')
        worker.result.connect(result_handler)
        worker.failed.connect(self.show_failure)
        worker.log.connect(self.log.appendPlainText)
        worker.progress.connect(self.bar.setValue)
        worker.finished.connect(self.finish)
        self.update_buttons()
        worker.start()

    def scan(self):
        self.invalidate_scan()
        self.log.clear()
        self.status.setText('Scanning for PS4 dumps…')
        self.bar.setRange(0, 0)
        self.start(PackageWorker(scan_build_inputs, self.source.text().strip()), self.show_dumps)

    def show_dumps(self, result):
        dumps, errors, self.nearby_gp4s, notices = result
        saves = {}
        for row in self.archive.list_saves(platform='PS4'):
            title_id = row['title_id'].upper()
            saves[title_id] = saves.get(title_id, 0) + 1
        titles = {dump.title_id: dump.title for dump in dumps if dump.category == 'gd'}
        groups = {}
        for dump in dumps:
            if dump.title_id not in groups:
                count = saves.get(dump.title_id, 0)
                badge = f'{count} archived save(s)' if count else 'No archived saves'
                title = titles.get(dump.title_id, dump.title)
                group = PackageRow([f'{title} [{dump.title_id}]', '', '', badge],
                                   {'Game': title.casefold(), 'Title ID': dump.title_id})
                groups[dump.title_id] = group
                self.tree.addTopLevelItem(group)
            gp4 = self.nearby_gp4s.get(dump.path)
            child = PackageRow([f'{CATEGORIES[dump.category]} · {dump.title}',
                                dump.build_version or '—', gp4.name if gp4 else 'Generate', str(dump.path)],
                               {'Game': dump.title.casefold(), 'Title ID': dump.title_id,
                                'Version': tuple(int(part) for part in dump.build_version.split('.')
                                                 if part.isdigit()),
                                'Package type': tuple(CATEGORIES).index(dump.category),
                                'GP4': gp4.name.casefold() if gp4 else '', 'Dump path': str(dump.path).casefold()})
            child.setToolTip(2, str(gp4) if gp4 else 'Generate a GP4 when building this dump')
            child.setToolTip(3, str(dump.path))
            child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            child.setCheckState(0, Qt.CheckState.Unchecked)
            groups[dump.title_id].addChild(child)
            self.dump_items.append((child, dump))
        self.apply_package_sort()
        self.tree.expandAll()
        self.scan_path = self.source.text().strip()
        self.status.setText(f'{len(dumps)} package dump(s) in {len(groups)} game(s) · {len(errors)} skipped')
        if errors or notices:
            self.log.appendPlainText('\n'.join([*errors, *notices]))
            self.log_toggle.setChecked(True)

    def configure_sort(self):
        choice = choose_sort(self, PACKAGE_SORT_FIELDS, self.package_sort)
        if choice is None:
            return
        settings = self.settings.load_settings()
        settings['package_sort'] = choice
        try:
            self.settings.save_settings(settings)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, 'Could not save sort order', str(error))
            return
        self.package_sort = choice
        self.apply_package_sort()

    def apply_package_sort(self):
        groups = [self.tree.topLevelItem(index) for index in range(self.tree.topLevelItemCount())]
        for group in groups:
            children = [group.child(index) for index in range(group.childCount())]
            for index, child in enumerate(sorted_by(children, self.package_sort,
                                                    lambda item, field: item.sort_values[field])):
                child.sort_rank = index
            group.sort_values.update({
                'Version': max(child.sort_values['Version'] for child in children),
                'Package type': min(child.sort_values['Package type'] for child in children),
                'GP4': min(child.sort_values['GP4'] for child in children),
                'Dump path': min(child.sort_values['Dump path'] for child in children),
            })
        for index, group in enumerate(sorted_by(groups, self.package_sort,
                                                lambda item, field: item.sort_values[field])):
            group.sort_rank = index
        self.tree.sortItems(0, Qt.SortOrder.AscendingOrder)

    def build(self):
        if not self.output.text().strip() or not self.tool.text().strip():
            self.status.setText('Choose the package tool and output folder.')
            return
        if not self.save_tool():
            return
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.status.setText('Building selected packages…')
        self.log.clear()
        self.log_toggle.setChecked(True)
        worker = PackageWorker(build_packages, self.selected(), self.tool.text().strip(),
                               self.output.text().strip(), preserve_keystone=self.keystone.isChecked(),
                               storage_type=self.storage.currentText(),
                               existing_base=self.existing_base.text().strip(),
                               existing_gp4=self.existing_gp4.text().strip(), nearby_gp4s=self.nearby_gp4s)
        worker.options.update(log=worker.log.emit, progress=worker.progress.emit)
        self.start(worker, self.show_build)

    def show_build(self, paths):
        self.status.setText(f'Built {len(paths)} package(s).')
        self.bar.setValue(100)

    def show_failure(self, error):
        self.status.setText(error)
        self.log.appendPlainText(error)
        self.log_toggle.setChecked(True)

    def cancel(self):
        if self.worker:
            self.worker.cancelled.set()
            self.status.setText('Cancelling…')
            self.cancel_button.setEnabled(False)

    def finish(self):
        self.worker = None
        if self.bar.maximum() == 0:
            self.bar.setRange(0, 100)
            self.bar.setValue(0)
        self.update_buttons()
