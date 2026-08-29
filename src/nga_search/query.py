"""查询引擎：离线 FTS5 + 在线搜索 + 分组筛选。"""
from __future__ import annotations

import asyncio
import json

from .crawler import Crawler
from .models import SearchParams, SearchResult
from .search_task import SearchTaskManager
from .store import Store, _snippet


class Query:
    def __init__(self, store: Store, crawler: Crawler | None = None):
        self.store = store
        self.crawler = crawler or Crawler()

    async def search(self, params: SearchParams) -> list[SearchResult]:
        """执行搜索，返回结果列表。"""
        groups = self._parse_groups(params)

        if params.source == "online":
            task_mgr = SearchTaskManager.get()

            has_post_mode = any(
                g.get("search_mode") == "post" for g in groups if isinstance(g, dict)
            )
            if not has_post_mode:
                if params.offset == 0:
                    task = await task_mgr.get_or_start(groups)
                    return task.get_results(0, params.limit)

                task = task_mgr.get_task(groups)
                if task:
                    return task.get_results(params.offset, params.limit)

            online_results = await self._crawl_groups(groups, params.limit, params.offset)
            if online_results is not None:
                return online_results

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
                    await self._crawl_posts_pages(g, match_kw, fid, stid, need, all_results)
                else:
                    await self._crawl_thread_pages(g, match_kw, fid, stid, need, all_results)
            except Exception:
                continue

        if not all_results:
            return None
        return all_results[offset:offset + limit]

    async def _crawl_thread_pages(self, g: dict, match_kw: str, fid, stid, limit: int,
                                  all_results: list[SearchResult]):
        """并发抓取多页主题搜索结果。"""
        # 首页先抓取，获取 total 和 per_page
        data1 = await self._fetch_search_page(g, match_kw, fid, stid, 1, "thread")
        if not data1 or not data1.get("threads"):
            return

        threads1 = data1["threads"]
        self._store_threads(threads1)
        self._collect_threads(threads1, all_results)

        total = data1.get("total", 0)
        per_page = len(threads1)
        if total <= per_page or len(all_results) >= limit:
            return

        total_pages = min(20, (total + per_page - 1) // per_page)
        if total_pages <= 1:
            return

        # 并发抓取剩余页
        tasks = [
            self._fetch_search_page(g, match_kw, fid, stid, p, "thread")
            for p in range(2, total_pages + 1)
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
                                 all_results: list[SearchResult]):
        """并发抓取多页回复搜索结果。"""
        data1 = await self._fetch_search_page(g, match_kw, fid, stid, 1, "post")
        if not data1:
            return

        self._store_and_collect_posts(data1, all_results)
        total = data1.get("total", 0)
        per_page = len(data1.get("posts") or data1.get("threads") or [])
        if total <= per_page or len(all_results) >= limit:
            return

        total_pages = min(20, (total + per_page - 1) // per_page)
        if total_pages <= 1:
            return

        tasks = [
            self._fetch_search_page(g, match_kw, fid, stid, p, "post")
            for p in range(2, total_pages + 1)
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
        """抓取单页搜索结果。"""
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
                    data = await self.crawler.search_posts(
                        int(fid) if fid else 0, match_kw, page,
                        stid=int(stid) if stid else 0,
                    )
                else:
                    data = await self.crawler.global_search_posts(match_kw, page)
                return data
        except Exception:
            return None

    def _store_threads(self, threads: list):
        """将主题搜索结果写入 DB。"""
        thread_dicts = [{
            "pid": t.tid, "tid": t.tid, "fid": t.fid,
            "authorid": t.authorid, "author": t.author,
            "subject": t.subject, "content": t.subject,
            "post_time": t.post_time, "reply_count": t.reply_count,
            "fetch_state": 1,
        } for t in threads]
        self.store.upsert_thread_posts(thread_dicts)

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