"""数据始终位于源码项目或可执行程序旁，不写入打包临时目录。"""
import sys
from pathlib import Path


def application_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent
