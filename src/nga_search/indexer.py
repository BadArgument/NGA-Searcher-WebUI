"""索引协调：爬取 + 写入 + 增量更新。"""
from __future__ import annotations

import asyncio
import logging

from .crawler import Crawler
from .models import STATE_FIRST, STATE_FULL, STATE_META
from .store import Store

log = logging.getLogger("nga_search")


class Indexer:
    """版面索引 + 增量更新。"""

    def __init__(self, store: Store, crawler: Crawler | None = None):
        self.store = store
        self.crawler = crawler or Crawler()

    # ---------- 版面发现 ----------
    async def discover_boards(self) -> int:
        boards = await self.crawler.get_boards()
        if boards:
            self.store.upsert_boards(boards)
        return len(boards)

    # ---------- 索引版面 ----------
    async def index_board(self, fid: int, progress_cb=None) -> dict:
        total_pages = await self.crawler.get_total_pages(fid)

        total_threads = 0
        for page in range(1, total_pages + 1):
            try:
                data = await self.crawler.get_threads(fid, page)
                threads = data["threads"]
                if threads:
                    thread_dicts = [{
                        "pid": t.tid, "tid": t.tid, "fid": t.fid,
                        "authorid": t.authorid, "author": t.author,
                        "subject": t.subject, "content": t.subject,
                        "post_time": t.post_time, "reply_count": t.reply_count,
                        "fetch_state": STATE_META,
                    } for t in threads]
                    self.store.upsert_thread_posts(thread_dicts)
                    total_threads += len(threads)
                if progress_cb:
                    progress_cb(fid, page, total_pages)
            except Exception as e:
                log.warning("版面 %s 第 %s 页失败: %s", fid, page, e)
                break
            await asyncio.sleep(0.5)

        return {"fid": fid, "pages": total_pages, "threads": total_threads}

    # ---------- 索引帖子 ----------
    async def index_thread(self, tid: int, full: bool = True) -> dict:
        data = await self.crawler.get_posts(tid, 1)
        posts = data["posts"]
        if not posts:
            return {"tid": tid, "posts": 0, "full": False}

        self.store.upsert_posts(posts)
        state = STATE_FIRST

        if full:
            total_pages = await self.crawler.get_post_total_pages(tid)
            for page in range(2, total_pages + 1):
                try:
                    more = await self.crawler.get_posts(tid, page)
                    if more["posts"]:
                        self.store.upsert_posts(more["posts"])
                except Exception as e:
                    log.warning("帖子 %s 第 %s 页失败: %s", tid, page, e)
                await asyncio.sleep(0.3)
            state = STATE_FULL

        self.store.set_thread_fetch_state(tid, state)
        return {"tid": tid, "posts": len(posts), "full": full}

    async def update_all(self, progress_cb=None) -> dict:
        boards = self.store.get_boards()
        if not boards:
            await self.discover_boards()
            boards = self.store.get_boards()

        changed = 0
        total = len(boards)
        for i, b in enumerate(boards):
            try:
                data = await self.crawler.get_threads(b.fid, 1)
                threads = data["threads"]
                if not threads:
                    continue
                new_or_changed = []
                for t in threads:
                    cur = self.store.get_thread(t.tid)
                    if cur and cur.get("last_reply_time", 0) >= t.last_reply_time:
                        continue
                    new_or_changed.append(t)
                if new_or_changed:
                    thread_dicts = [{
                        "pid": t.tid, "tid": t.tid, "fid": t.fid,
                        "authorid": t.authorid, "author": t.author,
                        "subject": t.subject, "content": t.subject,
                        "post_time": t.post_time, "reply_count": t.reply_count,
                        "fetch_state": STATE_META,
                    } for t in new_or_changed]
                    self.store.upsert_thread_posts(thread_dicts)
                    changed += len(new_or_changed)
                if progress_cb:
                    progress_cb(b.fid, i + 1, total)
            except Exception as e:
                log.warning("增量更新版面 %s 失败: %s", b.fid, e)
            await asyncio.sleep(0.3)

        return {"boards_checked": total, "threads_changed": changed}