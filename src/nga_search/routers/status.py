"""状态 API 路由。"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..store import Store

router = APIRouter(prefix="/api", tags=["status"])


@router.get("/status")
async def api_status():
    store = Store()
    try:
        return JSONResponse(store.counts())
    finally:
        store.close()