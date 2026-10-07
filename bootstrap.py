"""只依赖 Python 标准库的源码启动器；首次运行创建项目内虚拟环境。"""
import hashlib
import os
import subprocess
import sys
import venv
from pathlib import Path


def main():
    if sys.version_info < (3, 10):
        print("Python 3.10 or later is required. Conda is optional.")
        return 1
    root = Path(__file__).resolve().parent
    folder = root / ".venv"
    python = folder / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    requirements = root / "requirements.txt"
    stamp = folder / ".diary-requirements.sha256"
    digest = hashlib.sha256(requirements.read_bytes()).hexdigest()
    if not python.exists():
        print("Creating project virtual environment...", flush=True)
        venv.EnvBuilder(with_pip=True).create(folder)
    probe = subprocess.run([str(python), "-c", "import sys; assert sys.version_info >= (3,10); from PyQt6.QtCore import PYQT_VERSION_STR; assert (6,6) <= tuple(map(int,PYQT_VERSION_STR.split('.')[:2])) < (7,0)"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if probe.returncode or not stamp.exists() or stamp.read_text().strip() != digest:
        print("Installing diary dependencies (internet required on first run)...", flush=True)
        result = subprocess.run([str(python), "-m", "pip", "install", "-r", str(requirements)])
        if result.returncode:
            print("Installation failed. Check your connection and retry start.bat.")
            return result.returncode
        stamp.write_text(digest, encoding="ascii")
    args = [str(root / "main.py"), *sys.argv[1:]]
    pythonw = folder / "Scripts/pythonw.exe"
    if os.name == "nt" and pythonw.exists() and not any(a in ("--help", "-h", "--check-runtime") for a in sys.argv[1:]):
        subprocess.Popen([str(pythonw), *args], cwd=root)
        return 0
    return subprocess.call([str(python), *args], cwd=root)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"Startup failed: {exc}", file=sys.stderr)
        sys.exit(1)
