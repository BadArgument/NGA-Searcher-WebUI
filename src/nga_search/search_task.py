"""后台搜索任务管理器：跨请求并行爬取，动态更新 DB。"""
from __future__ import annotations

import asyncio
import json
import time

from .crawler import Crawler
from .models import SearchResult
from .store import DB_PATH, Store, _snippet

# 共享 Crawler（所有任务共用，TokenBucket 线程安全）
_SHARED_CRAWLER: Crawler | None = None


def _get_shared_crawler() -> Crawler:
    global _SHARED_CRAWLER
    if _SHARED_CRAWLER is None:
        _SHARED_CRAWLER = Crawler()
    return _SHARED_CRAWLER


def _make_key(groups: list[dict]) -> str:
    """生成搜索任务唯一键。"""
    payload = json.dumps(groups, sort_keys=True, ensure_ascii=False, default=str)
    return payload


class SearchTask:
    """一个搜索任务：异步并行爬取 NGA 多页，写入 DB，收集结果。"""

    def __init__(self, key: str, groups: list[dict]):
        self.key = key
        self.groups = groups
        self.crawler = _get_shared_crawler()
        self._results: list[SearchResult] = []
        self._running = False
        self._done = asyncio.Event()
        self._total_pages = 0
        self._pages_fetched = 0
        self._started_at = time.time()
        self._bg_tasks: list[asyncio.Task] = []

    async def start(self):
        """启动后台爬取。首页同步抓取，剩余页并行。"""
        if self._running:
            return
        self._running = True

        for g in self.groups:
            match_kw = g.get("match", "").strip()
            if not match_kw:
                continue
            fid = g.get("fid")
            stid = g.get("stid")

            # 首页同步抓取
            data1 = await self._fetch_page(g, match_kw, fid, stid, 1)
            if not data1 or not data1.get("threads"):
                continue

            threads1 = data1["threads"]
            self._store_and_collect(threads1)

            total = data1.get("total", 0)
            per_page = len(threads1)
            if total <= per_page:
                self._done.set()
                return

            self._total_pages = min(20, (total + per_page - 1) // per_page)
            if self._total_pages <= 1:
                self._done.set()
                return

            # 并行抓取剩余页
            self._pages_fetched = 1
            for page in range(2, self._total_pages + 1):
                t = asyncio.create_task(
                    self._crawl_page(g, match_kw, fid, stid, page))
                self._bg_tasks.append(t)

            # 只处理第一个匹配组
            break

    async def _fetch_page(self, g: dict, match_kw: str, fid, stid, page: int) -> dict | None:
        try:
            if fid or stid:
                return await self.crawler.search(
                    int(fid) if fid else 0, match_kw, page,
                    stid=int(stid) if stid else 0,
                )
            else:
                return await self.crawler.global_search(match_kw, page)
        except Exception:
            return None

    async def _crawl_page(self, g: dict, match_kw: str, fid, stid, page: int):
        """在后台任务中抓取一页。"""
        try:
            data = await self._fetch_page(g, match_kw, fid, stid, page)
            if data and data.get("threads"):
                self._store_and_collect(data["threads"])
        except Exception:
            pass
        finally:
            self._pages_fetched += 1
            if self._pages_fetched >= self._total_pages:
                self._done.set()

    def _store_and_collect(self, threads: list):
        """写入 DB 并收集结果。"""
        try:
            store = Store(DB_PATH)
            try:
                thread_dicts = [{
                    "pid": t.tid, "tid": t.tid, "fid": t.fid,
                    "authorid": t.authorid, "author": t.author,
                    "subject": t.subject, "content": t.subject,
                    "post_time": t.post_time, "reply_count": t.reply_count,
                    "fetch_state": 1,
                } for t in threads]
                store.upsert_thread_posts(thread_dicts)
            finally:
                store.close()
        except Exception:
            pass

        for t in threads:
            self._results.append(SearchResult(
                tid=t.tid, pid=t.tid, fid=t.fid, fname="",
                authorid=t.authorid, author=t.author,
                subject=t.subject, snippet=_snippet(t.subject),
                post_time=t.post_time, reply_count=t.reply_count,
                floor=0, is_topic=1,
                url=f"https://bbs.nga.cn/read.php?tid={t.tid}",
            ))

    def get_results(self, offset: int, limit: int) -> list[SearchResult]:
        return self._results[offset:offset + limit]

    def total_collected(self) -> int:
        return len(self._results)

    def is_done(self) -> bool:
        return self._done.is_set()

    @property
    def total_pages(self) -> int:
        return self._total_pages

    @property
    def pages_fetched(self) -> int:
        return self._pages_fetched

    @property
    def age(self) -> float:
        return time.time() - self._started_at


class SearchTaskManager:
    """全局搜索任务管理器（单例）。"""

    _instance: SearchTaskManager | None = None

    def __init__(self):
        self._tasks: dict[str, SearchTask] = {}

    @classmethod
    def get(cls) -> SearchTaskManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def get_or_start(self, groups: list[dict]) -> SearchTask:
        key = _make_key(groups)
        self._cleanup()
        if key not in self._tasks:
            task = SearchTask(key, groups)
            self._tasks[key] = task
            await task.start()
        return self._tasks[key]

    def get_task(self, groups: list[dict]) -> SearchTask | None:
        key = _make_key(groups)
        self._cleanup()
        return self._tasks.get(key)

    def _cleanup(self):
        now = time.time()
        expired = [k for k, t in self._tasks.items() if t.age > 300]
        for k in expired:
            del self._tasks[k]