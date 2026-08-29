"""数据模型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

STATE_META = 0
STATE_FIRST = 1
STATE_FULL = 2
STATE_ERROR = -1


@dataclass
class Board:
    fid: int
    name: str
    parent_fid: int = 0
    parent_name: str = ""
    description: str = ""


@dataclass
class Thread:
    tid: int
    fid: int
    authorid: int
    author: str
    subject: str
    reply_count: int = 0
    post_time: int = 0
    last_reply_time: int = 0
    type: int = 0
    stid: int = 0  # 父级 stid（parent.1），用于分组
    fetch_state: int = STATE_META


@dataclass
class Post:
    pid: int
    tid: int
    fid: int
    authorid: int
    author: str
    subject: str = ""
    content: str = ""
    post_time: int = 0
    floor: int = 0
    is_topic: int = 0
    reply_count: int = 0
    fetch_state: int = 0


@dataclass
class Favorite:
    tid: int
    fid: int
    subject: str
    author: str
    added_time: int


@dataclass
class SearchResult:
    tid: int
    fid: int
    pid: int = 0
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


@dataclass
class SearchParams:
    q: str = ""
    source: str = "offline"
    fid: int | None = None
    authorid: int | None = None
    author: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    exclude: str = ""
    match: str = ""
    groups: list = field(default_factory=list)  # 原生 list: [{"fid":1,"match":"...","search_mode":"thread"},...]
    sort: str = "time"
    limit: int = 50
    offset: int = 0