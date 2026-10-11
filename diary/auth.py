"""可由用户在本地 settings.json 中修改的启动密码。"""
import hmac
import json
import os
from pathlib import Path

from PyQt6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox,
                            QFormLayout, QLabel, QLineEdit, QVBoxLayout)

PASSWORD_KEY = "login_password"
DEFAULT_PASSWORD = "123456"


def read_settings_file(path):
    path = Path(path)
    if not path.exists():
        return {}
    try:
        settings = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(settings, dict):
            raise ValueError("设置内容必须是 JSON 对象。")
        if PASSWORD_KEY in settings and not isinstance(settings[PASSWORD_KEY], str):
            raise ValueError("login_password 必须是字符串。")
        return settings
    except (ValueError, UnicodeError) as exc:
        raise ValueError("settings.json 格式不正确，请修复 JSON 格式后再启动；未跳过密码验证。") from exc


def set_password(path, password):
    if not isinstance(password, str):
        raise ValueError("密码必须是字符串。")
    path = Path(path)
    settings = read_settings_file(path)
    settings[PASSWORD_KEY] = password
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


class PasswordDialog(QDialog):
    def __init__(self, parent=None, *, setup=False, allow_disable=False, expected=""):
        super().__init__(parent)
        self.setup = setup
        self.expected = expected
        self.password = None
        self.setWindowTitle("设置登录密码" if setup else "拾光日记 · 登录")
        self.setMinimumWidth(360)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("设置打开日记时使用的密码。" if setup else "请输入登录密码以打开日记。"))
        form = QFormLayout()
        self.entry = QLineEdit()
        self.entry.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("新密码" if setup else "密码", self.entry)
        self.confirm = QLineEdit()
        self.confirm.setEchoMode(QLineEdit.EchoMode.Password)
        if setup:
            form.addRow("确认密码", self.confirm)
        layout.addLayout(form)
        self.disable = QCheckBox("关闭登录密码验证")
        if allow_disable:
            layout.addWidget(self.disable)
            self.disable.toggled.connect(lambda checked: self.entry.setEnabled(not checked))
            self.disable.toggled.connect(lambda checked: self.confirm.setEnabled(not checked))
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("保存" if setup else "登录")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.entry.setFocus()

    def accept(self):
        password = self.entry.text()
        if self.setup:
            if self.disable.isChecked():
                password = ""
            elif not password:
                self.error_label.setText("请输入新密码。")
                return
            elif password != self.confirm.text():
                self.error_label.setText("两次输入的密码不一致。")
                self.confirm.setFocus()
                return
        elif not hmac.compare_digest(password.encode("utf-8"), self.expected.encode("utf-8")):
            self.error_label.setText("密码错误，请重新输入。")
            self.entry.clear()
            self.entry.setFocus()
            return
        self.password = password
        super().accept()


def authenticate(settings_path):
    settings = read_settings_file(settings_path)
    if PASSWORD_KEY not in settings:
        set_password(settings_path, DEFAULT_PASSWORD)
        settings[PASSWORD_KEY] = DEFAULT_PASSWORD
    password = settings[PASSWORD_KEY]
    if password == "":
        return True
    dialog = PasswordDialog(expected=password)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return False
    return True
