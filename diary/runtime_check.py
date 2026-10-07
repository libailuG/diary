"""打包验收：在临时目录验证 Qt、图片、PDF 与 SQLite 备份。"""
import json
import sys
import tempfile
import traceback
from pathlib import Path

from PyQt6.QtCore import QUrl, Qt, PYQT_VERSION_STR
from PyQt6.QtGui import QImage, QTextCursor, QTextDocument, QPdfWriter

from .editor import RichEditor
from .paths import application_dir
from .storage import Store
from .window import MainWindow


def check_runtime(report_path):
    report = {"ok": False, "frozen": bool(getattr(sys, "frozen", False)),
              "application_dir": str(application_dir()), "pyqt": PYQT_VERSION_STR}
    try:
        with tempfile.TemporaryDirectory(prefix="diary-runtime-check-") as directory:
            root = Path(directory)
            store = Store(root / "data")
            try:
                key = store.create("2026-01-01", "运行检查")
                editor = RichEditor(store)
                editor.diary_id = key
                editor.insertPlainText("中文运行检查")
                cursor = editor.textCursor()
                cursor.select(QTextCursor.SelectionType.Document)
                editor.setTextCursor(cursor)
                editor.char_format(setFontWeight=700)
                editor.moveCursor(QTextCursor.MoveOperation.End)
                editor.insertPlainText("\n")
                image = QImage(80, 60, QImage.Format.Format_RGB32)
                image.fill(Qt.GlobalColor.blue)
                editor.put_image(image)
                store.save(key, "运行检查", "2026-01-01", editor.toHtml(), editor.toPlainText(), ["测试"])
                editor.setHtml(store.get(key)["content_html"])
                assert "中文运行检查" in editor.toPlainText()
                image_id = store.conn.execute("SELECT id FROM attachments").fetchone()[0]
                loaded = editor.document().resource(QTextDocument.ResourceType.ImageResource, QUrl("diary-image://" + image_id))
                assert isinstance(loaded, QImage) and not loaded.isNull(), "图片加载失败"
                printer = QPdfWriter(str(root / "test.pdf"))
                printer.setResolution(1200)
                editor.document().print(printer)
                del printer
                assert (root / "test.pdf").read_bytes().startswith(b"%PDF"), "PDF 导出失败"
                store.backup(root / "backup.zip")
                store.restore(root / "backup.zip")
                assert "中文运行检查" in store.get(key)["content_text"], "备份恢复失败"
                window = MainWindow(store)
                window.daily_timer.stop()
                assert window.editor.toPlainText() == store.get(key)["content_text"]
                window.close()
                window.deleteLater()
                editor.deleteLater()
                report.update(ok=True, checks=["main_window", "rich_text", "image_resource", "pdf", "sqlite", "backup_restore"])
            finally:
                store.close()
    except Exception:
        report["error"] = traceback.format_exc()
    destination = Path(report_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1
