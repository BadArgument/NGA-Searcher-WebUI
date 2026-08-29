"""Web 服务 — 兼容性包装，实际逻辑已迁移到 app.py 和 routers/。"""
from __future__ import annotations

from .app import create_app

__all__ = ["create_app"]