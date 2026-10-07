"""使用临时数据目录验证保存、附件、备份和实际 Qt 窗口。"""
import hashlib
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDate, QMimeData, Qt
from PyQt6.QtGui import QImage, QTextCursor
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox
from PyQt6.QtTest import QTest

from diary.storage import Store
from diary.window import MainWindow

APP = QApplication.instance() or QApplication([])


class DiaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "data")
        self.windows = []
        self.errors = []
        self.mock_error = patch.object(QMessageBox, "critical", side_effect=lambda *args: self.errors.append(args[2])).start()
        patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok).start()

    def tearDown(self):
        for window in self.windows:
            window.dirty = False
            window.close()
            window.deleteLater()
        APP.processEvents()
        self.store.close()
        patch.stopall()
        self.temp.cleanup()

    def window(self):
        window = MainWindow(self.store)
        window.daily_timer.stop()
        window.settings["auto_backup"] = False
        self.windows.append(window)
        return window

    def test_repository_search_tags_and_trash(self):
        key = self.store.create("2026-10-07")
        self.store.save(key, "旅途", "2026-10-07", "<b>湖边</b>", "湖边", ["旅行", "旅行", " 生活 "], True)
        self.assertEqual(self.store.get(key)["tags"], ["旅行", "生活"])
        self.assertEqual(len(self.store.list("湖边", "favorite", tag="旅行")), 1)
        self.assertEqual(self.store.list("%"), [])
        self.store.delete(key)
        self.assertEqual(self.store.list(), [])
        self.assertEqual(len(self.store.list(mode="trash")), 1)
        self.store.undelete(key)
        self.assertEqual(len(self.store.list()), 1)
        self.store.delete(key)
        self.store.purge()
        self.assertIsNone(self.store.get(key))

    def test_backup_restore_images_and_safety_copy(self):
        key = self.store.create("2026-10-07", "原始内容")
        image = QImage(80, 60, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.red)
        url = self.store.add_image(key, image)
        self.store.save(key, "原始内容", "2026-10-07", f'<img src="{url}">', "", ["图片"])
        archive = self.root / "backup.zip"
        self.store.backup(archive)
        self.store.save(key, "后来修改", "2026-10-07", "<p>不同内容</p>", "不同内容", [])
        safety = self.store.restore(archive)
        self.assertTrue(safety.exists())
        self.assertEqual(self.store.get(key)["title"], "原始内容")
        self.assertTrue(self.store.image_path(url).exists())
        self.assertIn("data:image/png;base64,", self.store.portable_html(self.store.get(key)["content_html"]))
        # Restoring a safety copy also works, including its old content.
        self.store.restore(safety)
        self.assertEqual(self.store.get(key)["title"], "后来修改")

    def test_reject_corrupt_and_traversal_backup_without_replacing_data(self):
        key = self.store.create("2026-10-07", "保留我")
        archive = self.root / "bad.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("diary.db", b"broken")
            z.writestr("manifest.json", json.dumps({"format": 1, "files": {"diary.db": "bad"}}))
        with self.assertRaises(ValueError):
            self.store.restore(archive)
        self.assertEqual(self.store.get(key)["title"], "保留我")
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("diary.db", b"broken")
            z.writestr("attachments/../../outside.txt", b"x")
            z.writestr("manifest.json", json.dumps({"format": 1, "files": {
                "diary.db": hashlib.sha256(b"broken").hexdigest(),
                "attachments/../../outside.txt": hashlib.sha256(b"x").hexdigest()}}))
        with self.assertRaises(ValueError):
            self.store.restore(archive)
        self.assertFalse((self.store.root / "outside.txt").exists())
        self.assertEqual(self.store.get(key)["title"], "保留我")

    def test_real_window_autosave_format_and_switch(self):
        w = self.window()
        w.new_diary()
        first = w.current_id
        w.title_edit.setText("今天的测试")
        w.tags_edit.setText("工作，生活")
        w.editor.insertPlainText("中文日记正文")
        cursor = w.editor.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        w.editor.setTextCursor(cursor)
        w.bold_action.trigger()
        QTest.qWait(1200)
        self.assertFalse(w.dirty)
        self.assertEqual(self.store.get(first)["content_text"], "中文日记正文")
        w.new_diary()
        second = w.current_id
        w.editor.insertPlainText("另一篇")
        w.diary_list.setCurrentRow(1)
        self.assertEqual(w.current_id, first)
        self.assertEqual(self.store.get(second)["content_text"], "另一篇")
        cursor = w.editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        cursor.movePosition(QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor)
        self.assertGreaterEqual(cursor.charFormat().fontWeight(), 600)
        self.assertEqual(w.editor.toPlainText(), "中文日记正文")
        self.assertEqual(self.errors, [])

    def test_failed_save_keeps_content_and_blocks_close_and_switch(self):
        first = self.store.create("2026-10-06", "第一篇")
        self.store.create("2026-10-07", "第二篇")
        w = self.window()
        w.load_diary(first)
        w.editor.insertPlainText("尚未保存的重要内容")
        with patch.object(self.store, "save", side_effect=OSError("模拟磁盘写入失败")):
            with self.assertLogs(level="ERROR"):
                self.assertFalse(w.save_current())
                w.new_diary()
                self.assertEqual(w.current_id, first)
                self.assertFalse(w.close())
                self.assertTrue(w.dirty)
                self.assertEqual(w.editor.toPlainText(), "尚未保存的重要内容")
        self.assertTrue(w.save_current())
        self.assertEqual(self.store.get(first)["content_text"], "尚未保存的重要内容")

    def test_image_table_paste_and_export(self):
        w = self.window()
        w.new_diary()
        image = QImage(160, 100, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.blue)
        w.editor.put_image(image)
        w.editor.textCursor().insertBlock()
        w.editor.table(2, 2)
        w.editor.insertPlainText("表格内容")
        w.table_operation("row")
        self.assertEqual(w.editor.textCursor().currentTable().rows(), 3)
        w.save_current()
        key = w.current_id
        w.load_diary(key)
        self.assertIn("<table", w.editor.toHtml())
        self.assertIn("diary-image://", w.editor.toHtml())
        self.assertEqual(self.store.conn.execute("SELECT COUNT(*) FROM attachments").fetchone()[0], 1)
        mime = QMimeData()
        mime.setHtml('<p><b>粘贴</b><img src="https://example.invalid/a.jpg"></p>')
        w.editor.moveCursor(QTextCursor.MoveOperation.End)
        w.editor.insertFromMimeData(mime)
        self.assertIn("图片未导入", w.editor.toPlainText())
        for kind in ("TXT", "HTML", "PDF"):
            target = self.root / f"export.{kind.lower()}"
            with patch.object(QFileDialog, "getSaveFileName", return_value=(str(target), "")):
                w.export_current(kind)
            self.assertTrue(target.exists(), self.errors)
            self.assertGreater(target.stat().st_size, 0)
            if kind == "HTML":
                self.assertIn("data:image/png;base64,", target.read_text(encoding="utf-8"))
            if kind == "PDF":
                self.assertTrue(target.read_bytes().startswith(b"%PDF"))
        self.assertEqual(self.errors, [])

    def test_clipboard_image_paste_and_daily_backup(self):
        w = self.window()
        w.new_diary()
        image = QImage(30, 40, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.green)
        mime = QMimeData()
        mime.setImageData(image)
        self.assertTrue(w.editor.canInsertFromMimeData(mime))
        QApplication.clipboard().setMimeData(mime)
        w.editor.paste()
        self.assertIn("diary-image://", w.editor.toHtml())
        w.settings["auto_backup"] = True
        w.daily_backup()
        backups = list((self.store.root / "backups").glob("自动备份-*.zip"))
        self.assertEqual(len(backups), 1)
        original = backups[0].read_bytes()
        w.editor.insertPlainText("新增内容")
        w.daily_backup()
        self.assertEqual(backups[0].read_bytes(), original)
        self.assertTrue(w.save_current())
        self.assertEqual(self.errors, [])

    def test_filter_restore_and_theme(self):
        w = self.window()
        w.new_diary(title="旅行日记")
        key = w.current_id
        w.tags_edit.setText("旅行")
        w.favorite.setChecked(True)
        w.save_current()
        w.change_mode("favorite")
        self.assertEqual(w.diary_list.count(), 1)
        w.filter_day(QDate(2000, 1, 1))
        self.assertEqual(w.diary_list.count(), 0)
        self.assertIsNone(w.current_id)
        w.clear_filters()
        self.assertEqual(w.current_id, key)
        self.store.delete(key)
        w.change_mode("trash")
        self.assertTrue(w.editor.isReadOnly())
        w.restore_current()
        self.assertFalse(w.editor.isReadOnly())
        w.apply_theme(True)
        w.focus_mode(True)
        w.focus_mode(False)
        self.assertEqual(self.errors, [])


if __name__ == "__main__":
    unittest.main()
