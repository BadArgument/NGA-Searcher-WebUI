"""采集：httpx + __output=11 JSON API，零 HTML 解析。"""
from __future__ import annotations

import asyncio
import json
import logging
from urllib.parse import quote

import httpx

from .auth import AuthError, cookie_header, load_cookie
from .parser import parse_boards, parse_posts, parse_search_posts, parse_threads
from .ratelimit import TokenBucket
from .store import Store

log = logging.getLogger("nga_search")

BASE = "https://bbs.nga.cn"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


class Crawler:
    """异步 httpx 客户端，封装 NGA JSON API 请求。"""

    def __init__(self, rate: float = 3.0, timeout: float = 20):
        self.bucket = TokenBucket(rate)
        self.timeout = timeout
        self._cookie: str | None = None

    @property
    def cookie(self) -> str:
        if self._cookie is None:
            self._cookie = load_cookie()
        return self._cookie

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self.timeout,
            headers={
                "User-Agent": UA,
                "Cookie": self.cookie,
                "Accept": "application/json, text/html, */*",
                "Accept-Language": "zh-CN,zh;q=0.9",
            },
            follow_redirects=True,
        )

    async def _fetch(self, url: str, retries: int = 3) -> httpx.Response:
        for attempt in range(retries):
            await self.bucket.acquire()
            try:
                async with self._client() as client:
                    r = await client.get(url)
                    r.raise_for_status()
                    return r
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    await asyncio.sleep(60)
                    continue
                await asyncio.sleep(2 ** attempt)
            except (httpx.TimeoutException, httpx.ConnectError):
                await asyncio.sleep(2 ** attempt)
        raise RuntimeError(f"请求失败: {url}")

    async def _fetch_json(self, url: str) -> dict:
        r = await self._fetch(url)
        if not r.text.strip():
            raise RuntimeError("空响应")
        try:
            return r.json()
        except json.JSONDecodeError:
            if "ERROR:15" in r.text or "访客" in r.text:
                raise AuthError("Cookie 已过期，请更新 AUTH 文件")
            raise RuntimeError(f"JSON 解析失败: {r.text[:200]}")

    # ---------- 版面 ----------
    async def get_boards(self) -> list[dict]:
        j = await self._fetch_json(f"{BASE}/forum.php?__output=11")
        return parse_boards(j.get("data", []))

    # ---------- 主题 ----------
    async def get_threads(self, fid: int, page: int = 1, stid: int = 0) -> dict:
        if stid:
            url = f"{BASE}/thread.php?stid={stid}&page={page}&__output=11"
        else:
            url = f"{BASE}/thread.php?fid={fid}&page={page}&__output=11"
        j = await self._fetch_json(url)
        data = j.get("data", {})
        forum = data.get("__F", {})
        sub_forums = []
        raw_subs = forum.get("sub_forums", {}) or {}
        for key, arr in raw_subs.items():
            if isinstance(arr, list) and len(arr) >= 2:
                is_stid = str(key).startswith("t")
                sub_forums.append({
                    "fid": arr[0] if not is_stid else 0,
                    "stid": arr[0] if is_stid else 0,
                    "name": arr[1],
                    "description": arr[2] if len(arr) > 2 and arr[2] else "",
                    "is_stid": is_stid,
                })
        return {
            "threads": parse_threads(data, fid),
            "forum": forum,
            "total": data.get("__ROWS", 0),
            "page": page,
            "sub_forums": sub_forums,
        }

    async def get_total_pages(self, fid: int) -> int:
        j = await self._fetch_json(f"{BASE}/thread.php?fid={fid}&page=1&__output=11")
        rows = j.get("data", {}).get("__ROWS", 0)
        return max(1, (rows + 24) // 25)

    # ---------- 帖子 ----------
    async def get_posts(self, tid: int, page: int = 1) -> dict:
        j = await self._fetch_json(
            f"{BASE}/read.php?tid={tid}&page={page}&__output=11")
        data = j.get("data", {})
        return {
            "posts": parse_posts(data),
            "users": data.get("__U", {}),
            "total": data.get("__ROWS", 0),
            "thread_info": data.get("__T", {}),
            "forum_info": data.get("__F", {}),
            "page": page,
        }

    async def get_post_total_pages(self, tid: int) -> int:
        j = await self._fetch_json(f"{BASE}/read.php?tid={tid}&page=1&__output=11")
        rows = j.get("data", {}).get("__ROWS", 0)
        return max(1, (rows + 24) // 25)

    # ---------- 搜索 ----------
    async def search(self, fid: int, keyword: str, page: int = 1, stid: int = 0) -> dict:
        url = f"{BASE}/thread.php?key={quote(keyword)}&content=5&page={page}&__output=11"
        if fid:
            url += f"&fid={fid}"
        elif stid:
            url += f"&stid={stid}"
        j = await self._fetch_json(url)
        data = j.get("data", {})
        return {
            "threads": parse_threads(data, fid or stid),
            "total": data.get("__ROWS", 0),
            "page": page,
        }

    async def global_search(self, keyword: str, page: int = 1) -> dict:
        url = f"{BASE}/thread.php?key={quote(keyword)}&content=5&page={page}&__output=11"
        j = await self._fetch_json(url)
        data = j.get("data", {})
        return {
            "threads": parse_threads(data, 0),
            "total": data.get("__ROWS", 0),
            "page": page,
        }

    async def search_posts(self, fid: int, keyword: str, page: int = 1, stid: int = 0) -> dict:
        url = f"{BASE}/thread.php?key={quote(keyword)}&content=8&page={page}&__output=11"
        if fid:
            url += f"&fid={fid}"
        elif stid:
            url += f"&stid={stid}"
        j = await self._fetch_json(url)
        data = j.get("data", {})
        posts, thread_dicts = parse_search_posts(data)
        return {
            "posts": posts,
            "threads": thread_dicts,
            "total": data.get("__ROWS", 0),
            "page": page,
            "forum_info": data.get("__F", {}),
        }

    async def global_search_posts(self, keyword: str, page: int = 1) -> dict:
        return await self.search_posts(0, keyword, page)