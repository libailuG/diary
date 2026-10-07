"""SQLite 日记仓储、附件和可校验的完整备份。"""
import base64
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from contextlib import closing
from datetime import datetime
from pathlib import Path


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.attachments = self.root / "attachments"
        self.attachments.mkdir(exist_ok=True)
        self.settings_path = self.root / "settings.json"
        self.db = self.root / "diary.db"
        self.connect()

    def connect(self):
        self.conn = sqlite3.connect(self.db)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA journal_mode=WAL")
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if version > 1:
            self.conn.close()
            raise ValueError("数据库来自更新版本的软件，请使用对应版本打开。")
        self.conn.executescript('''
            CREATE TABLE IF NOT EXISTS diaries (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, entry_date TEXT NOT NULL,
                content_html TEXT NOT NULL DEFAULT '', content_text TEXT NOT NULL DEFAULT '',
                favorite INTEGER NOT NULL DEFAULT 0, mood TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_diary_date ON diaries(entry_date);
            CREATE TABLE IF NOT EXISTS tags (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
            CREATE TABLE IF NOT EXISTS diary_tags (
                diary_id TEXT REFERENCES diaries(id) ON DELETE CASCADE,
                tag_id INTEGER REFERENCES tags(id) ON DELETE CASCADE,
                PRIMARY KEY(diary_id, tag_id)
            );
            CREATE TABLE IF NOT EXISTS attachments (
                id TEXT PRIMARY KEY, diary_id TEXT REFERENCES diaries(id) ON DELETE CASCADE,
                relative_path TEXT NOT NULL, original_name TEXT NOT NULL,
                mime_type TEXT NOT NULL, created_at TEXT NOT NULL
            );
            PRAGMA user_version=1;
        ''')
        self.conn.commit()

    def close(self):
        self.conn.close()

    def create(self, date, title="未命名日记", html="", text=""):
        key = uuid.uuid4().hex
        stamp = now()
        with self.conn:
            self.conn.execute("INSERT INTO diaries(id,title,entry_date,content_html,content_text,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                              (key, title, date, html, text, stamp, stamp))
        return key

    def get(self, key):
        row = self.conn.execute("SELECT * FROM diaries WHERE id=?", (key,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["tags"] = [r[0] for r in self.conn.execute(
            "SELECT t.name FROM tags t JOIN diary_tags dt ON t.id=dt.tag_id WHERE dt.diary_id=? ORDER BY t.name", (key,))]
        return result

    def save(self, key, title, date, html, text, tags, favorite=False, mood=""):
        with self.conn:
            cursor = self.conn.execute("UPDATE diaries SET title=?,entry_date=?,content_html=?,content_text=?,favorite=?,mood=?,updated_at=? WHERE id=? AND deleted_at IS NULL",
                                      (title.strip() or "未命名日记", date, html, text, int(favorite), mood, now(), key))
            if cursor.rowcount != 1:
                raise ValueError("日记不存在或已删除，未覆盖当前内容。")
            self.conn.execute("DELETE FROM diary_tags WHERE diary_id=?", (key,))
            for tag in sorted(set(t.strip() for t in tags if t.strip())):
                self.conn.execute("INSERT OR IGNORE INTO tags(name) VALUES(?)", (tag,))
                self.conn.execute("INSERT INTO diary_tags SELECT ?,id FROM tags WHERE name=?", (key, tag))

    def list(self, query="", mode="all", date=None, tag=None, start=None, end=None):
        where = ["d.deleted_at IS NOT NULL" if mode == "trash" else "d.deleted_at IS NULL"]
        params = []
        if mode == "favorite":
            where.append("d.favorite=1")
        if query:
            where.append("(instr(lower(d.title),lower(?))>0 OR instr(lower(d.content_text),lower(?))>0)")
            params.extend([query, query])
        if date:
            where.append("d.entry_date=?")
            params.append(date)
        if start:
            where.append("d.entry_date>=?")
            params.append(start)
        if end:
            where.append("d.entry_date<=?")
            params.append(end)
        if tag:
            where.append("EXISTS(SELECT 1 FROM diary_tags dt JOIN tags t ON t.id=dt.tag_id WHERE dt.diary_id=d.id AND t.name=?)")
            params.append(tag)
        sql = "SELECT d.* FROM diaries d WHERE " + " AND ".join(where) + " ORDER BY d.entry_date DESC,d.created_at DESC"
        return [dict(r) for r in self.conn.execute(sql, params)]

    def tags(self):
        return [r[0] for r in self.conn.execute("SELECT DISTINCT t.name FROM tags t JOIN diary_tags dt ON dt.tag_id=t.id JOIN diaries d ON dt.diary_id=d.id WHERE d.deleted_at IS NULL ORDER BY t.name")]

    def dates(self):
        return [r[0] for r in self.conn.execute("SELECT DISTINCT entry_date FROM diaries WHERE deleted_at IS NULL")]

    def delete(self, key):
        with self.conn:
            self.conn.execute("UPDATE diaries SET deleted_at=? WHERE id=?", (now(), key))

    def undelete(self, key):
        with self.conn:
            self.conn.execute("UPDATE diaries SET deleted_at=NULL,updated_at=? WHERE id=?", (now(), key))

    def purge(self):
        keys = [r[0] for r in self.conn.execute("SELECT id FROM diaries WHERE deleted_at IS NOT NULL")]
        with self.conn:
            self.conn.execute("DELETE FROM diaries WHERE deleted_at IS NOT NULL")
        for key in keys:
            folder = self.attachments / key
            if folder.exists():
                shutil.rmtree(folder)

    def add_image(self, diary_id, image, original_name="粘贴图片"):
        if image.isNull():
            raise ValueError("无法读取图片，请选择 PNG、JPG、BMP 或 WebP 图片。")
        if not self.get(diary_id):
            raise ValueError("请先创建日记。")
        key = uuid.uuid4().hex
        folder = self.attachments / diary_id
        folder.mkdir(exist_ok=True)
        path = folder / f"{key}.png"
        if not image.save(str(path), "PNG"):
            raise OSError("图片保存失败。")
        try:
            with self.conn:
                self.conn.execute("INSERT INTO attachments VALUES(?,?,?,?,?,?)",
                                  (key, diary_id, path.relative_to(self.root).as_posix(), original_name, "image/png", now()))
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return f"diary-image://{key}"

    def image_path(self, url):
        key = str(url).removeprefix("diary-image://").rstrip("/")
        row = self.conn.execute("SELECT relative_path FROM attachments WHERE id=?", (key,)).fetchone()
        if row:
            path = (self.root / row[0]).resolve()
            if path.is_relative_to(self.attachments.resolve()):
                return path
        return None

    def portable_html(self, html):
        def replace(match):
            path = self.image_path(match[0])
            if not path or not path.is_file():
                raise ValueError("有图片附件缺失，请恢复完整备份后再导出。")
            return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
        return re.sub(r"diary-image://[a-f0-9]{32}/?", replace, html)

    def read_settings(self):
        try:
            value = json.loads(self.settings_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def write_settings(self, settings):
        temp = self.settings_path.with_suffix(".tmp")
        temp.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self.settings_path)

    def backup(self, destination):
        destination = Path(destination).resolve()
        if destination == self.db or destination.is_relative_to(self.attachments.resolve()):
            raise ValueError("备份文件不能覆盖数据库或保存在附件目录内。")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="diary-backup-") as directory:
            temp = Path(directory)
            database = temp / "diary.db"
            with closing(sqlite3.connect(database)) as target:
                self.conn.backup(target)
            files = [(database, "diary.db")]
            for row in self.conn.execute("SELECT relative_path FROM attachments"):
                path = (self.root / row[0]).resolve()
                if not path.is_relative_to(self.attachments.resolve()) or not path.is_file():
                    raise ValueError(f"附件缺失，备份已中止：{row[0]}")
                files.append((path, row[0]))
            manifest = {"format": 1, "created_at": now(), "files": {name: hashlib.sha256(path.read_bytes()).hexdigest() for path, name in files}}
            archive = temp / "backup.zip"
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
                for path, name in files:
                    z.write(path, name)
                z.writestr("manifest.json", json.dumps(manifest))
            # Write alongside destination, then replace atomically.
            staged = destination.with_name(destination.name + ".tmp-" + uuid.uuid4().hex)
            try:
                shutil.copyfile(archive, staged)
                os.replace(staged, destination)
            finally:
                staged.unlink(missing_ok=True)

    def restore(self, source):
        """Validate completely, create a safety backup, stage replacement and roll back on failure."""
        with tempfile.TemporaryDirectory(prefix="restore-", dir=self.root) as directory:
            temp = Path(directory)
            with zipfile.ZipFile(source) as archive:
                names = archive.namelist()
                if len(set(names)) != len(names):
                    raise ValueError("备份包含重复条目。")
                if sum(i.file_size for i in archive.infolist()) > 2 * 1024**3:
                    raise ValueError("备份超过 2 GB，请先检查来源。")
                manifest = json.loads(archive.read("manifest.json"))
                if manifest.get("format") != 1 or "diary.db" not in manifest.get("files", {}):
                    raise ValueError("不支持的备份格式。")
                if set(names) != set(manifest["files"]) | {"manifest.json"}:
                    raise ValueError("备份内容与校验清单不一致。")
                for name, digest in manifest["files"].items():
                    path = (temp / name).resolve()
                    if not path.is_relative_to(temp.resolve()) or (name != "diary.db" and not name.startswith("attachments/")):
                        raise ValueError("备份包含非法路径。")
                    raw = archive.read(name)
                    if hashlib.sha256(raw).hexdigest() != digest:
                        raise ValueError(f"备份校验失败：{name}")
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(raw)
            with closing(sqlite3.connect(temp / "diary.db")) as check:
                if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("备份数据库损坏。")
                if check.execute("PRAGMA user_version").fetchone()[0] != 1:
                    raise ValueError("备份数据库版本不受支持。")
                check.execute("SELECT id,title,entry_date,content_html,content_text,favorite,mood,created_at,updated_at,deleted_at FROM diaries LIMIT 1")
                check.execute("SELECT id,name FROM tags LIMIT 1")
                check.execute("SELECT diary_id,tag_id FROM diary_tags LIMIT 1")
                for row in check.execute("SELECT relative_path FROM attachments"):
                    p = (temp / row[0]).resolve()
                    if not p.is_relative_to((temp / "attachments").resolve()) or not p.is_file():
                        raise ValueError("备份缺少附件。")
                if check.execute("PRAGMA foreign_key_check").fetchone():
                    raise ValueError("备份数据库关联记录损坏。")
            safety = self.root / "backups" / f"恢复前-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}.zip"
            self.backup(safety)
            (temp / "attachments").mkdir(exist_ok=True)
            self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self.close()
            old_db = temp / "old.db"
            old_attachments = temp / "old-attachments"
            try:
                os.replace(self.db, old_db)
                os.replace(self.attachments, old_attachments)
                os.replace(temp / "diary.db", self.db)
                os.replace(temp / "attachments", self.attachments)
                self.connect()
            except Exception:
                try:
                    self.conn.close()
                except Exception:
                    pass
                if old_db.exists():
                    self.db.unlink(missing_ok=True)
                    for suffix in ("-wal", "-shm"):
                        Path(str(self.db) + suffix).unlink(missing_ok=True)
                    os.replace(old_db, self.db)
                if old_attachments.exists():
                    if self.attachments.exists():
                        shutil.rmtree(self.attachments)
                    os.replace(old_attachments, self.attachments)
                self.connect()
                raise
        return safety
