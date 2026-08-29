"""页面路由 — SSR 渲染。"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from .. import data_dir
from ..auth import has_cookie
from ..crawler import Crawler
from ..models import Board, Thread, STATE_FULL, STATE_FIRST, STATE_META
from ..store import Store

TEMPLATES_DIR = data_dir() / "web" / "templates"

router = APIRouter()

# Jinja2 环境（模块级单例）
try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    import datetime as _dt
    _jinja = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    _jinja.filters["format_time"] = lambda ts: _dt.datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M") if ts else ""
except Exception:
    _jinja = None


def _render(template: str, **ctx) -> HTMLResponse:
    status_code = ctx.pop("status_code", 200)
    if _jinja is None:
        return HTMLResponse(f"<h1>模板引擎未加载</h1><pre>{ctx}</pre>", status_code=status_code)
    tpl = _jinja.get_template(template)
    return HTMLResponse(tpl.render(**ctx), status_code=status_code)


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    store = Store()
    try:
        boards = store.get_boards()
        return _render("index.html.jinja2", request=request, boards=boards, active_page="search")
    finally:
        store.close()


@router.get("/favorites", response_class=HTMLResponse)
async def favorites_page(request: Request):
    store = Store()
    try:
        favs = store.list_favorites()
        return _render("favorites.html.jinja2", request=request, favorites=favs, active_page="favorites")
    finally:
        store.close()


@router.get("/boards", response_class=HTMLResponse)
async def boards_page(request: Request):
    store = Store()
    try:
        boards = store.get_boards()
        groups = defaultdict(list)
        for b in boards:
            groups[b.parent_name or ""].append(b)
        return _render("boards.html.jinja2",
                       request=request, boards=boards,
                       board_groups=dict(groups),
                       has_boards=len(boards) > 0,
                       active_page="boards")
    finally:
        store.close()


@router.get("/thread/{tid}", response_class=HTMLResponse)
async def thread_page(request: Request, tid: int):
    store = Store()
    try:
        thread = store.get_thread(tid)
        fetch_error = None

        if not thread:
            crawler = Crawler()
            try:
                data = await crawler.get_posts(tid, 1)
                tinfo = data.get("thread_info", {})
                if tinfo:
                    thread = Thread(
                        tid=tid, fid=tinfo.get("fid", 0),
                        authorid=tinfo.get("authorid", 0),
                        author=tinfo.get("author", ""),
                        subject=tinfo.get("subject", f"tid={tid}"),
                    )
            except Exception as e:
                fetch_error = str(e)

        if not thread:
            if not has_cookie():
                return _render("error.html.jinja2",
                    request=request, title="未配置 AUTH Cookie",
                    message="帖子不在本地索引中，且未配置 AUTH Cookie 无法在线获取。",
                    hint="请将浏览器 Cookie 放入 AUTH 文件", status_code=404)
            elif fetch_error:
                return _render("error.html.jinja2",
                    request=request, title="帖子获取失败",
                    message=f"tid={tid} 不在本地索引中，且在线获取失败。",
                    hint=fetch_error, status_code=404)
            else:
                return _render("error.html.jinja2",
                    request=request, title="帖子未找到",
                    message=f"tid={tid} 不存在或已被删除。", status_code=404)

        is_fav = store.is_favorite(tid)
        store.touch_thread(tid)
        return _render("thread.html.jinja2",
                       request=request, thread=thread,
                       is_favorite=is_fav, tid=tid)
    finally:
        store.close()


@router.get("/board/{fid}", response_class=HTMLResponse)
async def board_page(request: Request, fid: int, page: int = 1, stid: int = 0):
    store = Store()
    try:
        board = store.get_board(fid)
        local_threads = store.get_threads_by_fid(fid, limit=50) if board else []

        crawler = Crawler()
        threads = []
        forum = {}
        sub_forums = []
        ungrouped = []
        threads_by_stid = {}
        stale = False

        try:
            data = await crawler.get_threads(fid, page, stid=stid)
            threads = data["threads"]
            forum = data["forum"]
            sub_forums = data.get("sub_forums", [])
            threads_by_stid = defaultdict(list)
            ungrouped = []
            for t in threads:
                if t.stid:
                    threads_by_stid[t.stid].append(t)
                else:
                    ungrouped.append(t)
            if stid:
                ungrouped = [t for t in threads_by_stid.get(stid, []) if t.tid != stid]
                threads_by_stid = {}
            if threads:
                thread_dicts = [{
                    "pid": t.tid, "tid": t.tid, "fid": t.fid,
                    "authorid": t.authorid, "author": t.author,
                    "subject": t.subject, "content": t.subject,
                    "post_time": t.post_time, "reply_count": t.reply_count,
                    "fetch_state": 1,
                } for t in threads]
                store.upsert_thread_posts(thread_dicts)
            if forum and forum.get("fid"):
                existing = store.get_board(forum["fid"])
                store.upsert_boards([Board(
                    fid=forum["fid"],
                    name=forum.get("name", ""),
                    parent_fid=existing.parent_fid if existing else 0,
                    parent_name=existing.parent_name if existing else "",
                    description=existing.description if existing else "",
                )])
        except Exception:
            stale = True
            if local_threads:
                threads = [Thread(
                    tid=t["tid"], fid=t["fid"],
                    authorid=t.get("authorid", 0), author=t.get("author", ""),
                    subject=t.get("subject", ""), post_time=t.get("post_time", 0),
                    reply_count=t.get("reply_count", 0),
                ) for t in local_threads]
                ungrouped = threads
                threads_by_stid = {}
            else:
                threads = []
                ungrouped = []
                threads_by_stid = {}

        return _render("board.html.jinja2",
                       request=request, board=board, threads=ungrouped,
                       sub_forums=sub_forums, forum=forum,
                       threads_by_stid=dict(threads_by_stid),
                       stid=stid, stale=stale)
    finally:
        store.close()


@router.get("/status", response_class=HTMLResponse)
async def status_page(request: Request):
    store = Store()
    try:
        counts = store.counts()
        return _render("status.html.jinja2",
                       request=request, counts=counts,
                       db_path=str(store.path),
                       db_size=store.path.stat().st_size / 1024 / 1024 if store.path.exists() else 0)
    finally:
        store.close()