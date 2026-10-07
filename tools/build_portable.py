"""构建不依赖 Python/Conda 的 Windows 便携 ZIP；不读取项目日记目录。"""
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if os.name != "nt" or platform.machine().lower() not in ("amd64", "x86_64"):
        parser.error("Windows x64 包必须使用 Windows x64 的 Python 构建。")
    root = Path(__file__).resolve().parent.parent
    output = (args.output or root / "dist" / "ShiguangDiary-Windows-x64.zip").resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    build_root = root / "build"
    build_root.mkdir(exist_ok=True)
    # Rebuilding never deletes an existing app or its data.
    stage = Path(tempfile.mkdtemp(prefix="portable-", dir=build_root))
    extra_binaries = []
    # A venv created from Conda uses its Python stdlib; include SQLite's DLL explicitly.
    for candidate in (Path(sys.base_prefix) / "Library/bin/sqlite3.dll", Path(sys.base_prefix) / "DLLs/sqlite3.dll"):
        if candidate.is_file():
            extra_binaries = ["--add-binary", f"{candidate}{os.pathsep}."]
            break
    import PyQt6
    qt_bin = Path(PyQt6.__file__).parent / "Qt6/bin"
    build_env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("CONDA", "PYTHON", "QT_", "QML", "_CE_"))}
    build_env["PATH"] = os.pathsep.join(map(str, [qt_bin, Path(sys.executable).parent, Path(sys.base_prefix),
        Path(sys.base_prefix) / "DLLs", Path(sys.base_prefix) / "Library/bin",
        Path(os.environ["SystemRoot"]) / "System32", Path(os.environ["SystemRoot"])]))
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--onedir", "--windowed", "--noupx",
                    "--name", "ShiguangDiary", "--distpath", str(stage / "dist"),
                    "--workpath", str(stage / "work"), "--specpath", str(stage), *extra_binaries, str(root / "main.py")], cwd=root, env=build_env, check=True)
    bundle = stage / "dist" / "ShiguangDiary"
    executable = bundle / "ShiguangDiary.exe"
    clean_env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("CONDA", "PYTHON", "QT_", "QML", "_CE_"))}
    clean_env["PATH"] = os.pathsep.join([str(Path(os.environ["SystemRoot"]) / "System32"), os.environ["SystemRoot"]])
    clean_env["QT_QPA_PLATFORM"] = "windows"
    report = stage / "runtime-check.json"
    with tempfile.TemporaryDirectory(prefix="diary-check-cwd-") as cwd:
        subprocess.run([str(executable), "--check-runtime", str(report)], cwd=cwd, env=clean_env, check=True, timeout=120)
    result = json.loads(report.read_text(encoding="utf-8"))
    if not result.get("ok") or not result.get("frozen") or Path(result["application_dir"]) != bundle:
        raise RuntimeError(f"Portable runtime check failed: {result}")
    if (bundle / "data").exists():
        raise RuntimeError("便携包不应包含 data 目录。")
    shutil.copyfile(root / "README.md", bundle / "README.md")
    (bundle / "使用说明.txt").write_text("拾光日记 · Windows x64 便携版\n\n解压整个文件夹后，双击 ShiguangDiary.exe。\n无需安装 Python、Conda 或 PyQt。\n请保留 _internal 文件夹。\n日记保存在程序旁的 data 文件夹，首次使用自动创建。\n将软件放在有写入权限的目录，不要直接在 ZIP 内运行。\n更新程序前备份 data；新版解压到新文件夹后迁移完整 data 或恢复 ZIP 备份。\n", encoding="utf-8-sig")
    staged_archive = stage / "portable.zip"
    with zipfile.ZipFile(staged_archive, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(bundle.rglob("*")):
            if file.is_file():
                archive.write(file, file.relative_to(bundle.parent).as_posix())
    shutil.copyfile(staged_archive, output)
    checksum = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".zip.sha256").write_text(f"{checksum}  {output.name}\n", encoding="ascii")
    output.with_suffix(".runtime-check.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Portable package: {output}\nSHA256: {checksum}\nRuntime checks: OK", flush=True)


if __name__ == "__main__":
    main()
