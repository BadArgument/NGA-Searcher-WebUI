"""索引 API 路由 — 后台索引任务。"""
from __future__ import annotations

import threading

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from ..indexer import Indexer
from ..store import Store

router = APIRouter(prefix="/api", tags=["indexing"])


def _run_in_thread(fn):
    """在线程池中执行同步任务，避免阻塞事件循环。"""
    t = threading.Thread(target=fn, daemon=True)
    t.start()
    return t


@router.post("/index/board/{fid}")
async def api_index_board(fid: int):
    store = Store()
    indexer = Indexer(store)
    try:
        # 后台执行，避免阻塞请求
        result = {}
        def _run():
            nonlocal result
            result = indexer.index_board(fid)
        t = _run_in_thread(_run)
        t.join(timeout=600)  # 最多等 10 分钟
        if t.is_alive():
            return JSONResponse({"ok": True, "status": "running"})
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
        result = {}
        def _run():
            nonlocal result
            result = indexer.update_all()
        t = _run_in_thread(_run)
        t.join(timeout=600)
        if t.is_alive():
            return JSONResponse({"ok": True, "status": "running"})
        return JSONResponse(result)
    except Exception:
        raise HTTPException(500, "增量更新失败，请稍后重试")
    finally:
        store.close()