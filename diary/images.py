"""后台导入图片，原图附件与编辑预览分开处理。"""
import uuid
import base64
import html
import re
from pathlib import Path

from PyQt6.QtCore import QObject, QRunnable, QSize, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QImage, QImageReader

PREVIEW_LIMIT = 1600


def preview(image):
    if max(image.width(), image.height()) <= PREVIEW_LIMIT:
        return image
    return image.scaled(PREVIEW_LIMIT, PREVIEW_LIMIT, Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)


def read_preview(path):
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    size = reader.size()
    if max(size.width(), size.height()) > PREVIEW_LIMIT:
        reader.setScaledSize(size.scaled(QSize(PREVIEW_LIMIT, PREVIEW_LIMIT), Qt.AspectRatioMode.KeepAspectRatio))
    return preview(reader.read())


class ImportSignals(QObject):
    completed = pyqtSignal(object)


class ImageImport(QRunnable):
    def __init__(self, source, folder, original_name):
        super().__init__()
        self.source = source
        self.folder = Path(folder)
        self.original_name = original_name
        self.signals = ImportSignals()

    def run(self):
        try:
            result = self.prepare(self.source)
        except Exception as exc:
            result = dict(error=str(exc))
        self.signals.completed.emit(result)

    def prepare(self, source):
        path = None
        try:
            if isinstance(source, QImage):
                image = source
            elif isinstance(source, bytes):
                image = QImage.fromData(source)
            else:
                reader = QImageReader(str(source))
                reader.setAutoTransform(True)
                image = reader.read()
            if image.isNull():
                raise ValueError("无法读取图片，请选择有效的图片文件。")
            key = uuid.uuid4().hex
            self.folder.mkdir(parents=True, exist_ok=True)
            path = self.folder / f"{key}.png"
            if not image.save(str(path), "PNG"):
                raise OSError("图片保存失败。")
            return dict(key=key, path=path, original_name=self.original_name,
                          width=image.width(), height=image.height(), preview=preview(image))
        except Exception as exc:
            if path:
                path.unlink(missing_ok=True)
            raise


class HtmlImageImport(ImageImport):
    def __init__(self, raw, resources, folder):
        super().__init__(raw, folder, "粘贴图片")
        self.resources = resources

    def run(self):
        images = []
        try:
            raw = re.sub(r"<(script|style|iframe)\b[^>]*>.*?</\1>", "", self.source, flags=re.I | re.S)

            def replace(match):
                attr = re.search(r'''\bsrc\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))''', match[0], re.I)
                if not attr:
                    return ""
                url = html.unescape(next(v for v in attr.groups() if v is not None))
                if url in self.resources:
                    source = self.resources[url]
                elif url.startswith("data:image/"):
                    source = base64.b64decode(url.split(",", 1)[1], validate=True)
                elif QUrl(url).isLocalFile():
                    source = QUrl(url).toLocalFile()
                else:
                    return "[图片未导入，请使用“插入图片”添加本地图片]"
                item = self.prepare(source)
                images.append(item)
                width = min(item["width"], 560)
                return f'<img src="diary-image://{item["key"]}" width="{width}" height="{item["height"] * width / item["width"]:.0f}">'

            result = dict(html=re.sub(r"<img\b[^>]*>", replace, raw, flags=re.I), images=images)
        except Exception as exc:
            for item in images:
                item["path"].unlink(missing_ok=True)
            result = dict(error=str(exc))
        self.signals.completed.emit(result)
