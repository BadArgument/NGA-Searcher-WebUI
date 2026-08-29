"""收藏 API 路由。"""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from ..models import Favorite
from ..schemas import FavoriteAddRequest
from ..store import Store

router = APIRouter(prefix="/api", tags=["favorites"])


@router.get("/favorites")
async def api_favorites():
    store = Store()
    try:
        favs = store.list_favorites()
        return JSONResponse([{
            "tid": f.tid, "fid": f.fid,
            "subject": f.subject, "author": f.author,
            "added_time": f.added_time,
        } for f in favs])
    finally:
        store.close()


@router.post("/favorites")
async def api_fav_add(request: Request, body: FavoriteAddRequest):
    store = Store()
    try:
        tid = body.tid
        thread = store.get_thread(tid)
        fav = Favorite(
            tid=tid, fid=thread["fid"] if thread else 0,
            subject=thread["subject"] if thread else body.subject,
            author=thread["author"] if thread else body.author,
            added_time=int(time.time()),
        )
        store.add_favorite(fav)
        return JSONResponse({"ok": True})
    finally:
        store.close()


@router.delete("/favorites/{tid}")
async def api_fav_remove(tid: int):
    store = Store()
    try:
        store.remove_favorite(tid)
        return JSONResponse({"ok": True})
    finally:
        store.close()