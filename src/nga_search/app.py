"""FastAPI 应用工厂 — 组装路由、静态文件、中间件。"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import data_dir
from .routers import (
    pages_router,
    search_router,
    threads_router,
    boards_router,
    favorites_router,
    indexing_router,
    export_router,
    users_router,
    status_router,
)

STATIC_DIR = data_dir() / "web" / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="NGA 版面搜索器", version="0.1.0")

    # 静态文件
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # 注册路由
    app.include_router(pages_router)
    app.include_router(search_router)
    app.include_router(threads_router)
    app.include_router(boards_router)
    app.include_router(favorites_router)
    app.include_router(indexing_router)
    app.include_router(export_router)
    app.include_router(users_router)
    app.include_router(status_router)

    return app