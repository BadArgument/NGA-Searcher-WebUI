"""用户搜索 API 路由。"""
from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from ..store import Store

router = APIRouter(prefix="/api", tags=["users"])


@router.get("/users/search")
async def api_users_search(q: str = "", limit: int = 20):
    if not q.strip():
        return JSONResponse([])
    store = Store()
    try:
        return JSONResponse(store.search_users(q, limit))
    finally:
        store.close()