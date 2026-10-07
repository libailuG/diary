"""主窗口、格式工具栏与日记操作。"""
import html
import logging
from datetime import date, datetime
from pathlib import Path

from PyQt6.QtCore import QDate, Qt, QTimer, QByteArray, QUrl
from PyQt6.QtGui import (QAction, QColor, QDesktopServices, QFont, QImage,
                         QKeySequence, QTextCharFormat, QTextCursor, QTextDocument)
from PyQt6.QtPrintSupport import QPrinter
from PyQt6.QtWidgets import (QApplication, QCalendarWidget, QCheckBox, QColorDialog,
    QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFileDialog, QFontComboBox,
    QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QSpinBox, QSplitter,
    QToolBar, QVBoxLayout, QWidget)

from .editor import DiaryDocument, RichEditor


LIGHT = """
QMainWindow, QDialog { background: #f4f6fa; color: #28354a; }
QWidget { font-family: 'Microsoft YaHei UI'; font-size: 10pt; }
QLineEdit, QDateEdit, QSpinBox, QComboBox { background: #ffffff; color: #28354a; border: 1px solid #dce2ed; border-radius: 5px; padding: 5px; }
QTextEdit { background: #fffefa; color: #263448; border: 1px solid #e0e4eb; border-radius: 8px; selection-background-color: #c4daf8; }
QListWidget { background: #ffffff; color: #28354a; border: 1px solid #e0e4eb; border-radius: 8px; outline: none; }
QListWidget::item { padding: 12px 8px; border-bottom: 1px solid #f0f2f6; }
QListWidget::item:selected { background: #e5eefc; color: #245ab1; border-left: 3px solid #527ec0; }
QPushButton { background: #ffffff; color: #354763; border: 1px solid #dce2ed; border-radius: 6px; padding: 7px 12px; }
QPushButton:hover { background: #e8effa; }
QPushButton:checked { background: #dce8fb; color: #245ab1; }
QPushButton#primary { background: #356bb2; color: white; border: none; padding: 11px; font-weight: bold; }
QLabel#brand { font-size: 22pt; font-weight: bold; color: #355e95; }
QLabel#muted { color: #78859b; }
QToolBar { background: #ffffff; border: none; spacing: 3px; padding: 5px; }
QToolButton { padding: 5px; color: #354763; }
QToolButton:checked { background: #dce8fb; }
QStatusBar { background: #eaf0f8; color: #53647d; }
QCalendarWidget QWidget { font-size: 9pt; }
QCalendarWidget QToolButton { color: #354763; }
"""

DARK = """
QMainWindow, QDialog, QWidget { background: #202735; color: #e2e8f2; font-family: 'Microsoft YaHei UI'; font-size: 10pt; }
QLineEdit, QDateEdit, QSpinBox, QComboBox { background: #2b3547; color: #e2e8f2; border: 1px solid #45526b; border-radius: 5px; padding: 5px; }
QTextEdit, QListWidget { background: #283143; color: #e2e8f2; border: 1px solid #43516a; border-radius: 8px; selection-background-color: #456ba2; }
QListWidget::item { padding: 12px 8px; border-bottom: 1px solid #344057; }
QListWidget::item:selected { background: #375783; color: #ffffff; }
QPushButton { background: #2b3547; border: 1px solid #45526b; border-radius: 6px; padding: 7px 12px; }
QPushButton:hover, QPushButton:checked, QToolButton:checked { background: #375783; }
QPushButton#primary { background: #4b79ba; color: white; padding: 11px; font-weight: bold; }
QLabel#brand { font-size: 22pt; font-weight: bold; color: #98bcf2; }
QLabel#muted { color: #99a9c2; }
QToolBar { border: none; spacing: 3px; padding: 5px; }
QToolButton { padding: 5px; }
"""


