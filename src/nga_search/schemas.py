"""Pydantic 请求/响应模型 — API 输入校验与输出序列化。"""
from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field, field_validator


# ============================================================
# 枚举
# ============================================================
class SearchSource(str, Enum):
    OFFLINE = "offline"
    ONLINE = "online"


class SearchMode(str, Enum):
    THREAD = "thread"
    POST = "post"


class SortOrder(str, Enum):
    TIME = "time"
    RANK = "rank"


class ExportFormat(str, Enum):
    HTML = "html"
    UBB = "ubb"


# ============================================================
# 搜索请求
# ============================================================
class SearchGroup(BaseModel):
    """搜索筛选组 — 组内 AND，组间 OR。"""
    match: str = Field(default="", description="关键词（空格分隔为 AND）")
    search_mode: SearchMode = Field(default=SearchMode.THREAD)
    fid: int | None = None
    stid: int | None = None
    author: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    exclude: str = Field(default="", description="排除关键词")


class SearchRequest(BaseModel):
    q: str = Field(default="", description="搜索关键词")
    source: SearchSource = Field(default=SearchSource.OFFLINE)
    fid: int | None = None
    author: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    exclude: str = Field(default="")
    match: str = Field(default="")
    groups: list[SearchGroup] = Field(default_factory=list)
    sort: SortOrder = Field(default=SortOrder.TIME)
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)

    @field_validator("limit")
    @classmethod
    def clamp_limit(cls, v: int) -> int:
        return min(max(v, 1), 200)


# ============================================================
# 帖子相关
# ============================================================
class PostResponse(BaseModel):
    pid: int
    floor: int
    author: str
    authorid: int
    subject: str
    content: str = ""
    content_ubb: str = ""
    post_time: int


class ThreadPostsResponse(BaseModel):
    tid: int
    page: int
    posts: list[PostResponse]


class ThreadRefreshResponse(BaseModel):
    ok: bool
    fetched: int


# ============================================================
# 收藏相关
# ============================================================
class FavoriteAddRequest(BaseModel):
    tid: int = Field(gt=0)
    subject: str = ""
    author: str = ""


class FavoriteResponse(BaseModel):
    tid: int
    fid: int
    subject: str
    author: str
    added_time: int


# ============================================================
# 搜索响应
# ============================================================
class SearchResultResponse(BaseModel):
    tid: int
    pid: int = 0
    fid: int
    fname: str = ""
    authorid: int = 0
    author: str = ""
    subject: str = ""
    snippet: str = ""
    post_time: int = 0
    reply_count: int = 0
    floor: int = 0
    is_topic: int = 0
    url: str = ""


class SearchResponse(BaseModel):
    results: list[SearchResultResponse]


# ============================================================
# 版面相关
# ============================================================
class BoardResponse(BaseModel):
    fid: int
    name: str
    parent_fid: int = 0
    parent_name: str = ""
    description: str = ""


class BoardTreeResponse(BaseModel):
    fid: int
    name: str
    has_children: bool = False


class BoardFetchResponse(BaseModel):
    ok: bool
    count: int


# ============================================================
# 状态
# ============================================================
class StatusResponse(BaseModel):
    boards: int
    threads: int
    posts: int
    favorites: int


# ============================================================
# 用户搜索
# ============================================================
class UserResponse(BaseModel):
    uid: int
    username: str


# ============================================================
# 索引
# ============================================================
class IndexResult(BaseModel):
    fid: int | None = None
    pages: int | None = None
    threads: int | None = None
    boards_checked: int | None = None
    threads_changed: int | None = None
    ok: bool = True