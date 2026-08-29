"""SQLite 存储层：建表、读写、搜索。"""
from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path

from . import app_dir
from .models import Board, Favorite, Post, STATE_META


DB_PATH = app_dir() / "search.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS boards (
    fid          INTEGER PRIMARY KEY,
    name         TEXT    NOT NULL,
    parent_fid   INTEGER DEFAULT 0,
    parent_name  TEXT    DEFAULT ''
);

CREATE TABLE IF NOT EXISTS posts (
    pid         INTEGER PRIMARY KEY,
    tid         INTEGER NOT NULL,
    fid         INTEGER NOT NULL,
    authorid    INTEGER NOT NULL,
    author      TEXT    NOT NULL,
    subject     TEXT    DEFAULT '',
    content     TEXT    DEFAULT '',
    post_time   INTEGER NOT NULL,
    floor       INTEGER DEFAULT 0,
    is_topic    INTEGER DEFAULT 0,
    reply_count INTEGER DEFAULT 0,
    fetch_state INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS favorites (
    tid        INTEGER PRIMARY KEY,
    fid        INTEGER NOT NULL,
    subject    TEXT    NOT NULL,
    author     TEXT    NOT NULL,
    added_time INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    uid      INTEGER PRIMARY KEY,
    username TEXT NOT NULL,
    last_seen INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_posts_tid ON posts(tid);
CREATE INDEX IF NOT EXISTS idx_posts_fid ON posts(fid);
CREATE INDEX IF NOT EXISTS idx_posts_author ON posts(author);
CREATE INDEX IF NOT EXISTS idx_posts_post_time ON posts(post_time);
CREATE INDEX IF NOT EXISTS idx_posts_fid_topic ON posts(fid, is_topic);
CREATE INDEX IF NOT EXISTS idx_posts_topic_time ON posts(is_topic, post_time);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

CREATE TABLE IF NOT EXISTS thread_access (
    tid         INTEGER PRIMARY KEY,
    last_access INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_thread_access_time ON thread_access(last_access);
"""


def _snippet(content: str, n: int = 200) -> str:
    """提取纯文本摘要。"""
    text = re.sub(r"<[^>]+>", " ", content or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:n]


class Store:
    def __init__(self, path: Path | str = DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.executescript(SCHEMA)
        # 迁移：为旧库添加 description 列
        try:
            self.conn.execute("ALTER TABLE boards ADD COLUMN description TEXT DEFAULT ''")
        except Exception:
            pass

    # ---------- 版面 ----------
    def upsert_boards(self, boards: list[Board]):
        self.conn.executemany(
            "INSERT INTO boards(fid,name,parent_fid,parent_name,description)"
            " VALUES(?,?,?,?,?)"
            " ON CONFLICT(fid) DO UPDATE SET name=excluded.name,"
            " parent_fid=excluded.parent_fid, parent_name=excluded.parent_name,"
            " description=excluded.description",
            [(b.fid, b.name, b.parent_fid, b.parent_name, b.description) for b in boards],
        )
        self.conn.commit()

    def get_boards(self) -> list[Board]:
        rows = self.conn.execute("SELECT * FROM boards ORDER BY fid").fetchall()
        return [Board(**dict(r)) for r in rows]

    def get_board(self, fid: int) -> Board | None:
        row = self.conn.execute("SELECT * FROM boards WHERE fid=?", (fid,)).fetchone()
        return Board(**dict(row)) if row else None

    def search_boards(self, q: str) -> list[Board]:
        rows = self.conn.execute(
            "SELECT * FROM boards WHERE name LIKE ? ORDER BY fid",
            (f"%{q}%",)).fetchall()
        return [Board(**dict(r)) for r in rows]

    # ---------- 帖子写入 ----------
    def upsert_thread_posts(self, threads: list[dict], commit: bool = True):
        """写入主题帖（is_topic=1）。"""
        if threads:
            self.conn.executemany(
                "INSERT INTO posts(pid,tid,fid,authorid,author,subject,content,"
                " post_time,floor,is_topic,reply_count,fetch_state)"
                " VALUES(?,?,?,?,?,?,?,?,?,1,?,?)"
                " ON CONFLICT(pid) DO UPDATE SET"
                " subject=excluded.subject, reply_count=excluded.reply_count,"
                " fetch_state=excluded.fetch_state",
                [(t["pid"], t["tid"], t["fid"], t.get("authorid", 0),
                  t.get("author", ""), t.get("subject", ""), t.get("content", ""),
                  t.get("post_time", 0), 0, t.get("reply_count", 0),
                  t.get("fetch_state", 0)) for t in threads],
            )
        if threads:
            users = list({(t.get("authorid", 0), t.get("author", ""))
                          for t in threads if t.get("author")})
            self.upsert_users(users, commit=False)
        if commit:
            self.conn.commit()

    def upsert_posts(self, posts: list[Post], commit: bool = True):
        """写入回复帖。

        主题行（is_topic=1，NGA 原始楼主 pid 为 0）统一以 pid=tid 存储，
        与版面爬取写入的主题行主键一致，避免产生 pid=0 的重复主题行脏数据。
        """
        if posts:
            self.conn.executemany(
                "INSERT INTO posts(pid,tid,fid,authorid,author,subject,content,"
                " post_time,floor,is_topic)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(pid) DO UPDATE SET content=excluded.content,"
                " floor=excluded.floor, subject=excluded.subject,"
                " post_time=excluded.post_time",
                [(p.tid if getattr(p, "is_topic", 0) else p.pid,
                  p.tid, p.fid, p.authorid, p.author, p.subject,
                  p.content, p.post_time, p.floor, p.is_topic) for p in posts],
            )
        if posts:
            users = list({(p.authorid, p.author) for p in posts})
            self.upsert_users(users, commit=False)
        if commit:
            self.conn.commit()

    def set_thread_fetch_state(self, tid: int, state: int, commit: bool = True):
        self.conn.execute(
            "UPDATE posts SET fetch_state=? WHERE tid=? AND is_topic=1", (state, tid))
        if commit:
            self.conn.commit()

    def get_thread_fetch_state(self, tid: int) -> int:
        row = self.conn.execute(
            "SELECT fetch_state FROM posts WHERE tid=? AND is_topic=1", (tid,)).fetchone()
        return row["fetch_state"] if row else STATE_META

    # ---------- 查询 ----------
    def get_thread(self, tid: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM posts WHERE tid=? AND is_topic=1", (tid,)).fetchone()
        return dict(row) if row else None

    def get_posts(self, tid: int) -> list[Post]:
        rows = self.conn.execute(
            "SELECT * FROM posts WHERE tid=? ORDER BY floor", (tid,)).fetchall()
        return [Post(**dict(r)) for r in rows]

    def get_threads_by_fid(self, fid: int, limit: int = 50) -> list[dict]:
        """从本地缓存按版面获取主题帖（is_topic=1），用于兜底搜索/爬虫失败时展示。"""
        rows = self.conn.execute(
            "SELECT * FROM posts WHERE fid=? AND is_topic=1 ORDER BY post_time DESC LIMIT ?",
            (fid, limit)).fetchall()
        return [dict(r) for r in rows]

    def get_posts_page(self, tid: int, page: int, per_page: int = 25) -> list[Post]:
        offset = (page - 1) * per_page
        rows = self.conn.execute(
            "SELECT * FROM posts WHERE tid=? ORDER BY floor LIMIT ? OFFSET ?",
            (tid, per_page, offset)).fetchall()
        return [Post(**dict(r)) for r in rows]

    def has_posts_page(self, tid: int, page: int, per_page: int = 25) -> bool:
        offset = (page - 1) * per_page
        row = self.conn.execute(
            "SELECT 1 FROM posts WHERE tid=? ORDER BY floor LIMIT 1 OFFSET ?",
            (tid, offset)).fetchone()
        return row is not None

    def count_posts(self, tid: int) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) n FROM posts WHERE tid=?", (tid,)).fetchone()
        return row["n"] if row else 0

    def threads_exist(self, tids: list[int]) -> set[int]:
        if not tids:
            return set()
        placeholders = ",".join("?" * len(tids))
        rows = self.conn.execute(
            f"SELECT tid FROM posts WHERE tid IN ({placeholders}) AND is_topic=1",
            tids).fetchall()
        return {r["tid"] for r in rows}

    # ---------- 分组搜索（纯 SQL LIKE） ----------
    def grouped_search(
        self,
        groups: list[dict],
        sort: str = "time",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """分组搜索：组内 AND（关键词间 AND），组间 OR。

        groups: [{"match": "关键词", "search_mode": "thread", "fid": 123,
                  "author": "xxx", "date_from": "2024-01-01",
                  "date_to": "2024-12-31", "exclude": "排除词"}, ...]
        """
        if not groups:
            return []

        order = "p.post_time DESC" if sort != "rank" else "p.post_time DESC"
        group_clauses: list[str] = []
        all_params: list = []

        for g in groups:
            if not isinstance(g, dict):
                continue
            match_kw = g.get("match", "").strip()
            if not match_kw:
                continue

            conditions: list[str] = []

            # 搜索模式：主题模式仅匹配 is_topic=1
            search_mode = g.get("search_mode", "thread")
            if search_mode == "thread":
                conditions.append("p.is_topic = 1")
            elif search_mode == "post":
                conditions.append("p.is_topic = 0")

            # 关键词匹配：多词 AND，每个词在 subject 或 content 中出现
            for word in match_kw.split():
                like = f"%{word}%"
                conditions.append(
                    "(p.subject LIKE ? OR p.content LIKE ?)")
                all_params.append(like)
                all_params.append(like)

            # 版面筛选
            fid = g.get("fid")
            if fid is not None:
                conditions.append("p.fid = ?")
                all_params.append(int(fid))

            # 作者筛选
            author = g.get("author")
            if author:
                conditions.append("p.author = ?")
                all_params.append(author)

            # 日期筛选
            date_from = g.get("date_from")
            if date_from:
                conditions.append("p.post_time >= ?")
                all_params.append(_parse_date_ts(date_from))
            date_to = g.get("date_to")
            if date_to:
                conditions.append("p.post_time <= ?")
                all_params.append(_parse_date_ts(date_to, is_end=True))

            # 排除关键词
            exclude = g.get("exclude")
            if exclude:
                for w in exclude.split():
                    like = f"%{w}%"
                    conditions.append(
                        "(p.subject NOT LIKE ? AND p.content NOT LIKE ?)")
                    all_params.append(like)
                    all_params.append(like)

            if conditions:
                group_clauses.append("(" + " AND ".join(conditions) + ")")

        if not group_clauses:
            return []

        where = " OR ".join(group_clauses)

        search_sql = (
            f"SELECT p.*, COALESCE(b.name, '') AS fname "
            f"FROM posts p LEFT JOIN boards b ON p.fid = b.fid "
            f"WHERE ({where})"
            f" ORDER BY {order} LIMIT ? OFFSET ?"
        )

        rows = self.conn.execute(
            search_sql, all_params + [limit, offset]).fetchall()

        results = []
        for r in rows:
            results.append({
                "tid": r["tid"],
                "pid": r["pid"],
                "fid": r["fid"],
                "fname": r["fname"] or "",
                "authorid": r["authorid"],
                "author": r["author"],
                "subject": r["subject"] or "",
                "snippet": _snippet(r["content"]),
                "post_time": r["post_time"],
                "reply_count": r["reply_count"],
                "floor": r["floor"],
                "is_topic": r["is_topic"],
                "url": f"https://bbs.nga.cn/read.php?tid={r['tid']}",
            })
        return results

    # ---------- 数量统计 ----------
    def counts(self) -> dict:
        def c(table: str) -> int:
            return self.conn.execute(
                f"SELECT COUNT(*) n FROM {table}").fetchone()["n"]
        return {
            "boards": c("boards"),
            "threads": self.conn.execute(
                "SELECT COUNT(*) n FROM posts WHERE is_topic=1").fetchone()["n"],
            "posts": c("posts"),
            "favorites": c("favorites"),
        }

    # ---------- 收藏 ----------
    def add_favorite(self, f: Favorite):
        self.conn.execute(
            "INSERT OR REPLACE INTO favorites"
            " (tid,fid,subject,author,added_time)"
            " VALUES(?,?,?,?,?)",
            (f.tid, f.fid, f.subject, f.author, f.added_time))
        self.conn.commit()

    def remove_favorite(self, tid: int):
        self.conn.execute("DELETE FROM favorites WHERE tid=?", (tid,))
        self.conn.commit()

    def list_favorites(self) -> list[Favorite]:
        rows = self.conn.execute(
            "SELECT * FROM favorites ORDER BY added_time DESC").fetchall()
        return [Favorite(**dict(r)) for r in rows]

    def is_favorite(self, tid: int) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM favorites WHERE tid=?", (tid,)).fetchone() is not None

    # ---------- 用户 ----------
    def upsert_users(self, users: list[tuple[int, str]], commit: bool = True):
        now = int(time.time())
        self.conn.executemany(
            "INSERT OR REPLACE INTO users(uid,username,last_seen)"
            " VALUES(?,?,?)",
            [(uid, name, now) for uid, name in users],
        )
        if commit:
            self.conn.commit()

    def search_users(self, q: str, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT uid, username, last_seen FROM users"
            " WHERE username LIKE ? ORDER BY last_seen DESC LIMIT ?",
            (f"%{q}%", limit),
        ).fetchall()
        return [{"uid": r["uid"], "username": r["username"]} for r in rows]

    def sync_users_from_posts(self):
        self.conn.execute(
            "INSERT OR IGNORE INTO users(uid,username,last_seen)"
            " SELECT DISTINCT authorid, author, MAX(post_time)"
            " FROM posts GROUP BY authorid"
        )
        self.conn.commit()

    # ---------- GC ----------
    def touch_thread(self, tid: int):
        """记录帖子最近访问时间。"""
        self.conn.execute(
            "INSERT OR REPLACE INTO thread_access(tid, last_access)"
            " VALUES(?, ?)",
            (tid, int(time.time())),
        )
        self.conn.commit()

    def gc_cleanup(self, max_age_days: int = 7) -> int:
        """清理超过 max_age_days 天未访问的帖子数据。纯 SQL 实现。"""
        cutoff = int(time.time()) - max_age_days * 86400
        cur = self.conn.execute(
            "DELETE FROM posts WHERE tid IN"
            " (SELECT tid FROM thread_access WHERE last_access < ?)",
            (cutoff,),
        )
        total = cur.rowcount
        self.conn.execute(
            "DELETE FROM thread_access WHERE last_access < ?", (cutoff,),
        )
        self.conn.commit()
        return total

    def close(self):
        self.conn.commit()
        self.conn.close()


def _parse_date_ts(s: str, is_end: bool = False) -> int | None:
    """解析日期字符串为时间戳。"""
    import datetime
    try:
        if "T" in s:
            dt = datetime.datetime.fromisoformat(s)
        else:
            dt = datetime.datetime.strptime(s, "%Y-%m-%d")
        if is_end:
            dt = dt.replace(hour=23, minute=59, second=59)
        return int(dt.timestamp())
    except (ValueError, TypeError):
        return None