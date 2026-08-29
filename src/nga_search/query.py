"""查询引擎：离线 FTS5 + 在线搜索 + 分组筛选。"""
from __future__ import annotations

import json

from .crawler import Crawler
from .models import SearchParams, SearchResult
from .store import Store, _snippet


class Query:
    def __init__(self, store: Store, crawler: Crawler | None = None):
        self.store = store
        self.crawler = crawler or Crawler()

    def search(self, params: SearchParams) -> list[SearchResult]:
        """执行搜索，返回结果列表。"""
        groups = self._parse_groups(params)

        # 在线：先爬取 NGA 数据，写入本地
        if params.source == "online":
            online_results = self._crawl_groups(groups)
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

    def _crawl_groups(self, groups: list[dict]) -> list[SearchResult] | None:
        """对每组调用 NGA API 搜索，将结果写入本地 DB。

        主题模式：写入线程元数据，返回 None（走 group_search 查库）。
        回复模式：写入线程元数据，不存回复帖（避免 floor=0），直接返回结果。
        """
        all_results: list[SearchResult] = []
        has_post_mode = False

        for g in groups:
            match_kw = g.get("match", "").strip()
            if not match_kw:
                continue
            fid = g.get("fid")
            stid = g.get("stid")
            search_mode = g.get("search_mode", "thread")

            try:
                if search_mode == "post":
                    has_post_mode = True
                    # 回复模式：thread.php?key=...&content=8
                    if fid or stid:
                        data = self.crawler.search_posts(int(fid) if fid else 0, match_kw, 1, stid=int(stid) if stid else 0)
                    else:
                        data = self.crawler.global_search_posts(match_kw, 1)
                    if data:
                        # 只存线程元数据，不存回复帖（floor=0 无意义）
                        if data.get("threads"):
                            self.store.upsert_thread_posts(data["threads"])
                        # 从 API 响应直接构建结果
                        posts = data.get("posts", [])
                        threads = data.get("threads", [])
                        tid_to_thread = {t["tid"]: t for t in threads}
                        for p in posts:
                            t = tid_to_thread.get(p.tid, {})
                            all_results.append(SearchResult(
                                tid=p.tid, pid=p.pid,
                                fid=t.get("fid", p.fid),
                                fname="",
                                authorid=t.get("authorid", 0),
                                author=t.get("author", ""),
                                subject=t.get("subject", ""),
                                snippet=_snippet(p.content),
                                post_time=p.post_time,
                                reply_count=t.get("reply_count", 0),
                                floor=0,
                                is_topic=1,
                                url=f"https://bbs.nga.cn/read.php?tid={p.tid}",
                            ))
                else:
                    # 主题模式：thread.php?key=...&content=5
                    if fid or stid:
                        data = self.crawler.search(int(fid) if fid else 0, match_kw, 1, stid=int(stid) if stid else 0)
                    else:
                        data = self.crawler.global_search(match_kw, 1)
                    if data and data.get("threads"):
                        thread_dicts = []
                        for t in data["threads"]:
                            thread_dicts.append({
                                "pid": t.tid,
                                "tid": t.tid,
                                "fid": t.fid,
                                "authorid": t.authorid,
                                "author": t.author,
                                "subject": t.subject,
                                "content": t.subject,
                                "post_time": t.post_time,
                                "reply_count": t.reply_count,
                                "fetch_state": 1,
                            })
                        self.store.upsert_thread_posts(thread_dicts)
            except Exception:
                continue

        return all_results if has_post_mode else None


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