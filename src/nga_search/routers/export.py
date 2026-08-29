"""导出 API 路由。"""
from __future__ import annotations

import asyncio
import re
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import JSONResponse

from .. import data_dir
from ..crawler import Crawler
from ..export import export_posts, ubb_to_html
from ..store import Store

TEMPLATES_DIR = data_dir() / "web" / "templates"

router = APIRouter(prefix="/api", tags=["export"])


def _ts_fmt(ts: int) -> str:
    if not ts:
        return ""
    import datetime
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


@router.get("/export/{tid}")
async def api_export(tid: int, format: str = "html"):
    if format not in ("html", "ubb"):
        raise HTTPException(400, "格式仅支持 html|ubb")

    store = Store()
    crawler = Crawler()
    try:
        # 导出前抓取全部帖子，确保导出完整内容
        try:
            total_pages = await crawler.get_post_total_pages(tid)
            tasks = [crawler.get_posts(tid, p) for p in range(1, total_pages + 1)]
            pages = await asyncio.gather(*tasks, return_exceptions=True)
            for data in pages:
                if isinstance(data, Exception) or not data:
                    continue
                posts_list = data.get("posts", [])
                if posts_list:
                    store.upsert_posts(posts_list)
            store.sync_users_from_posts()
        except Exception:
            pass  # 抓取失败时使用已有数据

        posts = store.get_posts(tid)
        thread = store.get_thread(tid)
        title = thread["subject"] if thread else f"tid={tid}"
        author = thread["author"] if thread else ""
        safe_title = re.sub(r'[\\/*?:"<>|]', "", title)[:50]

        if format == "html":
            css_path = data_dir() / "web" / "static" / "style.css"
            css = css_path.read_text(encoding="utf-8")
            rendered = []
            for p in posts:
                rendered.append({
                    "floor": p.floor,
                    "author": p.author,
                    "post_time_str": _ts_fmt(p.post_time),
                    "content": ubb_to_html(p.content),
                })

            try:
                from jinja2 import Environment, FileSystemLoader, select_autoescape
                _jinja = Environment(
                    loader=FileSystemLoader(str(TEMPLATES_DIR)),
                    autoescape=select_autoescape(["html", "xml"]),
                )
                tpl = _jinja.get_template("export.html.jinja2")
                html = tpl.render(title=safe_title, author=author, tid=tid,
                                  posts=rendered, css=css)
            except Exception:
                raise HTTPException(500, "模板渲染失败")

            return Response(html, media_type="text/html; charset=utf-8", headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(safe_title)}.html"
            })
        else:
            result = export_posts(store, tid, "ubb")
            return Response(result, media_type="text/plain; charset=utf-8", headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(safe_title)}.txt"
            })
    finally:
        store.close()