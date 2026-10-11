"""富文本编辑器：图片资源由应用管理，粘贴时不依赖外部文件。"""
import re

from PyQt6.QtCore import QUrl, QThreadPool, pyqtSignal
from PyQt6.QtGui import (QImage, QTextCharFormat, QTextCursor, QTextDocument,
                         QTextImageFormat, QTextListFormat, QTextTableFormat)
from PyQt6.QtWidgets import QTextEdit

from .images import ImageImport, HtmlImageImport, preview, read_preview


class DiaryDocument(QTextDocument):
    def __init__(self, store, parent=None, preview_images=True):
        super().__init__(parent)
        self.store = store
        self.preview_images = preview_images
        self.setDocumentMargin(32)

    def loadResource(self, kind, name):
        if kind == QTextDocument.ResourceType.ImageResource:
            path = self.store.image_path(name.toString())
            return (read_preview(path) if self.preview_images else QImage(str(path))) if path else QImage()
        return None


class RichEditor(QTextEdit):
    attachmentError = pyqtSignal(str)
    importsChanged = pyqtSignal(int)

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.diary_id = None
        self._imports = {}
        self._image_pool = QThreadPool(self)
        self._image_pool.setMaxThreadCount(1)
        self.setDocument(DiaryDocument(store, self))
        self.setPlaceholderText("把今天值得记住的事情，慢慢写下来……")
        self.setAcceptRichText(True)
        self.setAutoFormatting(QTextEdit.AutoFormattingFlag.AutoBulletList)

    @property
    def pending_images(self):
        return len(self._imports)

    def import_image(self, source, original_name="粘贴图片", width=None):
        if not self.diary_id or self.isReadOnly():
            return
        job = ImageImport(source, self.store.attachments / self.diary_id, original_name)
        self._start_import(job, width)

    def _start_import(self, job, width=None):
        # The cursor tracks edits while the image is being prepared.
        self._imports[job] = (self.diary_id, QTextCursor(self.textCursor()), width)
        job.signals.completed.connect(lambda result, task=job: self._finish_image(task, result))
        self.importsChanged.emit(self.pending_images)
        self._image_pool.start(job)

    def _finish_image(self, job, result):
        diary_id, cursor, width = self._imports.pop(job)
        images = result.get("images", [] if "error" in result else [result])
        registered = set()
        try:
            if "error" in result:
                raise ValueError(result["error"])
            if diary_id != self.diary_id or cursor.document() != self.document():
                raise ValueError("日记已切换，图片未插入，请重新选择图片。")
            for item in images:
                self.store.register_image(diary_id, item["key"], item["path"], item["original_name"])
                registered.add(item["key"])
                self.document().addResource(QTextDocument.ResourceType.ImageResource,
                                            QUrl(f'diary-image://{item["key"]}'), item["preview"])
            if "html" in result:
                cursor.insertHtml(result["html"])
            else:
                self._insert_image(f'diary-image://{result["key"]}', result["preview"],
                                   result["width"], result["height"], width, cursor, move_cursor=False)
        except Exception as exc:
            self.attachmentError.emit(str(exc))
        finally:
            for item in images:
                if item["key"] not in registered:
                    item["path"].unlink(missing_ok=True)
            self.importsChanged.emit(self.pending_images)

    def put_image(self, image, original_name="粘贴图片", width=None):
        if not self.diary_id:
            raise ValueError("请先创建一篇日记。")
        name = self.store.add_image(self.diary_id, image, original_name)
        self._insert_image(name, preview(image), image.width(), image.height(), width, self.textCursor())

    def _insert_image(self, name, image, original_width, original_height, width, cursor, move_cursor=True):
        self.document().addResource(QTextDocument.ResourceType.ImageResource, QUrl(name), image)
        fmt = QTextImageFormat()
        fmt.setName(name)
        w = width or min(original_width, 560)
        fmt.setWidth(w)
        fmt.setHeight(original_height * w / original_width)
        cursor.insertImage(fmt)
        if move_cursor:
            self.setTextCursor(cursor)

    def insertFromMimeData(self, source):
        if self.isReadOnly() or not self.diary_id:
            return
        try:
            if source.hasHtml():
                raw = source.html()
                if re.search(r"<img\b", raw, re.I):
                    resources = {url: self.store.image_path(url) for url in set(re.findall(r"diary-image://[a-f0-9]{32}", raw))}
                    resources = {url: path for url, path in resources.items() if path}
                    self._start_import(HtmlImageImport(raw, resources, self.store.attachments / self.diary_id))
                else:
                    self.insertHtml(re.sub(r"<(script|style|iframe)\b[^>]*>.*?</\1>", "", raw, flags=re.I | re.S))
            elif source.hasImage():
                self.import_image(QImage(source.imageData()))
            elif source.hasUrls():
                for url in source.urls():
                    if url.isLocalFile():
                        self.import_image(url.toLocalFile(), url.fileName())
            else:
                self.insertPlainText(source.text())
        except Exception as exc:
            self.attachmentError.emit(str(exc))

    def canInsertFromMimeData(self, source):
        return bool(not self.isReadOnly() and self.diary_id and
                    (source.hasImage() or source.hasHtml() or source.hasUrls() or source.hasText()))

    def char_format(self, **properties):
        fmt = QTextCharFormat()
        for name, value in properties.items():
            getattr(fmt, name)(value)
        self.mergeCurrentCharFormat(fmt)
        self.setFocus()

    def list_style(self, numbered=False):
        fmt = QTextListFormat()
        fmt.setStyle(QTextListFormat.Style.ListDecimal if numbered else QTextListFormat.Style.ListDisc)
        fmt.setIndent(1)
        self.textCursor().createList(fmt)
        self.setFocus()

    def table(self, rows, columns):
        fmt = QTextTableFormat()
        fmt.setBorder(1)
        fmt.setCellPadding(8)
        fmt.setCellSpacing(0)
        cursor = self.textCursor()
        table = cursor.insertTable(rows, columns, fmt)
        self.setTextCursor(table.cellAt(0, 0).firstCursorPosition())
        self.setFocus()

    def clear_format(self):
        self.textCursor().setCharFormat(QTextCharFormat())
        self.setCurrentCharFormat(QTextCharFormat())
        self.setFocus()

    def apply_style(self, name):
        cursor = self.textCursor()
        cursor.beginEditBlock()
        fmt = QTextCharFormat()
        size, weight = {"正文": (12, 400), "标题一": (24, 700), "标题二": (18, 700), "引用": (12, 400)}[name]
        fmt.setFontPointSize(size)
        fmt.setFontWeight(weight)
        fmt.setFontItalic(name == "引用")
        block = cursor.blockFormat()
        block.setTopMargin(8)
        block.setBottomMargin(10)
        block.setLeftMargin(24 if name == "引用" else 0)
        block.setHeadingLevel({"标题一": 1, "标题二": 2}.get(name, 0))
        cursor.mergeBlockFormat(block)
        if not cursor.hasSelection():
            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
        cursor.mergeCharFormat(fmt)
        cursor.endEditBlock()
        self.mergeCurrentCharFormat(fmt)
        self.setFocus()
