# 拾光日记

使用 PyQt6 和 SQLite 的本地富文本日记软件。已适配 Conda 的 `pyqt` 环境。

## 启动

在 Anaconda Prompt 或支持 Conda 的 PowerShell 中执行：

```powershell
conda activate pyqt
cd C:\play\diary
python main.py
```

本机可直接双击 `start.bat`，使用 `%USERPROFILE%\miniconda3\envs\pyqt\pythonw.exe` 启动，不保留控制台窗口。其他 Conda 安装位置则在 Conda 可用的终端运行 `start.bat` 或 `start.ps1`。程序只依赖 PyQt6 和 Python 标准库，无需联网。

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

默认数据保存在项目目录下的 `data/`，本机为 `C:\play\diary\data`。路径以 `main.py` 所在目录为基准，从其他工作目录启动也不会改变保存位置。点击左侧“打开数据目录”查看实际位置。移动整个项目目录即可同时携带日记数据。

也可使用独立的数据目录：

```powershell
python main.py --data-dir C:\play\diary\data
```

目录包含 `diary.db`、`attachments/`、`backups/`、`settings.json` 和 `app.log`。不要单独移动数据库，图片也属于日记数据。迁移请使用完整 ZIP 备份。程序通过锁文件阻止两个窗口同时使用同一数据目录。

自动备份在应用启动及运行期间每小时检查，每天首次符合条件时生成一份，保存于 `backups/`；当天后续修改不会覆盖当日首份备份。恢复会替换全部日记和附件（包括回收站），保留当前机器的界面设置，并先生成“恢复前”备份。备份超过 2 GB 时不能通过此版本恢复。自动备份不会自动清理旧文件。

日记与备份未加密，不包含密码锁或云同步。富文本采用 Qt 支持的 HTML 子集，Word 中复杂的分页、页眉页脚及粘贴样式可能被简化。外部网页图片不会自动下载；请使用“插入图片”保存本地图片。任意类型文件附件、批量导出、混合字体选区提示未包含在此版本。

## 结构与验证

`diary/window.py` 管理界面和自动保存；`diary/editor.py` 管理富文本与资源加载；`diary/storage.py` 管理 SQLite、附件和备份。数据库版本为 1，后续修改结构应增加版本迁移。

```powershell
conda run --no-capture-output -n pyqt python -m unittest discover -v
```

测试使用临时目录，不操作真实日记；覆盖富文本自动保存、切换、保存失败防丢失、图片表格、导出、筛选和备份校验恢复。

Qt 富文本能力参考：[QTextEdit 官方文档](https://doc.qt.io/qt-6/qtextedit.html)。
