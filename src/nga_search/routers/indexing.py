"""索引 API 路由 — 后台索引任务。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from ..indexer import Indexer
from ..store import Store

router = APIRouter(prefix="/api", tags=["indexing"])


@router.post("/index/board/{fid}")
async def api_index_board(fid: int):
    store = Store()
    indexer = Indexer(store)
    try:
        result = await indexer.index_board(fid)
        return JSONResponse(result)
    except Exception:
        raise HTTPException(500, "索引失败，请稍后重试")
    finally:
        store.close()


@router.post("/index/update")
async def api_index_update():
    store = Store()
    indexer = Indexer(store)
    try:
        result = await indexer.update_all()
        return JSONResponse(result)
    except Exception:
        raise HTTPException(500, "增量更新失败，请稍后重试")
    finally:
        store.close()