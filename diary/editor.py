"""富文本编辑器：图片资源由应用管理，粘贴时不依赖外部文件。"""
import base64
import html
import re

from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtGui import (QImage, QTextCharFormat, QTextCursor, QTextDocument,
                         QTextImageFormat, QTextListFormat, QTextTableFormat)
from PyQt6.QtWidgets import QTextEdit


class DiaryDocument(QTextDocument):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setDocumentMargin(32)

    def loadResource(self, kind, name):
        if kind == QTextDocument.ResourceType.ImageResource:
            path = self.store.image_path(name.toString())
            return QImage(str(path)) if path else QImage()
        return None


class RichEditor(QTextEdit):
    attachmentError = pyqtSignal(str)

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.diary_id = None
        self.setDocument(DiaryDocument(store, self))
        self.setPlaceholderText("把今天值得记住的事情，慢慢写下来……")
        self.setAcceptRichText(True)
        self.setAutoFormatting(QTextEdit.AutoFormattingFlag.AutoBulletList)

    def put_image(self, image, original_name="粘贴图片", width=None):
        if not self.diary_id:
            raise ValueError("请先创建一篇日记。")
        name = self.store.add_image(self.diary_id, image, original_name)
        self.document().addResource(QTextDocument.ResourceType.ImageResource, QUrl(name), image)
        fmt = QTextImageFormat()
        fmt.setName(name)
        w = width or min(image.width(), 560)
        fmt.setWidth(w)
        fmt.setHeight(image.height() * w / image.width())
        cursor = self.textCursor()
        cursor.insertImage(fmt)
        self.setTextCursor(cursor)

    def insertFromMimeData(self, source):
        if self.isReadOnly() or not self.diary_id:
            return
        try:
            if source.hasHtml():
                raw = source.html()
                raw = re.sub(r"<(script|style|iframe)\b[^>]*>.*?</\1>", "", raw, flags=re.I | re.S)
                def image_tag(match):
                    src = re.search(r'''\bsrc\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))''', match[0], re.I)
                    if not src:
                        return ""
                    url = html.unescape(next(v for v in src.groups() if v is not None))
                    image = QImage()
                    if url.startswith("diary-image://"):
                        path = self.store.image_path(url)
                        if path:
                            image = QImage(str(path))
                    elif url.startswith("data:image/"):
                        image.loadFromData(base64.b64decode(url.split(",", 1)[1], validate=True))
                    elif QUrl(url).isLocalFile():
                        image = QImage(QUrl(url).toLocalFile())
                    # Remote/relative images cannot be reliably preserved offline.
                    if image.isNull():
                        return "[图片未导入，请使用“插入图片”添加本地图片]"
                    name = self.store.add_image(self.diary_id, image)
                    width = min(image.width(), 560)
                    return f'<img src="{name}" width="{width}" height="{image.height() * width / image.width():.0f}">'
                raw = re.sub(r"<img\b[^>]*>", image_tag, raw, flags=re.I)
                self.insertHtml(raw)
            elif source.hasImage():
                self.put_image(QImage(source.imageData()))
            elif source.hasUrls():
                for url in source.urls():
                    if url.isLocalFile():
                        self.put_image(QImage(url.toLocalFile()), url.fileName())
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
