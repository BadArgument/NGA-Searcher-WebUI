"""
NGA 论坛搜索器 — Python 数据获取测试（基于 __output=11 JSON API）
用法: uv run test/test_json_api.py
Cookie 从 AUTH 文件读取（纯文本，浏览器 Network 面板复制）
"""
import json
import sys
from pathlib import Path

import httpx

AUTH_FILE = Path(__file__).parent / "AUTH"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
BASE = "https://bbs.nga.cn"


def load_cookie() -> str:
    if not AUTH_FILE.exists():
        print(f"[ERR] 未找到 {AUTH_FILE}")
        print("   请创建此文件，粘贴浏览器 F12 → Network → 请求标头 → Cookie 的完整值")
        sys.exit(1)
    cookie = AUTH_FILE.read_text(encoding="utf-8").strip()
    if not cookie or cookie.startswith("#"):
        print(f"[ERR] {AUTH_FILE} 为空或只有注释")
        sys.exit(1)
    return cookie


def fetch_json(cookie: str, url: str) -> dict:
    """用 httpx 获取 NGA JSON 数据"""
    try:
        r = httpx.get(
            url,
            headers={
                "Cookie": cookie,
                "User-Agent": UA,
                "Accept": "application/json, text/html, */*",
                "Accept-Language": "zh-CN,zh;q=0.9",
            },
            timeout=30,
        )
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise RuntimeError(f"HTTP 请求失败: {e}")

    if not r.text.strip():
        raise RuntimeError("空响应")

    try:
        return r.json()
    except json.JSONDecodeError:
        if "ERROR:15" in r.text or "访客" in r.text:
            raise RuntimeError("Cookie 无效或过期，请重新从浏览器 Network 面板复制完整 Cookie")
        raise RuntimeError(f"JSON 解析失败，响应前 200 字符: {r.text[:200]}")


# ============================================================
# 数据获取
# ============================================================
def get_boards(cookie: str) -> list[dict]:
    j = fetch_json(cookie, f"{BASE}/forum.php?__output=11")
    return j.get("data", [])


def get_threads(cookie: str, fid: int, page: int) -> dict:
    j = fetch_json(cookie, f"{BASE}/thread.php?fid={fid}&page={page}&__output=11")
    return j.get("data", {})


def get_posts(cookie: str, tid: int, page: int) -> dict:
    j = fetch_json(cookie, f"{BASE}/read.php?tid={tid}&page={page}&__output=11")
    return j.get("data", {})


def search_threads(cookie: str, fid: int, keyword: str, page: int) -> dict:
    from urllib.parse import quote
    j = fetch_json(
        cookie,
        f"{BASE}/thread.php?fid={fid}&search=1&key={quote(keyword)}&page={page}&__output=11",
    )
    return j.get("data", {})


# ============================================================
# 解析（纯 JSON，零 HTML）
# ============================================================
def parse_boards(raw: list) -> list[dict]:
    return [
        {
            "fid": b["fid"],
            "name": b["name"],
            "parent_fid": b.get("parent", {}).get("fid", 0),
            "parent_name": b.get("parent", {}).get("name", ""),
        }
        for b in raw
        if not b.get("denied")
    ]


def parse_threads(data: dict) -> tuple[list[dict], dict, int]:
    threads = data.get("__T", [])
    forum = data.get("__F", {})
    total = data.get("__ROWS", 0)
    return [
        {
            "tid": t["tid"], "fid": t.get("fid", 0),
            "author": t.get("author", ""), "authorid": t.get("authorid", 0),
            "subject": t.get("subject", ""),
            "postdate": t.get("postdate", 0), "lastpost": t.get("lastpost", 0),
            "replies": t.get("replies", 0),
        }
        for t in threads
    ], forum, total


def parse_posts(data: dict) -> tuple[list[dict], dict, int]:
    posts = data.get("__R", [])
    users = data.get("__U", {})
    total = data.get("__ROWS", 0)
    return [
        {
            "pid": p.get("pid", 0), "tid": p.get("tid", 0),
            "fid": p.get("fid", 0), "lou": p.get("lou", 0),
            "authorid": p.get("authorid", 0),
            "author": users.get(str(p.get("authorid", "")), {}).get("username", ""),
            "subject": p.get("subject", ""),
            "content": p.get("content", ""),
            "postdate": p.get("postdate", ""),
            "postdatetimestamp": p.get("postdatetimestamp", 0),
        }
        for p in posts
    ], users, total


# ============================================================
# 测试
# ============================================================
def test():
    cookie = load_cookie()

    print("=" * 60)
    print("测试 1: 版面列表 — forum.php?__output=11")
    boards = parse_boards(get_boards(cookie))
    print(f"  [OK] {len(boards)} 个版面")
    for b in boards[:5]:
        print(f"     fid={b['fid']:>10}  {b['name']:<25} 大区={b['parent_name']}")

    print("\n" + "=" * 60)
    print("测试 2: 主题列表 — thread.php?fid=780&page=1&__output=11")
    data = get_threads(cookie, 780, 1)
    threads, forum, total = parse_threads(data)
    print(f"  [OK] 版面={forum.get('name')}, 总主题={total}, 本页={len(threads)}")
    for t in threads[:5]:
        print(
            f"     tid={t['tid']}  {t['author'][:12]:<12}  "
            f"replies={t['replies']:<5}  {t['subject'][:40]}"
        )

    print("\n" + "=" * 60)
    print("测试 3: 帖子内容 — read.php?tid=47455536&page=1&__output=11")
    data = get_posts(cookie, 47455536, 1)
    posts, users, total = parse_posts(data)
    print(f"  [OK] {len(posts)} 楼, {len(users)} 个用户, 总计 {total} 楼")
    for p in posts[:5]:
        content = (p["content"] or "")[:50]
        print(f"     L{p['lou']}  {p['author'][:12]:<12}  {p['postdate']}  {content}")

    print("\n" + "=" * 60)
    print("测试 4: 在线搜索 — thread.php?fid=780&search=1&key=赛马娘&__output=11")
    data = search_threads(cookie, 780, "赛马娘", 1)
    threads, _, _ = parse_threads(data)
    print(f"  [OK] {len(threads)} 条结果")
    for t in threads[:5]:
        print(f"     tid={t['tid']}  {t['subject'][:50]}")

    print("\n[OK] 全部测试通过")


if __name__ == "__main__":
    test()