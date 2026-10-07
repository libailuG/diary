"""源码和独立可执行程序共用的日记软件入口。"""
import argparse
import logging
import sys
from pathlib import Path

from PyQt6.QtCore import QLockFile
from PyQt6.QtWidgets import QApplication, QMessageBox

from diary.storage import Store
from diary.window import MainWindow
from diary.paths import application_dir


def main():
    parser = argparse.ArgumentParser(description="拾光日记 · 本地富文本日记")
    parser.add_argument("--data-dir", type=Path, help="指定数据目录（默认使用项目目录下的 data 文件夹）")
    parser.add_argument("--check-runtime", type=Path, help="在临时目录验证运行环境，将结果写入 JSON，不修改日记数据")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setOrganizationName("LocalDiary")
    app.setApplicationName("ShiguangDiary")
    app.setApplicationDisplayName("拾光日记")
    if args.check_runtime:
        from diary.runtime_check import check_runtime
        return check_runtime(args.check_runtime)
    root = args.data_dir or application_dir() / "data"
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        QMessageBox.critical(None, "数据目录不可写", f"请将软件放在可写的文件夹中，例如文档目录。\n\n数据目录：{root}\n{exc}")
        return 1
    logging.basicConfig(filename=root / "app.log", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
    lock = QLockFile(str(root / "app.lock"))
    if not lock.tryLock(100):
        QMessageBox.warning(None, "无法打开", "这个数据目录已被另一个日记窗口使用。请先关闭已有窗口。")
        logging.shutdown()
        return 1
    store = None
    previous_hook = sys.excepthook
    try:
        store = Store(root)
        window = MainWindow(store)
        def exception_hook(kind, value, traceback):
            logging.error("界面操作异常", exc_info=(kind, value, traceback))
            QMessageBox.critical(window, "操作失败", f"{value}\n\n当前编辑内容仍留在窗口中。错误日志：{root / 'app.log'}")
        sys.excepthook = exception_hook
        window.show()
        return app.exec()
    except Exception as exc:
        logging.exception("启动失败")
        QMessageBox.critical(None, "启动失败", str(exc))
        return 1
    finally:
        sys.excepthook = previous_hook
        if store:
            store.close()
        lock.unlock()
        logging.shutdown()


if __name__ == "__main__":
    sys.exit(main())
