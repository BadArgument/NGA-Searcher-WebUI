"""版面 API 路由。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from ..crawler import Crawler
from ..store import Store

router = APIRouter(prefix="/api", tags=["boards"])


@router.get("/boards")
async def api_boards(q: str = ""):
    store = Store()
    try:
        if q:
            boards = store.search_boards(q)
        else:
            boards = store.get_boards()
        return JSONResponse([{
            "fid": b.fid, "name": b.name,
            "parent_fid": b.parent_fid, "parent_name": b.parent_name,
        } for b in boards])
    finally:
        store.close()


@router.get("/boards/tree")
async def api_boards_tree(parent_fid: int = 0):
    store = Store()
    try:
        boards = store.get_boards()
        all_parents = {b.parent_fid for b in boards}
        children = []
        for b in boards:
            if b.parent_fid == parent_fid:
                children.append({
                    "fid": b.fid,
                    "name": b.name,
                    "has_children": b.fid in all_parents,
                })
        return JSONResponse(children)
    finally:
        store.close()


@router.post("/boards/fetch")
async def api_boards_fetch():
    crawler = Crawler()
    store = Store()
    try:
        try:
            boards = crawler.get_boards()
            store.upsert_boards(boards)
            return JSONResponse({"ok": True, "count": len(boards)})
        except Exception:
            raise HTTPException(500, "版面列表获取失败，请稍后重试")
    finally:
        store.close()


@router.get("/boards/{fid}")
async def api_board_detail(fid: int, page: int = 1, sort: str = "time", stid: int = 0):
    crawler = Crawler()
    try:
        data = crawler.get_threads(fid, page, stid=stid)
    except Exception:
        raise HTTPException(500, "版面数据获取失败，请稍后重试")
    return JSONResponse({
        "forum": data["forum"],
        "threads": [{
            "tid": t.tid, "fid": t.fid,
            "author": t.author, "authorid": t.authorid,
            "subject": t.subject,
            "post_time": t.post_time, "last_reply_time": t.last_reply_time,
            "reply_count": t.reply_count,
        } for t in data["threads"] if not (stid and t.tid == stid)],
        "page": data["page"],
    })