import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from PyQt6.QtWidgets import QApplication, QDialog, QLineEdit
from diary.auth import (PASSWORD_KEY, DEFAULT_PASSWORD, PasswordDialog, authenticate,
                        read_settings_file, set_password)
from diary.storage import Store

APP = QApplication.instance() or QApplication([])


class PasswordTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "settings.json"

    def tearDown(self):
        self.temp.cleanup()

    def test_login_masks_input_rejects_wrong_password_and_accepts_unicode(self):
        dialog = PasswordDialog(expected="我的密码 🔐")
        self.assertEqual(dialog.entry.echoMode(), QLineEdit.EchoMode.Password)
        dialog.entry.setText("错误")
        dialog.accept()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Rejected)
        self.assertTrue(dialog.error_label.text())
        self.assertEqual(dialog.entry.text(), "")
        dialog.entry.setText("我的密码 🔐")
        dialog.accept()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)

    def test_setup_requires_matching_nonempty_password(self):
        dialog = PasswordDialog(setup=True)
        dialog.accept()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Rejected)
        dialog.entry.setText("new secret")
        dialog.confirm.setText("different")
        dialog.accept()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Rejected)
        dialog.confirm.setText("new secret")
        dialog.accept()
        self.assertEqual(dialog.password, "new secret")
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)

    def test_first_login_uses_default_password_and_cancel_blocks_login(self):
        with patch.object(PasswordDialog, "exec", return_value=QDialog.DialogCode.Rejected):
            self.assertFalse(authenticate(self.path))
        self.assertEqual(read_settings_file(self.path)[PASSWORD_KEY], DEFAULT_PASSWORD)

    def test_first_login_persists_default_without_setup_and_keeps_other_settings(self):
        self.path.write_text('{"dark": true}', encoding="utf-8")
        with patch("diary.auth.PasswordDialog") as factory:
            factory.return_value.exec.return_value = QDialog.DialogCode.Accepted
            self.assertTrue(authenticate(self.path))
            factory.assert_called_once_with(expected="123456")
        self.assertEqual(read_settings_file(self.path), {"dark": True, PASSWORD_KEY: "123456"})

    def test_manual_password_edit_and_disable_take_effect_on_next_login(self):
        set_password(self.path, "first")
        set_password(self.path, "edited 中文")
        with patch("diary.auth.PasswordDialog") as factory:
            factory.return_value.exec.return_value = QDialog.DialogCode.Rejected
            self.assertFalse(authenticate(self.path))
            factory.assert_called_once_with(expected="edited 中文")
        set_password(self.path, "")
        with patch("diary.auth.PasswordDialog") as factory:
            self.assertTrue(authenticate(self.path))
            factory.assert_not_called()

    def test_malformed_settings_never_skip_password(self):
        for text in ('{broken', '[]', '{"login_password": 123}', '{"login_password": null}'):
            self.path.write_text(text, encoding="utf-8")
            with self.assertRaises(ValueError):
                authenticate(self.path)

    def test_window_settings_save_preserves_password_edited_on_disk(self):
        store = Store(self.path.parent)
        try:
            set_password(self.path, "old")
            stale_settings = store.read_settings()
            self.path.write_text(json.dumps({PASSWORD_KEY: "new", "dark": False}), encoding="utf-8-sig")
            stale_settings["dark"] = True
            store.write_settings(stale_settings)
            self.assertEqual(read_settings_file(self.path)[PASSWORD_KEY], "new")
            self.assertTrue(read_settings_file(self.path)["dark"])
        finally:
            store.close()

    def test_cancelled_login_never_opens_database_or_main_window(self):
        import main
        root = self.path.parent
        with patch.object(main.sys, "argv", ["main.py", "--data-dir", str(root)]), \
             patch.object(main, "QApplication", return_value=MagicMock()), \
             patch.object(main, "authenticate", return_value=False), \
             patch.object(main, "Store") as store, \
             patch.object(main, "MainWindow") as window, \
             patch.object(main.logging, "basicConfig"), patch.object(main.logging, "shutdown"):
            self.assertEqual(main.main(), 0)
            store.assert_not_called()
            window.assert_not_called()
