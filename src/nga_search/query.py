"""查询引擎：离线 FTS5 + 在线搜索 + 分组筛选。"""
from __future__ import annotations

import json

from .crawler import Crawler
from .models import SearchParams, SearchResult
from .search_task import SearchTaskManager
from .store import Store, _snippet


class Query:
    def __init__(self, store: Store, crawler: Crawler | None = None):
        self.store = store
        self.crawler = crawler or Crawler()

    def search(self, params: SearchParams) -> list[SearchResult]:
        """执行搜索，返回结果列表。"""
        groups = self._parse_groups(params)

        # 在线搜索：后台并行爬取 + 动态更新 DB
        if params.source == "online":
            task_mgr = SearchTaskManager.get()

            # 仅主题模式使用并行任务；帖子模式回退到顺序爬取
            has_post_mode = any(
                g.get("search_mode") == "post" for g in groups if isinstance(g, dict)
            )
            if not has_post_mode:
                if params.offset == 0:
                    # 首次搜索：启动后台任务
                    task = task_mgr.get_or_start(groups)
                    return task.get_results(0, params.limit)

                # 翻页：从已有任务取结果
                task = task_mgr.get_task(groups)
                if task:
                    return task.get_results(params.offset, params.limit)

            # 帖子模式或无任务时的回退
            online_results = self._crawl_groups(groups, params.limit, params.offset)
            if online_results is not None:
                return online_results

        # 本地 SQL 搜索
        results = self.store.grouped_search(
            groups, params.sort,
            params.limit, params.offset,
        )
        return [_to_result(r) for r in results]

    def _parse_groups(self, params: SearchParams) -> list[dict]:
        """从 params.groups 获取原生 list，或从独立参数构建单组。"""
        if params.groups:
            if isinstance(params.groups, list):
                return [g for g in params.groups if isinstance(g, dict)]
            # 兼容旧 JSON 字符串格式
            try:
                groups = json.loads(params.groups)
                if isinstance(groups, list):
                    return [g for g in groups if isinstance(g, dict)]
            except (json.JSONDecodeError, TypeError):
                pass

        # 无 groups 时从独立参数构建
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

    def _crawl_groups(self, groups: list[dict], limit: int = 50,
                      offset: int = 0) -> list[SearchResult] | None:
        """对每组调用 NGA API 搜索，懒抓取多页写入本地 DB。

        直接返回 NGA 搜索结果（不走 LIKE 过滤），写入 DB 供离线查询。
        返回 None 表示退化为离线查询。
        """
        all_results: list[SearchResult] = []
        need = offset + limit  # 需要抓够 offset + limit 条才能正确切片

        for g in groups:
            match_kw = g.get("match", "").strip()
            if not match_kw:
                continue
            fid = g.get("fid")
            stid = g.get("stid")
            search_mode = g.get("search_mode", "thread")

            try:
                if search_mode == "post":
                    self._crawl_posts_pages(g, match_kw, fid, stid, need, all_results)
                else:
                    self._crawl_thread_pages(g, match_kw, fid, stid, need, all_results)
            except Exception:
                continue

        if not all_results:
            return None

        # 处理分页：跳过 offset 条，截取 limit 条
        return all_results[offset:offset + limit]

    def _crawl_thread_pages(self, g: dict, match_kw: str, fid, stid, limit: int,
                            all_results: list[SearchResult]):
        """逐页抓取主题搜索结果，写入 DB 并构建结果。"""
        stored = 0
        for page in range(1, 20):  # 最多 20 页
            if fid or stid:
                data = self.crawler.search(
                    int(fid) if fid else 0, match_kw, page,
                    stid=int(stid) if stid else 0,
                )
            else:
                data = self.crawler.global_search(match_kw, page)

            threads = data.get("threads") if data else None
            if not threads:
                break

            thread_dicts = [{
                "pid": t.tid, "tid": t.tid, "fid": t.fid,
                "authorid": t.authorid, "author": t.author,
                "subject": t.subject, "content": t.subject,
                "post_time": t.post_time, "reply_count": t.reply_count,
                "fetch_state": 1,
            } for t in threads]
            self.store.upsert_thread_posts(thread_dicts)

            for t in threads:
                all_results.append(SearchResult(
                    tid=t.tid, pid=t.tid, fid=t.fid, fname="",
                    authorid=t.authorid, author=t.author,
                    subject=t.subject, snippet=_snippet(t.subject),
                    post_time=t.post_time, reply_count=t.reply_count,
                    floor=0, is_topic=1,
                    url=f"https://bbs.nga.cn/read.php?tid={t.tid}",
                ))
            stored += len(threads)

            if stored >= limit:
                break

    def _crawl_posts_pages(self, g: dict, match_kw: str, fid, stid, limit: int,
                           all_results: list[SearchResult]):
        """逐页抓取回复搜索结果，写入线程元数据，构建结果。"""
        stored = 0
        for page in range(1, 20):
            if fid or stid:
                data = self.crawler.search_posts(
                    int(fid) if fid else 0, match_kw, page,
                    stid=int(stid) if stid else 0,
                )
            else:
                data = self.crawler.global_search_posts(match_kw, page)

            if not data:
                break

            threads = data.get("threads")
            posts = data.get("posts")
            if not posts and not threads:
                break

            if threads:
                self.store.upsert_thread_posts(threads)

            if posts:
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
                stored += len(posts)

            if stored >= limit:
                break


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