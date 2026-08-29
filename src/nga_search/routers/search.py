"""搜索 API 路由。"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..crawler import Crawler
from ..models import SearchParams
from ..query import Query
from ..schemas import SearchRequest
from ..search_task import SearchTaskManager
from ..store import Store

router = APIRouter(prefix="/api", tags=["search"])


@router.post("/search")
async def api_search(request: Request, body: SearchRequest):
    store = Store()
    crawler = Crawler()
    query = Query(store, crawler)
    try:
        params = SearchParams(
            q=body.q,
            source=body.source.value,
            fid=body.fid,
            author=body.author,
            date_from=body.date_from,
            date_to=body.date_to,
            exclude=body.exclude,
            match=body.match,
            groups=[g.model_dump() for g in body.groups],
            sort=body.sort.value,
            limit=body.limit,
            offset=body.offset,
        )
        results = await query.search(params)

        # 查询任务状态
        total = len(results)
        has_more = False
        if body.source.value == "online":
            tm = SearchTaskManager.get()
            groups = [g.model_dump() for g in body.groups]
            task = tm.get_task(groups)
            if task:
                total = task.total_collected()
                # has_more: 任务还在跑 或 还有更多已收集结果可翻页
                has_more = not task.is_done() or (body.offset + body.limit) < total
        else:
            # 离线搜索：结果数 >= limit 时认为还有更多
            has_more = len(results) >= body.limit

        return JSONResponse({
            "results": [{
                "tid": r.tid, "pid": r.pid, "fid": r.fid, "fname": r.fname,
                "authorid": r.authorid, "author": r.author,
                "subject": r.subject, "snippet": r.snippet,
                "post_time": r.post_time, "reply_count": r.reply_count,
                "floor": r.floor, "is_topic": r.is_topic,
                "url": r.url,
            } for r in results],
            "total": total,
            "has_more": has_more,
        })
    finally:
        store.close()