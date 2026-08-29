"""搜索 API 路由。"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..crawler import Crawler
from ..models import SearchParams
from ..query import Query
from ..schemas import SearchRequest
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
        results = query.search(params)
        return JSONResponse({
            "results": [{
                "tid": r.tid, "pid": r.pid, "fid": r.fid, "fname": r.fname,
                "authorid": r.authorid, "author": r.author,
                "subject": r.subject, "snippet": r.snippet,
                "post_time": r.post_time, "reply_count": r.reply_count,
                "floor": r.floor, "is_topic": r.is_topic,
                "url": r.url,
            } for r in results],
        })
    finally:
        store.close()