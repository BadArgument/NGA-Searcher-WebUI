"""路由模块 — 聚合所有 router。"""
from .pages import router as pages_router
from .search import router as search_router
from .threads import router as threads_router
from .boards import router as boards_router
from .favorites import router as favorites_router
from .indexing import router as indexing_router
from .export import router as export_router
from .users import router as users_router
from .status import router as status_router

__all__ = [
    "pages_router",
    "search_router",
    "threads_router",
    "boards_router",
    "favorites_router",
    "indexing_router",
    "export_router",
    "users_router",
    "status_router",
]