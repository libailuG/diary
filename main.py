"""日记软件入口：conda run -n pyqt python main.py。"""
import argparse
import logging
import sys
from pathlib import Path

from PyQt6.QtCore import QLockFile
from PyQt6.QtWidgets import QApplication, QMessageBox

from diary.storage import Store
from diary.window import MainWindow


def main():
    parser = argparse.ArgumentParser(description="拾光日记 · 本地富文本日记")
    parser.add_argument("--data-dir", type=Path, help="指定数据目录（默认使用项目目录下的 data 文件夹）")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setOrganizationName("LocalDiary")
    app.setApplicationName("ShiguangDiary")
    app.setApplicationDisplayName("拾光日记")
    root = args.data_dir or Path(__file__).resolve().parent / "data"
    root.mkdir(parents=True, exist_ok=True)
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
