"""查询引擎：离线 FTS5 + 在线搜索 + 分组筛选。"""
from __future__ import annotations

import asyncio
import json

from .crawler import Crawler
from .models import SearchParams, SearchResult
from .search_task import SearchTaskManager
from .store import Store, _snippet

PER_PAGE_EST = 20  # NGA 搜索 API 每页结果数


class Query:
    def __init__(self, store: Store, crawler: Crawler | None = None):
        self.store = store
        self.crawler = crawler or Crawler()

    async def search(self, params: SearchParams) -> list[SearchResult]:
        """执行搜索，返回结果列表。"""
        groups = self._parse_groups(params)

        if params.source == "online":
            task_mgr = SearchTaskManager.get()
            task = await task_mgr.get_or_start(groups)
            results = task.get_results(params.offset, params.limit)
            return results

        results = self.store.grouped_search(
            groups, params.sort,
            params.limit, params.offset,
        )
        return [_to_result(r) for r in results]

    def _parse_groups(self, params: SearchParams) -> list[dict]:
        if params.groups:
            if isinstance(params.groups, list):
                return [g for g in params.groups if isinstance(g, dict)]
            try:
                groups = json.loads(params.groups)
                if isinstance(groups, list):
                    return [g for g in groups if isinstance(g, dict)]
            except (json.JSONDecodeError, TypeError):
                pass

        group = {"match": params.q or params.match}
        if params.fid:
            group["fid"] = params.fid
        if params.author:
            group["author"] = params.author
        if params.date_from:
            group["date_from"] = params.date_from
        if params.date_to:
            group["date_to"] = params.date_to
        if params.exclude:
            group["exclude"] = params.exclude
        return [group] if group.get("match") else []

    async def _crawl_groups(self, groups: list[dict], limit: int = 50,
                            offset: int = 0) -> list[SearchResult] | None:
        """任务过期时的回退路径：按需抓取，不拉全量。"""
        all_results: list[SearchResult] = []
        need = offset + limit

        for g in groups:
            match_kw = g.get("match", "").strip()
            if not match_kw:
                continue
            fid = g.get("fid")
            stid = g.get("stid")
            search_mode = g.get("search_mode", "thread")

            try:
                if search_mode == "post":
                    await self._crawl_posts_pages(
                        g, match_kw, fid, stid, need, all_results, offset)
                else:
                    await self._crawl_thread_pages(
                        g, match_kw, fid, stid, need, all_results, offset)
            except Exception:
                continue

        if not all_results:
            return None
        return all_results[offset:offset + limit]

    async def _crawl_thread_pages(self, g: dict, match_kw: str, fid, stid, limit: int,
                                  all_results: list[SearchResult], offset: int = 0):
        """按需抓取主题搜索结果。只抓取包含所需结果的最少页数。"""
        start_page = max(1, (offset // PER_PAGE_EST) + 1)

        data1 = await self._fetch_search_page(g, match_kw, fid, stid, start_page, "thread")
        if not data1 or not data1.get("threads"):
            return

        threads = data1["threads"]
        self._store_threads(threads)
        self._collect_threads(threads, all_results)

        if len(all_results) >= limit:
            return

        # 按需计算剩余页数
        per_page = len(threads)
        remaining = limit - len(all_results)
        pages_needed = (remaining + per_page - 1) // per_page
        total = data1.get("total", 0)
        max_page = min(20, (total + per_page - 1) // per_page) if total > 0 else 20
        last_page = min(start_page + pages_needed, max_page)

        if last_page <= start_page:
            return

        tasks = [
            self._fetch_search_page(g, match_kw, fid, stid, p, "thread")
            for p in range(start_page + 1, last_page + 1)
        ]
        pages = await asyncio.gather(*tasks, return_exceptions=True)

        for data in pages:
            if isinstance(data, Exception) or not data or not data.get("threads"):
                continue
            threads = data["threads"]
            self._store_threads(threads)
            self._collect_threads(threads, all_results)
            if len(all_results) >= limit:
                break

    async def _crawl_posts_pages(self, g: dict, match_kw: str, fid, stid, limit: int,
                                 all_results: list[SearchResult], offset: int = 0):
        """按需抓取回复搜索结果。"""
        start_page = max(1, (offset // PER_PAGE_EST) + 1)

        data1 = await self._fetch_search_page(g, match_kw, fid, stid, start_page, "post")
        if not data1:
            return

        self._store_and_collect_posts(data1, all_results)

        if len(all_results) >= limit:
            return

        per_page = len(data1.get("posts") or data1.get("threads") or [])
        if per_page == 0:
            return
        remaining = limit - len(all_results)
        pages_needed = (remaining + per_page - 1) // per_page
        total = data1.get("total", 0)
        max_page = min(20, (total + per_page - 1) // per_page) if total > 0 else 20
        last_page = min(start_page + pages_needed, max_page)

        if last_page <= start_page:
            return

        tasks = [
            self._fetch_search_page(g, match_kw, fid, stid, p, "post")
            for p in range(start_page + 1, last_page + 1)
        ]
        pages = await asyncio.gather(*tasks, return_exceptions=True)

        for data in pages:
            if isinstance(data, Exception) or not data:
                continue
            self._store_and_collect_posts(data, all_results)
            if len(all_results) >= limit:
                break

    async def _fetch_search_page(self, g: dict, match_kw: str, fid, stid, page: int,
                                  mode: str) -> dict | None:
        try:
            if mode == "thread":
                if fid or stid:
                    return await self.crawler.search(
                        int(fid) if fid else 0, match_kw, page,
                        stid=int(stid) if stid else 0,
                    )
                else:
                    return await self.crawler.global_search(match_kw, page)
            else:
                if fid or stid:
                    return await self.crawler.search_posts(
                        int(fid) if fid else 0, match_kw, page,
                        stid=int(stid) if stid else 0,
                    )
                return await self.crawler.global_search_posts(match_kw, page)
        except Exception:
            return None

    def _store_threads(self, threads: list):
        self.store.upsert_thread_posts([{
            "pid": t.tid, "tid": t.tid, "fid": t.fid,
            "authorid": t.authorid, "author": t.author,
            "subject": t.subject, "content": t.subject,
            "post_time": t.post_time, "reply_count": t.reply_count,
            "fetch_state": 1,
        } for t in threads])

    def _collect_threads(self, threads: list, all_results: list[SearchResult]):
        for t in threads:
            all_results.append(SearchResult(
                tid=t.tid, pid=t.tid, fid=t.fid, fname="",
                authorid=t.authorid, author=t.author,
                subject=t.subject, snippet=_snippet(t.subject),
                post_time=t.post_time, reply_count=t.reply_count,
                floor=0, is_topic=1,
                url=f"https://bbs.nga.cn/read.php?tid={t.tid}",
            ))

    def _store_and_collect_posts(self, data: dict, all_results: list[SearchResult]):
        threads = data.get("threads")
        posts = data.get("posts")
        if threads:
            self.store.upsert_thread_posts(threads)
        if not posts:
            return
        tid_to_thread = {t["tid"]: t for t in (threads or [])}
        for p in posts:
            t = tid_to_thread.get(p.tid, {})
            all_results.append(SearchResult(
                tid=p.tid, pid=p.pid,
                fid=t.get("fid", p.fid), fname="",
                authorid=t.get("authorid", 0),
                author=t.get("author", ""),
                subject=t.get("subject", ""),
                snippet=_snippet(p.content),
                post_time=p.post_time,
                reply_count=t.get("reply_count", 0),
                floor=0, is_topic=1,
                url=f"https://bbs.nga.cn/read.php?tid={p.tid}",
            ))


def _to_result(r: dict) -> SearchResult:
    return SearchResult(
        tid=r.get("tid", 0), pid=r.get("pid", 0),
        fid=r.get("fid", 0),
        fname=r.get("fname", ""), authorid=r.get("authorid", 0),
        author=r.get("author", ""), subject=r.get("subject", ""),
        snippet=r.get("snippet", ""), post_time=r.get("post_time", 0),
        reply_count=r.get("reply_count", 0),
        floor=r.get("floor", 0), is_topic=r.get("is_topic", 0),
        url=r.get("url", f"https://bbs.nga.cn/read.php?tid={r.get('tid', 0)}"),
    )