# 拾光日记

使用 PyQt6 和 SQLite 的本地富文本日记软件。支持普通 Python、可选 Conda 环境，以及无需安装 Python 的 Windows x64 便携包。

## 启动

### 普通用户：Windows 便携版

获取 `ShiguangDiary-Windows-x64.zip`，**完整解压**到可写目录，然后双击其中的 `ShiguangDiary.exe`。包内自带 Python、PyQt 和 Qt 运行库，无需安装 Conda、Python 或其他依赖，也无需联网。必须保留旁边的 `_internal` 文件夹。

日记保存在 EXE 旁的 `data/`，首次运行时创建。升级时将新版解压到新目录，再迁移完整的 `data/` 或通过备份恢复，不要覆盖已有数据。

### 源码用户：普通 Python（无需 Conda）

先安装 Python 3.10+。Windows 安装时启用 “Add Python to PATH”，然后双击 `start.bat`。启动器自动检测 `py` 或 `python`，在项目内创建 `.venv` 并安装 `requirements.txt`；仅首次安装依赖需要联网。

也可手动执行，Windows：

```powershell
cd <项目目录>
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Linux/macOS 源码启动（需要桌面图形环境）：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python main.py
```

`.venv` 是当前机器的本地环境，不需要上传或复制到其他电脑；换电脑重新执行启动器即可。

### Conda（可选）

已有 Conda 用户仍可使用 `conda activate pyqt` 后执行 `python main.py`，软件不依赖该环境名称或任何固定安装路径。

需要重建环境时：`conda env create -f environment.yml`；已有 `pyqt` 环境无需重复创建。

## 已实现

- 三栏主界面、专注模式、浅色和深色主题，记住窗口大小及上次日记。
- 一天多篇日记，标题、日期、心情、收藏、逗号分隔的标签。
- 富文本编辑：字体、字号、粗体、斜体、下划线、删除线、字色、高亮、正文与标题样式。
- 对齐、段落间距、行距、缩进、项目符号与编号列表。
- 图片插入、粘贴和尺寸调整，表格插入及行列编辑，超链接插入。
- 当前日记查找、替换和全部替换，撤销与重做。
- 停止输入 1 秒后自动保存；切换、关闭前保存；失败时保留编辑内容并阻止关闭。
- 标题与正文搜索、标签和日期范围筛选、日历日期标记、收藏列表。
- 回收站、恢复日记、永久清空回收站。
- 每日总结、感恩日记和旅行模板，UTF-8/GB18030 TXT 导入。
- 当前日记 TXT、内嵌图片的独立 HTML、PDF 导出。
- 完整 ZIP 备份、哈希校验恢复、恢复前安全备份，每日自动备份（可关闭）。
- 日记篇数、字数、记录天数、月度篇数及连续记录天数统计。

菜单入口：文件（导入/导出/模板/备份）、编辑（查找替换/回收站）、格式（段落/列表）、插入（图片/表格）、视图（主题/专注）。

## 快捷键

| 操作 | 快捷键 |
|---|---|
| 新建 / 保存 | Ctrl+N / Ctrl+S |
| 撤销 / 重做 | Ctrl+Z / Ctrl+Y |
| 粗体 / 斜体 / 下划线 | Ctrl+B / Ctrl+I / Ctrl+U |
| 查找替换 | Ctrl+F |
| 粘贴纯文本 | Ctrl+Shift+V |
| 专注模式 | F11 |
| 放大 / 缩小正文 | Ctrl+= / Ctrl+- |

## 数据与备份

源码运行时默认数据保存在项目目录下的 `data/`；便携版保存在 EXE 旁的 `data/`。从其他工作目录启动也不会改变保存位置，数据不会写入 PyInstaller 的临时解压目录或 `_internal`。点击左侧“打开数据目录”查看实际位置。

也可使用独立的数据目录：

```powershell
python main.py --data-dir ./data
```

目录包含 `diary.db`、`attachments/`、`backups/`、`settings.json` 和 `app.log`。不要单独移动数据库，图片也属于日记数据。迁移请使用完整 ZIP 备份。程序通过锁文件阻止两个窗口同时使用同一数据目录。

自动备份在应用启动及运行期间每小时检查，每天首次符合条件时生成一份，保存于 `backups/`；当天后续修改不会覆盖当日首份备份。恢复会替换全部日记和附件（包括回收站），保留当前机器的界面设置，并先生成“恢复前”备份。备份超过 2 GB 时不能通过此版本恢复。自动备份不会自动清理旧文件。

日记与备份未加密，不包含密码锁或云同步。富文本采用 Qt 支持的 HTML 子集，Word 中复杂的分页、页眉页脚及粘贴样式可能被简化。外部网页图片不会自动下载；请使用“插入图片”保存本地图片。任意类型文件附件、批量导出、混合字体选区提示未包含在此版本。

## 结构与验证

`diary/window.py` 管理界面和自动保存；`diary/editor.py` 管理富文本与资源加载；`diary/storage.py` 管理 SQLite、附件和备份。数据库版本为 1，后续修改结构应增加版本迁移。

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
```

测试使用临时目录，不操作真实日记；覆盖富文本自动保存、切换、保存失败防丢失、图片表格、导出、筛选和备份校验恢复。

## 构建 Windows 便携包

在 Windows x64 机器上：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe tools/build_portable.py
```

输出为 `dist/ShiguangDiary-Windows-x64.zip`，附带 SHA256 和运行检查报告。构建脚本不会读取或打包 `data/`；每次构建使用独立目录，避免删除旧版运行数据。构建后会清除子进程中的 Conda/Python/Qt 环境变量及 PATH 路径，在不同工作目录验证独立 EXE 的富文本、图片、PDF、SQLite 和备份恢复。

Windows 包仅适用于 Windows x64；Linux/macOS 可运行源码，独立包需要在对应系统另行构建。

GitHub 的 `Build Windows portable` 工作流在代码推送和手动触发时运行：安装普通 Python、运行测试、打包并上传可下载的 ZIP Artifact。下载入口为仓库 Actions 页；自动构建不接触本地日记数据。

Qt 富文本能力参考：[QTextEdit 官方文档](https://doc.qt.io/qt-6/qtextedit.html)。
打包目录处理参考：[PyInstaller runtime information](https://pyinstaller.org/en/stable/runtime-information.html)。
