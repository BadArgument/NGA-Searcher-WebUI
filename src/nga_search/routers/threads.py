"""帖子 API 路由。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from ..crawler import Crawler
from ..export import ubb_to_html
from ..models import STATE_FIRST
from ..store import Store

router = APIRouter(prefix="/api", tags=["threads"])


@router.get("/thread/{tid}")
async def api_thread(
    tid: int,
    q: str = "",
    author: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
):
    store = Store()
    try:
        posts = store.get_posts(tid)
        thread = store.get_thread(tid)
        if not posts:
            raise HTTPException(404, "帖子未找到")

        if q:
            posts = [p for p in posts if q.lower() in (p.subject + p.content).lower()]
        if author:
            posts = [p for p in posts if author.lower() in p.author.lower()]

        return JSONResponse({
            "tid": tid,
            "subject": thread["subject"] if thread else "",
            "posts": [{
                "pid": p.pid, "floor": p.floor,
                "author": p.author, "authorid": p.authorid,
                "subject": p.subject, "content": p.content,
                "post_time": p.post_time,
            } for p in posts],
        })
    finally:
        store.close()


@router.get("/thread/{tid}/posts")
async def api_thread_posts(tid: int, page: int = 1):
    store = Store()
    store.touch_thread(tid)
    per_page = 20
    try:
        all_posts = store.get_posts_page(tid, page, per_page=per_page)
        if page == 1:
            local = all_posts
        else:
            local = [p for p in all_posts if not p.is_topic]
        posts = local

        if not local or all(p.floor == 0 for p in local):
            crawler = Crawler()
            try:
                data = crawler.get_posts(tid, page)
                raw = data["posts"]
                total = data.get("total", 0)
                expect_start = (page - 1) * per_page
                if page == 1:
                    valid = [p for p in raw if p.floor >= expect_start]
                else:
                    valid = [p for p in raw if p.floor >= expect_start and not p.is_topic]
                if not raw or expect_start >= total or not valid:
                    return JSONResponse({"tid": tid, "page": page, "posts": []})
                store.upsert_posts(valid)
                store.conn.execute(
                    "DELETE FROM posts WHERE tid=? AND floor=0 AND is_topic=0", (tid,))
                store.conn.commit()
                posts = valid
            except Exception:
                pass

        for p in posts:
            p.content = ubb_to_html(p.content)

        return JSONResponse({
            "tid": tid, "page": page,
            "posts": [{
                "pid": p.pid, "floor": p.floor,
                "author": p.author, "authorid": p.authorid,
                "subject": p.subject, "content": p.content,
                "post_time": p.post_time,
            } for p in posts],
        })
    finally:
        store.close()


@router.post("/thread/{tid}/refresh")
async def api_thread_refresh(tid: int):
    store = Store()
    crawler = Crawler()
    try:
        try:
            data = crawler.get_posts(tid, 1)
            posts = data["posts"]
            fetched = 0
            if posts:
                store.upsert_posts(posts)
                fetched += len(posts)
            store.set_thread_fetch_state(tid, STATE_FIRST)
            return JSONResponse({"ok": True, "fetched": fetched})
        except Exception as e:
            raise HTTPException(500, "刷新失败，请稍后重试")
    finally:
        store.close()