class MainWindow(QMainWindow):
    def __init__(self, store):
        super().__init__()
        self.store = store
        self.settings = store.read_settings()
        self.current_id = None
        self.loading = True
        self.dirty = False
        self.mode = "all"
        self.selected_date = None
        self.marked_dates = set()
        self.setWindowTitle("拾光日记 · 记录生活，留住片刻")
        self.resize(1360, 860)
        self.setMinimumSize(1060, 680)
        self.autosave = QTimer(self)
        self.autosave.setSingleShot(True)
        self.autosave.setInterval(1000)
        self.autosave.timeout.connect(self.save_current)
        self.build_ui()
        self.build_tools()
        self.build_menus()
        self.apply_theme(bool(self.settings.get("dark", False)))
        self.loading = False
        geometry = self.settings.get("geometry")
        if geometry:
            self.restoreGeometry(QByteArray.fromBase64(geometry.encode("ascii")))
        self.refresh_list(self.settings.get("last_id"), load=True)
        self.daily_timer = QTimer(self)
        self.daily_timer.setInterval(60 * 60 * 1000)
        self.daily_timer.timeout.connect(self.daily_backup)
        self.daily_timer.start()
        QTimer.singleShot(1000, self.daily_backup)

    def action(self, text, callback, shortcut=None, checkable=False):
        action = QAction(text, self)
        action.setCheckable(checkable)
        action.triggered.connect(callback)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        return action

    def button(self, text, callback, primary=False):
        button = QPushButton(text)
        if primary:
            button.setObjectName("primary")
        button.clicked.connect(callback)
        return button

    def build_ui(self):
        self.splitter = QSplitter()
        self.setCentralWidget(self.splitter)
        self.nav = QWidget()
        left = QVBoxLayout(self.nav)
        left.setContentsMargins(18, 20, 12, 12)
        brand = QLabel("拾光日记")
        brand.setObjectName("brand")
        subtitle = QLabel("写下此刻，留给未来")
        subtitle.setObjectName("muted")
        left.addWidget(brand)
        left.addWidget(subtitle)
        left.addSpacing(14)
        left.addWidget(self.button("＋  写一篇日记", self.new_diary, True))
        left.addSpacing(8)
        self.nav_buttons = {}
        for mode, text in (("all", "全部日记"), ("favorite", "★  我的收藏"), ("trash", "回收站")):
            button = self.button(text, lambda checked=False, m=mode: self.change_mode(m))
            button.setCheckable(True)
            self.nav_buttons[mode] = button
            left.addWidget(button)
        left.addSpacing(12)
        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(False)
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.calendar.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
        self.calendar.clicked.connect(self.filter_day)
        left.addWidget(self.calendar)
        left.addWidget(QLabel("蓝色日期表示有日记"))
        left.addWidget(QLabel("按标签浏览"))
        self.tag_filter = QComboBox()
        self.tag_filter.addItem("全部标签")
        self.tag_filter.currentIndexChanged.connect(self.filter_changed)
        left.addWidget(self.tag_filter)
        left.addWidget(self.button("写作统计", self.statistics))
        left.addStretch()
        left.addWidget(self.button("备份与恢复…", self.backup_dialog))
        left.addWidget(self.button("打开数据目录", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.store.root)))))
        self.nav.setMinimumWidth(260)
        self.nav.setMaximumWidth(330)
        self.splitter.addWidget(self.nav)

        self.middle = QWidget()
        mid = QVBoxLayout(self.middle)
        mid.setContentsMargins(5, 20, 10, 12)
        self.list_heading = QLabel("全部日记")
        self.list_heading.setStyleSheet("font-size: 16pt; font-weight: bold;")
        mid.addWidget(self.list_heading)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索标题或正文…")
        self.search.setClearButtonEnabled(True)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(250)
        self.search_timer.timeout.connect(self.filter_changed)
        self.search.textChanged.connect(lambda: self.search_timer.start())
        mid.addWidget(self.search)
        self.range_enabled = QCheckBox("限定日期范围")
        self.range_enabled.toggled.connect(self.filter_changed)
        mid.addWidget(self.range_enabled)
        row = QHBoxLayout()
        self.start_date = QDateEdit(QDate.currentDate().addMonths(-1))
        self.end_date = QDateEdit(QDate.currentDate())
        for widget in (self.start_date, self.end_date):
            widget.setCalendarPopup(True)
            widget.setDisplayFormat("yyyy-MM-dd")
            widget.dateChanged.connect(self.filter_changed)
            row.addWidget(widget)
        mid.addLayout(row)
        mid.addWidget(self.button("清除筛选", self.clear_filters))
        self.diary_list = QListWidget()
        self.diary_list.setWordWrap(True)
        self.diary_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.diary_list.currentItemChanged.connect(self.selection_changed)
        mid.addWidget(self.diary_list, 1)
        self.list_count = QLabel()
        self.list_count.setObjectName("muted")
        mid.addWidget(self.list_count)
        self.middle.setMinimumWidth(250)
        self.splitter.addWidget(self.middle)

        self.panel = QWidget()
        right = QVBoxLayout(self.panel)
        right.setContentsMargins(10, 20, 20, 12)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("给今天起一个标题")
        self.title_edit.setStyleSheet("font-size: 19pt; padding: 10px;")
        self.title_edit.textChanged.connect(self.changed)
        right.addWidget(self.title_edit)
        metadata = QHBoxLayout()
        self.entry_date = QDateEdit(QDate.currentDate())
        self.entry_date.setCalendarPopup(True)
        self.entry_date.setDisplayFormat("yyyy-MM-dd")
        self.entry_date.dateChanged.connect(self.changed)
        metadata.addWidget(self.entry_date)
        self.mood = QComboBox()
        self.mood.addItems(["心情（可选）", "开心", "平静", "充实", "疲惫", "难过"])
        self.mood.currentIndexChanged.connect(self.changed)
        metadata.addWidget(self.mood)
        self.favorite = QCheckBox("收藏")
        self.favorite.toggled.connect(self.changed)
        metadata.addWidget(self.favorite)
        metadata.addStretch()
        self.delete_button = self.button("移入回收站", self.delete_current)
        self.restore_button = self.button("恢复这篇日记", self.restore_current)
        metadata.addWidget(self.delete_button)
        metadata.addWidget(self.restore_button)
        right.addLayout(metadata)
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("标签：生活，工作，旅行（用逗号分隔）")
        self.tags_edit.textChanged.connect(self.changed)
        right.addWidget(self.tags_edit)
        self.editor = RichEditor(self.store)
        self.editor.document().setDefaultFont(QFont("Microsoft YaHei", 12))
        self.editor.textChanged.connect(self.changed)
        self.editor.attachmentError.connect(lambda text: self.error("图片导入失败", text))
        right.addWidget(self.editor, 1)
        self.meta_label = QLabel("点击“写一篇日记”开始记录。")
        self.meta_label.setObjectName("muted")
        right.addWidget(self.meta_label)
        self.splitter.addWidget(self.panel)
        self.splitter.setStretchFactor(2, 1)
        self.splitter.setSizes([270, 285, 805])
        self.save_label = QLabel("就绪")
        self.word_label = QLabel("0 字")
        self.statusBar().addWidget(self.save_label, 1)
        self.statusBar().addPermanentWidget(self.word_label)

    def build_tools(self):
        toolbar = QToolBar("编辑与格式")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.toolbar = toolbar
        self.new_action = self.action("新建", self.new_diary, "Ctrl+N")
        self.save_action = self.action("保存", self.save_current, "Ctrl+S")
        toolbar.addAction(self.new_action)
        toolbar.addAction(self.save_action)
        self.undo_action = self.action("撤销", self.editor.undo, "Ctrl+Z")
        self.redo_action = self.action("重做", self.editor.redo, "Ctrl+Y")
        toolbar.addAction(self.undo_action)
        toolbar.addAction(self.redo_action)
        self.undo_action.setEnabled(False)
        self.redo_action.setEnabled(False)
        self.editor.undoAvailable.connect(self.undo_action.setEnabled)
        self.editor.redoAvailable.connect(self.redo_action.setEnabled)
        toolbar.addSeparator()
        self.font_box = QFontComboBox()
        self.font_box.setMaximumWidth(170)
        self.font_box.setCurrentFont(QFont("Microsoft YaHei"))
        self.font_box.currentFontChanged.connect(lambda f: self.editor.char_format(setFontFamilies=[f.family()]))
        toolbar.addWidget(self.font_box)
        self.size_box = QSpinBox()
        self.size_box.setRange(6, 96)
        self.size_box.setValue(12)
        self.size_box.setSuffix(" pt")
        self.size_box.valueChanged.connect(lambda v: self.editor.char_format(setFontPointSize=v))
        toolbar.addWidget(self.size_box)
        self.bold_action = self.action("粗体", lambda v: self.editor.char_format(setFontWeight=700 if v else 400), "Ctrl+B", True)
        self.italic_action = self.action("斜体", lambda v: self.editor.char_format(setFontItalic=v), "Ctrl+I", True)
        self.underline_action = self.action("下划线", lambda v: self.editor.char_format(setFontUnderline=v), "Ctrl+U", True)
        self.strike_action = self.action("删除线", lambda v: self.editor.char_format(setFontStrikeOut=v), checkable=True)
        for action in (self.bold_action, self.italic_action, self.underline_action, self.strike_action):
            toolbar.addAction(action)
        toolbar.addAction(self.action("字色", lambda: self.pick_color(False)))
        toolbar.addAction(self.action("高亮", lambda: self.pick_color(True)))
        toolbar.addSeparator()
        self.style_box = QComboBox()
        self.style_box.addItems(["正文", "标题一", "标题二", "引用"])
        self.style_box.activated.connect(lambda: self.editor.apply_style(self.style_box.currentText()))
        toolbar.addWidget(self.style_box)
        self.editor.currentCharFormatChanged.connect(self.sync_format)
        self.editor.cursorPositionChanged.connect(lambda: self.sync_format(self.editor.currentCharFormat()))

    def build_menus(self):
        file = self.menuBar().addMenu("文件")
        file.addAction(self.new_action)
        file.addAction(self.save_action)
        file.addAction(self.action("使用模板新建…", self.template))
        file.addAction(self.action("导入 TXT…", self.import_text))
        export = file.addMenu("导出当前日记")
        for kind in ("TXT", "HTML", "PDF"):
            export.addAction(self.action(kind, lambda checked=False, k=kind: self.export_current(k)))
        file.addSeparator()
        file.addAction(self.action("备份与恢复…", self.backup_dialog))
        file.addAction(self.action("退出", self.close, "Ctrl+Q"))
        edit = self.menuBar().addMenu("编辑")
        edit.addAction(self.undo_action)
        edit.addAction(self.redo_action)
        for label, slot in (("剪切", self.editor.cut), ("复制", self.editor.copy), ("粘贴", self.editor.paste)):
            edit.addAction(self.action(label, slot))
        self.plain_paste_action = self.action("粘贴为纯文本", lambda: self.editor.insertPlainText(QApplication.clipboard().text()), "Ctrl+Shift+V")
        edit.addAction(self.plain_paste_action)
        edit.addAction(self.action("查找与替换…", self.find_dialog, "Ctrl+F"))
        edit.addSeparator()
        edit.addAction(self.action("移入回收站", self.delete_current))
        edit.addAction(self.action("清空回收站…", self.purge_trash))
        format_menu = self.menuBar().addMenu("格式")
        for a in (self.bold_action, self.italic_action, self.underline_action, self.strike_action):
            format_menu.addAction(a)
        for label, alignment in (("左对齐", Qt.AlignmentFlag.AlignLeft), ("居中", Qt.AlignmentFlag.AlignHCenter),
                                  ("右对齐", Qt.AlignmentFlag.AlignRight), ("两端对齐", Qt.AlignmentFlag.AlignJustify)):
            format_menu.addAction(self.action(label, lambda checked=False, align=alignment: self.editor.setAlignment(align)))
        format_menu.addAction(self.action("项目符号", lambda: self.editor.list_style(False)))
        format_menu.addAction(self.action("编号列表", lambda: self.editor.list_style(True)))
        format_menu.addAction(self.action("段落设置…", self.paragraph_dialog))
        format_menu.addAction(self.action("清除文字格式", self.editor.clear_format))
        insert = self.menuBar().addMenu("插入")
        insert.addAction(self.action("图片…", self.insert_image))
        insert.addAction(self.action("调整当前图片尺寸…", self.resize_image))
        insert.addAction(self.action("表格…", self.insert_table))
        insert.addAction(self.action("超链接…", self.insert_link))
        insert.addAction(self.action("当前时间", lambda: self.editor.insertPlainText(datetime.now().strftime("%H:%M"))))
        table = insert.addMenu("编辑当前表格")
        for label, op in (("下方插入行", "row"), ("右侧插入列", "column"), ("删除当前行", "delete_row"), ("删除当前列", "delete_column")):
            table.addAction(self.action(label, lambda checked=False, operation=op: self.table_operation(operation)))
        view = self.menuBar().addMenu("视图")
        self.focus_action = self.action("专注模式", self.focus_mode, "F11", True)
        self.dark_action = self.action("深色主题", self.apply_theme, checkable=True)
        self.dark_action.setChecked(bool(self.settings.get("dark", False)))
        view.addAction(self.focus_action)
        view.addAction(self.dark_action)
        view.addAction(self.action("放大正文", lambda: self.editor.zoomIn(1), "Ctrl+="))
        view.addAction(self.action("缩小正文", lambda: self.editor.zoomOut(1), "Ctrl+-"))
        view.addAction(self.action("写作统计", self.statistics))
        self.auto_backup_action = self.action("每日自动备份", self.set_auto_backup, checkable=True)
        self.auto_backup_action.setChecked(self.settings.get("auto_backup", True))
        file.addAction(self.auto_backup_action)
        help_menu = self.menuBar().addMenu("帮助")
        help_menu.addAction(self.action("关于拾光日记", lambda: QMessageBox.information(self, "拾光日记", "拾光日记 1.0\n本地富文本日记 · PyQt6 + SQLite\n\nCtrl+N 新建 · Ctrl+S 保存 · Ctrl+F 查找\nF11 专注模式\n\n数据仅保存在本机；应用未提供密码锁或磁盘加密。\n请定期将备份复制到其他磁盘。")))
        # Disable all mutating editor menus when no diary or viewing trash.
        self.edit_menu = edit
        self.format_menu = format_menu
        self.insert_menu = insert

    def error(self, title, text):
        logging.error("%s: %s", title, text)
        QMessageBox.critical(self, title, str(text))

    def changed(self, *args):
        if self.loading or not self.current_id or self.editor.isReadOnly():
            return
        self.dirty = True
        self.save_label.setText("未保存 · 停止输入后自动保存")
        self.word_label.setText(f"{len(''.join(self.editor.toPlainText().split()))} 字")
        self.autosave.start()

    def save_current(self, checked=False, refresh=True):
        self.autosave.stop()
        if not self.current_id or not self.dirty:
            return True
        try:
            self.save_label.setText("保存中…")
            self.store.save(self.current_id, self.title_edit.text(), self.entry_date.date().toString("yyyy-MM-dd"),
                            self.editor.toHtml(), self.editor.toPlainText(), self.tags_edit.text().replace("，", ",").split(","),
                            self.favorite.isChecked(), "" if self.mood.currentIndex() == 0 else self.mood.currentText())
            self.dirty = False
            self.save_label.setText("已保存 · " + datetime.now().strftime("%H:%M:%S"))
            if refresh:
                self.refresh_list(self.current_id, load=False)
            return True
        except Exception as exc:
            logging.exception("保存失败")
            self.save_label.setText("保存失败 · 按 Ctrl+S 重试")
            self.error("保存失败", f"{exc}\n\n当前内容仍在编辑器中，请重试保存。")
            return False

    def update_navigation(self):
        for mode, button in self.nav_buttons.items():
            button.setChecked(mode == self.mode)
        selected_tag = self.tag_filter.currentText()
        self.tag_filter.blockSignals(True)
        self.tag_filter.clear()
        self.tag_filter.addItem("全部标签")
        self.tag_filter.addItems(self.store.tags())
        self.tag_filter.setCurrentIndex(max(0, self.tag_filter.findText(selected_tag)))
        self.tag_filter.blockSignals(False)
        for value in self.marked_dates:
            self.calendar.setDateTextFormat(QDate.fromString(value, "yyyy-MM-dd"), QTextCharFormat())
        self.marked_dates = set(self.store.dates())
        fmt = QTextCharFormat()
        fmt.setForeground(QColor("#5a8ed4"))
        fmt.setFontWeight(700)
        for value in self.marked_dates:
            self.calendar.setDateTextFormat(QDate.fromString(value, "yyyy-MM-dd"), fmt)

    def refresh_list(self, preferred=None, load=True):
        self.update_navigation()
        kwargs = {}
        if self.range_enabled.isChecked():
            kwargs = dict(start=self.start_date.date().toString("yyyy-MM-dd"), end=self.end_date.date().toString("yyyy-MM-dd"))
        rows = self.store.list(self.search.text().strip(), self.mode, self.selected_date,
                               self.tag_filter.currentText() if self.tag_filter.currentIndex() > 0 else None, **kwargs)
        self.diary_list.blockSignals(True)
        self.diary_list.clear()
        target = None
        for row in rows:
            summary = " ".join(row["content_text"].split())[:55] or "还没有正文，写下第一句话吧。"
            title = ("★ " if row["favorite"] else "") + row["title"]
            item = QListWidgetItem(f"{title}\n{row['entry_date']}\n{summary}")
            item.setData(Qt.ItemDataRole.UserRole, row["id"])
            item.setToolTip(row["title"])
            self.diary_list.addItem(item)
            if row["id"] == preferred:
                target = item
        if load and target is None and self.diary_list.count():
            target = self.diary_list.item(0)
        self.diary_list.setCurrentItem(target)
        self.diary_list.blockSignals(False)
        heading = {"all": "全部日记", "favorite": "我的收藏", "trash": "回收站"}[self.mode]
        self.list_heading.setText(self.selected_date or heading)
        self.list_count.setText(f"共 {len(rows)} 篇" + (" · 没有匹配的日记" if not rows else ""))
        if load:
            self.load_diary(target.data(Qt.ItemDataRole.UserRole) if target else None)

    def selection_changed(self, item, previous):
        if not self.save_current(refresh=False):
            self.diary_list.blockSignals(True)
            self.diary_list.setCurrentItem(previous)
            self.diary_list.blockSignals(False)
            return
        self.load_diary(item.data(Qt.ItemDataRole.UserRole) if item else None)

    def load_diary(self, key):
        self.loading = True
        self.autosave.stop()
        self.current_id = key
        self.editor.diary_id = key
        row = self.store.get(key) if key else None
        editable = bool(row and row["deleted_at"] is None)
        self.panel.setEnabled(bool(row))
        for widget in (self.title_edit, self.tags_edit):
            widget.setReadOnly(not editable)
        for widget in (self.entry_date, self.mood, self.favorite):
            widget.setEnabled(editable)
        self.editor.setReadOnly(not editable)
        self.format_menu.setEnabled(editable)
        self.insert_menu.setEnabled(editable)
        self.edit_menu.setEnabled(True)
        self.plain_paste_action.setEnabled(editable)
        for widget in (self.font_box, self.size_box, self.style_box):
            widget.setEnabled(editable)
        for action in (self.bold_action, self.italic_action, self.underline_action, self.strike_action):
            action.setEnabled(editable)
        self.delete_button.setVisible(editable)
        self.restore_button.setVisible(bool(row and not editable))
        self.title_edit.setText(row["title"] if row else "")
        self.entry_date.setDate(QDate.fromString(row["entry_date"], "yyyy-MM-dd") if row else QDate.currentDate())
        self.tags_edit.setText("，".join(row["tags"]) if row else "")
        self.favorite.setChecked(bool(row and row["favorite"]))
        self.mood.setCurrentIndex(max(0, self.mood.findText(row["mood"])) if row else 0)
        # A fresh document avoids retaining another diary's image cache / undo history.
        document = DiaryDocument(self.store, self.editor)
        document.setDefaultFont(QFont("Microsoft YaHei", 12))
        old_document = self.editor.document()
        self.editor.setDocument(document)
        if old_document.parent() == self.editor:
            old_document.deleteLater()
        self.editor.setHtml(row["content_html"] if row else "")
        document.setModified(False)
        self.undo_action.setEnabled(False)
        self.redo_action.setEnabled(False)
        self.meta_label.setText(f"创建：{row['created_at'][:19].replace('T', ' ')}    修改：{row['updated_at'][:19].replace('T', ' ')}" if row else "点击“写一篇日记”开始记录。")
        self.word_label.setText(f"{len(''.join(self.editor.toPlainText().split()))} 字")
        self.save_label.setText("回收站 · 只读" if row and not editable else "已保存" if row else "欢迎 · 从一篇日记开始")
        self.dirty = False
        self.loading = False
        self.sync_format(self.editor.currentCharFormat())

    def change_mode(self, mode):
        if self.save_current(refresh=False):
            self.mode = mode
            self.selected_date = None
            self.refresh_list(load=True)

    def filter_day(self, day):
        if self.save_current(refresh=False):
            self.mode = "all"
            self.selected_date = day.toString("yyyy-MM-dd")
            self.refresh_list(load=True)

    def filter_changed(self, *args):
        if not self.loading and self.save_current(refresh=False):
            self.refresh_list(self.current_id, load=True)

    def reset_filters(self):
        self.loading = True
        self.search_timer.stop()
        self.search.clear()
        self.range_enabled.setChecked(False)
        self.tag_filter.setCurrentIndex(0)
        self.selected_date = None
        self.loading = False

    def clear_filters(self):
        if self.save_current(refresh=False):
            self.reset_filters()
            self.refresh_list(self.current_id, load=True)

    def new_diary(self, checked=False, content="", title=""):
        if not self.save_current(refresh=False):
            return
        target_date = self.selected_date or QDate.currentDate().toString("yyyy-MM-dd")
        doc = QTextDocument()
        doc.setHtml(content)
        key = self.store.create(target_date, title or "未命名日记", content, doc.toPlainText())
        self.mode = "all"
        self.reset_filters()
        self.refresh_list(key, load=True)
        self.title_edit.setFocus()
        self.title_edit.selectAll()

    def delete_current(self):
        if not self.current_id or self.editor.isReadOnly():
            return
        if not self.save_current(refresh=False):
            return
        if QMessageBox.question(self, "移入回收站", "将这篇日记移入回收站？可以随时恢复。") == QMessageBox.StandardButton.Yes:
            self.store.delete(self.current_id)
            self.refresh_list(load=True)

    def restore_current(self):
        if self.current_id:
            key = self.current_id
            self.store.undelete(key)
            self.mode = "all"
            self.reset_filters()
            self.refresh_list(key, load=True)

    def purge_trash(self):
        if not self.save_current(refresh=False):
            return
        if QMessageBox.question(self, "永久删除", "永久删除回收站中的所有日记及图片？\n此操作无法撤销，建议先备份。", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.store.purge()
            self.refresh_list(load=True)

    def sync_format(self, fmt):
        for action, value in ((self.bold_action, fmt.fontWeight() >= 600), (self.italic_action, fmt.fontItalic()),
                              (self.underline_action, fmt.fontUnderline()), (self.strike_action, fmt.fontStrikeOut())):
            action.setChecked(value)
        self.font_box.blockSignals(True)
        self.font_box.setCurrentFont(self.editor.currentFont())
        self.font_box.blockSignals(False)
        self.size_box.blockSignals(True)
        self.size_box.setValue(round(fmt.fontPointSize() or self.editor.document().defaultFont().pointSizeF()))
        self.size_box.blockSignals(False)
        level = self.editor.textCursor().blockFormat().headingLevel()
        self.style_box.setCurrentText({1: "标题一", 2: "标题二"}.get(level, "引用" if self.editor.textCursor().blockFormat().leftMargin() > 0 else "正文"))

    def pick_color(self, background):
        if self.editor.isReadOnly():
            return
        color = QColorDialog.getColor(parent=self, title="选择高亮颜色" if background else "选择文字颜色")
        if color.isValid():
            self.editor.char_format(**{"setBackground" if background else "setForeground": color})

    def insert_image(self):
        if self.editor.isReadOnly():
            return
        path, _ = QFileDialog.getOpenFileName(self, "插入图片", "", "图片 (*.png *.jpg *.jpeg *.bmp *.webp)")
        if path:
            try:
                self.editor.put_image(QImage(path), Path(path).name)
            except Exception as exc:
                self.error("图片导入失败", exc)

    def resize_image(self):
        cursor = self.editor.textCursor()
        if not cursor.charFormat().isImageFormat():
            cursor.movePosition(QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor)
        if not cursor.charFormat().isImageFormat():
            QMessageBox.information(self, "图片尺寸", "请把光标放在图片后，或先选中图片。")
            return
        fmt = cursor.charFormat().toImageFormat()
        width, ok = QInputDialog.getInt(self, "图片尺寸", "显示宽度（像素）", int(fmt.width() or 400), 30, 1800)
        if ok:
            fmt.setHeight(fmt.height() * width / fmt.width() if fmt.width() else width)
            fmt.setWidth(width)
            if not cursor.hasSelection():
                cursor.movePosition(QTextCursor.MoveOperation.PreviousCharacter, QTextCursor.MoveMode.KeepAnchor)
            cursor.setCharFormat(fmt)

    def insert_table(self):
        rows, ok = QInputDialog.getInt(self, "插入表格", "行数", 3, 1, 30)
        if not ok:
            return
        columns, ok = QInputDialog.getInt(self, "插入表格", "列数", 3, 1, 12)
        if ok:
            self.editor.table(rows, columns)

    def table_operation(self, operation):
        cursor = self.editor.textCursor()
        table = cursor.currentTable()
        if table is None:
            QMessageBox.information(self, "编辑表格", "请先将光标放在表格单元格内。")
            return
        cell = table.cellAt(cursor)
        if operation == "row":
            table.insertRows(cell.row() + 1, 1)
        elif operation == "column":
            table.insertColumns(cell.column() + 1, 1)
        elif operation == "delete_row":
            table.removeRows(cell.row(), 1)
        else:
            table.removeColumns(cell.column(), 1)

    def insert_link(self):
        url, ok = QInputDialog.getText(self, "插入链接", "网址（https://…）")
        if not ok or not url:
            return
        parsed = QUrl.fromUserInput(url)
        if parsed.scheme() not in ("http", "https", "mailto"):
            QMessageBox.warning(self, "无效链接", "仅支持 http、https 和 mailto 链接。")
            return
        cursor = self.editor.textCursor()
        label = cursor.selectedText() or url
        cursor.insertHtml(f'<a href="{html.escape(parsed.toString(), quote=True)}">{html.escape(label)}</a>')

    def paragraph_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("段落设置")
        form = QFormLayout(dialog)
        block = self.editor.textCursor().blockFormat()
        fields = {}
        for key, label, value in (("line", "行距（%）", block.lineHeight() or 150), ("before", "段前（pt）", block.topMargin()),
                                  ("after", "段后（pt）", block.bottomMargin()), ("indent", "左缩进（pt）", block.leftMargin())):
            spin = QSpinBox()
            spin.setRange(100 if key == "line" else 0, 300)
            spin.setValue(int(value))
            form.addRow(label, spin)
            fields[key] = spin
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec():
            block.setLineHeight(fields["line"].value(), 1)
            block.setTopMargin(fields["before"].value())
            block.setBottomMargin(fields["after"].value())
            block.setLeftMargin(fields["indent"].value())
            self.editor.textCursor().mergeBlockFormat(block)

    def find_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("查找与替换 · 当前日记")
        form = QFormLayout(dialog)
        query, replacement = QLineEdit(), QLineEdit()
        form.addRow("查找", query)
        form.addRow("替换为", replacement)
        feedback = QLabel()
        def find_next():
            if not query.text():
                return
            if not self.editor.find(query.text()):
                self.editor.moveCursor(QTextCursor.MoveOperation.Start)
                found = self.editor.find(query.text())
                feedback.setText("已从头查找" if found else "没有找到匹配文字")
        def replace_one():
            if query.text() and self.editor.textCursor().selectedText() == query.text():
                self.editor.textCursor().insertText(replacement.text())
            find_next()
        def replace_all():
            if not query.text():
                return
            document = self.editor.document()
            group = QTextCursor(document)
            group.beginEditBlock()
            cursor = QTextCursor(document)
            count = 0
            while True:
                cursor = document.find(query.text(), cursor, QTextDocument.FindFlag.FindCaseSensitively)
                if cursor.isNull():
                    break
                cursor.insertText(replacement.text())
                count += 1
            group.endEditBlock()
            feedback.setText(f"已替换 {count} 处")
        form.addRow(self.button("查找下一个", find_next))
        one = self.button("替换当前", replace_one)
        all_button = self.button("全部替换（区分大小写）", replace_all)
        one.setEnabled(not self.editor.isReadOnly())
        all_button.setEnabled(not self.editor.isReadOnly())
        form.addRow(one)
        form.addRow(all_button)
        form.addRow(feedback)
        dialog.resize(360, 280)
        dialog.exec()

    def template(self):
        name, ok = QInputDialog.getItem(self, "日记模板", "选择模板", ["每日总结", "感恩日记", "旅行记录"], 0, False)
        if ok:
            sections = {"每日总结": ["今天发生了什么", "今天的收获", "明天想做的事"],
                        "感恩日记": ["今天感谢的人", "让我开心的小事", "给自己的话"],
                        "旅行记录": ["今天去了哪里", "沿途见闻", "值得记住的瞬间"]}[name]
            content = "".join(f"<h2>{s}</h2><p><br></p>" for s in sections)
            self.new_diary(content=content, title=name)

    def import_text(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入文本日记", "", "文本文件 (*.txt)")
        if path:
            try:
                raw = Path(path).read_text(encoding="utf-8-sig")
            except UnicodeDecodeError:
                try:
                    raw = Path(path).read_text(encoding="gb18030")
                except Exception as exc:
                    self.error("导入失败", exc)
                    return
            except Exception as exc:
                self.error("导入失败", exc)
                return
            self.new_diary(content="<p>" + html.escape(raw).replace("\n", "<br>") + "</p>", title=Path(path).stem)

    def export_current(self, kind):
        if not self.current_id or not self.save_current():
            return
        row = self.store.get(self.current_id)
        suffix = kind.lower()
        path, _ = QFileDialog.getSaveFileName(self, f"导出 {kind}", f"日记-{row['entry_date']}.{suffix}", f"{kind} (*.{suffix})")
        if not path:
            return
        if not Path(path).suffix:
            path += "." + suffix
        try:
            if kind == "TXT":
                Path(path).write_text(f"{row['title']}\n{row['entry_date']}\n标签：{'、'.join(row['tags'])}\n\n{row['content_text']}", encoding="utf-8")
            else:
                content = row["content_html"]
                header = f"<h1>{html.escape(row['title'])}</h1><p>{row['entry_date']}　{html.escape('、'.join(row['tags']))}</p><hr>"
                import re
                content = re.sub(r"(<body\b[^>]*>)", lambda m: m[0] + header, content, count=1, flags=re.I)
                if kind == "HTML":
                    Path(path).write_text(self.store.portable_html(content), encoding="utf-8")
                else:
                    document = DiaryDocument(self.store)
                    document.setDefaultFont(QFont("Microsoft YaHei", 12))
                    document.setHtml(content)
                    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
                    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
                    printer.setOutputFileName(path)
                    document.print(printer)
                    if not Path(path).exists() or Path(path).stat().st_size == 0:
                        raise OSError("PDF 文件未成功生成。")
            self.statusBar().showMessage(f"已导出：{path}", 8000)
        except Exception as exc:
            self.error("导出失败", exc)

    def backup_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("备份与恢复")
        layout = QVBoxLayout(dialog)
        label = QLabel("完整备份包含所有日记、标签、回收站和图片。\n恢复会替换当前日记数据，并先保存恢复前的完整备份。\n每日自动备份在应用运行时执行，请定期复制到其他磁盘。")
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addWidget(self.button("创建完整备份…", self.manual_backup, True))
        layout.addWidget(self.button("从备份恢复…", lambda: self.restore_backup(dialog)))
        layout.addWidget(self.button("打开备份目录", self.open_backups))
        layout.addWidget(QLabel(f"数据位置：{self.store.root}"))
        dialog.resize(540, 230)
        dialog.exec()

    def open_backups(self):
        folder = self.store.root / "backups"
        folder.mkdir(exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def manual_backup(self):
        if not self.save_current():
            return
        path, _ = QFileDialog.getSaveFileName(self, "创建完整备份", f"拾光日记-{datetime.now():%Y%m%d-%H%M%S}.zip", "备份文件 (*.zip)")
        if path:
            try:
                if not Path(path).suffix:
                    path += ".zip"
                self.store.backup(path)
                QMessageBox.information(self, "备份完成", f"完整备份已保存：\n{path}")
            except Exception as exc:
                self.error("备份失败", exc)

    def restore_backup(self, dialog):
        if not self.save_current():
            return
        path, _ = QFileDialog.getOpenFileName(self, "恢复完整备份", "", "备份文件 (*.zip)")
        if not path:
            return
        if QMessageBox.question(self, "确认恢复", "用此备份替换当前所有日记和图片？\n恢复前会自动保留当前数据的完整备份。", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        try:
            safety = self.store.restore(path)
            self.current_id = None
            self.dirty = False
            self.mode = "all"
            self.reset_filters()
            self.refresh_list(load=True)
            dialog.accept()
            QMessageBox.information(self, "恢复完成", f"日记已恢复。\n恢复前数据备份：\n{safety}")
        except Exception as exc:
            self.error("恢复失败", exc)

    def daily_backup(self):
        if not self.settings.get("auto_backup", True) or not self.store.list():
            return
        folder = self.store.root / "backups"
        target = folder / f"自动备份-{date.today().isoformat()}.zip"
        if target.exists():
            return
        try:
            if self.save_current():
                self.store.backup(target)
                self.statusBar().showMessage("今日自动备份已完成", 6000)
        except Exception:
            logging.exception("自动备份失败")
            self.statusBar().showMessage("自动备份失败，请使用文件菜单手动备份", 15000)

    def set_auto_backup(self, enabled):
        self.settings["auto_backup"] = enabled
        self.store.write_settings(self.settings)
        if enabled:
            self.daily_backup()

    def apply_theme(self, dark):
        self.settings["dark"] = dark
        self.setStyleSheet(DARK if dark else LIGHT)

    def focus_mode(self, enabled):
        self.nav.setVisible(not enabled)
        self.middle.setVisible(not enabled)

    def statistics(self):
        if not self.save_current():
            return
        rows = self.store.list()
        dates = set(r["entry_date"] for r in rows)
        streak = 0
        day = QDate.currentDate()
        if day.toString("yyyy-MM-dd") not in dates:
            day = day.addDays(-1)
        while day.toString("yyyy-MM-dd") in dates:
            streak += 1
            day = day.addDays(-1)
        words = sum(len("".join(r["content_text"].split())) for r in rows)
        month = date.today().isoformat()[:7]
        count = sum(r["entry_date"].startswith(month) for r in rows)
        QMessageBox.information(self, "写作统计", f"日记总数：{len(rows)} 篇\n记录天数：{len(dates)} 天\n正文总字数：{words} 字（不含空白）\n本月日记：{count} 篇\n截至今天或昨天的连续记录：{streak} 天")

    def closeEvent(self, event):
        if not self.save_current():
            event.ignore()
            return
        self.settings["geometry"] = bytes(self.saveGeometry().toBase64()).decode("ascii")
        self.settings["last_id"] = self.current_id
        try:
            self.store.write_settings(self.settings)
        except Exception as exc:
            logging.exception("设置保存失败")
            self.error("设置保存失败", f"日记已保存，但窗口设置未保存：{exc}")
        event.accept()
