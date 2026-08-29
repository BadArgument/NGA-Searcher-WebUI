"""
完整端到端测试：Playwright → NGA → Python 解析
运行: uv run test/verify_e2e.py
"""
import re
import json
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


def fetch_html(page, url, wait_until="domcontentloaded"):
    """通过 Playwright 获取页面 HTML"""
    resp = page.goto(url, wait_until=wait_until, timeout=20000)
    html = page.content()
    return html, resp.status


def test_forum_php(page):
    """测试 1: 版面列表"""
    print("=" * 60)
    print("测试 1: 版面列表 — forum.php (Playwright)")
    html, status = fetch_html(page, "https://bbs.nga.cn/forum.php")
    print(f"  status={status}, len={len(html)}")

    soup = BeautifulSoup(html, "lxml")
    boards = []
    for row in soup.select("tr.forumrow"):
        link = row.select_one("td.c1 a.fnamecolor")
        cat = row.select_one("td.c2 b.gray")
        if not link:
            continue
        href = link.get("href", "")
        m = re.search(r"fid=(-?\d+)", href)
        if not m:
            continue
        if "javascript:void" in href:
            continue
        boards.append({
            "fid": int(m.group(1)),
            "name": link.text.strip(),
            "category": cat.text.strip() if cat else "",
        })

    print(f"  ✅ 版面数: {len(boards)}")
    for b in boards[:5]:
        print(f"     fid={b['fid']:>10}, 大区={b['category']:<20} 版面={b['name']}")
    return len(boards) > 0


def test_thread_list(page):
    """测试 2: 主题列表"""
    print("\n" + "=" * 60)
    print("测试 2: 主题列表 — thread.php?fid=780 (Playwright)")
    html, status = fetch_html(page, "https://bbs.nga.cn/thread.php?fid=780")
    print(f"  status={status}, len={len(html)}")

    fid_match = re.search(r"__CURRENT_FID=(\d+)", html)
    fid = int(fid_match.group(1)) if fid_match else None
    print(f"  fid={fid}")

    soup = BeautifulSoup(html, "lxml")
    threads = []
    for row in soup.select("tr.topicrow"):
        topic_a = row.select_one("a.topic")
        if not topic_a:
            continue
        href = topic_a.get("href", "")
        tid_match = re.search(r"tid=(\d+)", href)
        if not tid_match:
            continue
        tid = int(tid_match.group(1))
        subject = topic_a.text.strip()

        author_a = row.select_one("a.author")
        uid = 0
        author = ""
        if author_a:
            uid_match = re.search(r"uid=(\d+)", author_a.get("href", ""))
            uid = int(uid_match.group(1)) if uid_match else 0
            author = author_a.text.strip()

        replies_a = row.select_one("a.replies")
        reply_count = 0
        if replies_a:
            t = replies_a.text.strip()
            reply_count = int(t) if t.isdigit() else 0

        postdate_span = row.select_one("span.postdate")
        post_time = 0
        if postdate_span:
            t = postdate_span.text.strip()
            post_time = int(t) if t.isdigit() else 0

        threads.append({
            "tid": tid, "fid": fid, "uid": uid, "author": author,
            "subject": subject, "reply_count": reply_count,
            "post_time": post_time,
        })

    print(f"  ✅ 主题数: {len(threads)}")
    for t in threads[:5]:
        print(f"     tid={t['tid']}, author={t['author'][:15]}, "
              f"replies={t['reply_count']}, subject={t['subject'][:40]}")
    return len(threads) > 0


def test_read_php(page):
    """测试 3: 帖子内容"""
    print("\n" + "=" * 60)
    print("测试 3: 帖子内容 — read.php?tid=47455536 (Playwright)")
    html, status = fetch_html(page, "https://bbs.nga.cn/read.php?tid=47455536")
    print(f"  status={status}, len={len(html)}")

    soup = BeautifulSoup(html, "lxml")

    # userInfo
    user_match = re.search(
        r"commonui\.userInfo\.setAll\(\s*(\{[\s\S]*?\})\s*\)", html
    )
    user_info = {}
    if user_match:
        try:
            user_info = json.loads(user_match.group(1))
            usernames = {k: v.get("username", "?") for k, v in user_info.items()
                        if isinstance(v, dict) and "username" in v}
            print(f"  ✅ 用户信息: {len(usernames)} 人")
            for uid, name in usernames.items():
                print(f"     uid={uid}: {name}")
        except json.JSONDecodeError as e:
            print(f"  ❌ userInfo JSON: {e}")

    posts = []
    for row in soup.select("tr.postrow"):
        author_link = row.select_one("a.author")
        uid = None
        if author_link:
            uid_match = re.search(r"uid=(\d+)", author_link.get("href", ""))
            uid = int(uid_match.group(1)) if uid_match else None

        author = user_info.get(str(uid), {}).get("username", "") if uid else ""

        date_el = row.select_one("span[id^='postdate']")
        post_time = date_el.text.strip() if date_el else ""

        subj_el = row.select_one("h3[id^='postsubject']")
        subject = subj_el.text.strip() if subj_el else ""

        content_el = row.select_one("p.postcontent.ubbcode, span.postcontent.ubbcode")
        content = str(content_el) if content_el else ""

        row_id = row.get("id", "")
        floor_match = re.search(r"post1strow(\d+)", row_id)
        floor = int(floor_match.group(1)) if floor_match else 0

        pid_anchor = row.select_one("a[id^='pid']")
        pid = 0
        if pid_anchor:
            pid_match = re.search(r"pid(\d+)Anchor", pid_anchor.get("id", ""))
            pid = int(pid_match.group(1)) if pid_match else 0

        posts.append({
            "floor": floor, "pid": pid, "uid": uid, "author": author,
            "subject": subject, "post_time": post_time,
            "content_len": len(content),
        })

    print(f"  ✅ 帖子数: {len(posts)}")
    for p in posts[:5]:
        print(f"     floor={p['floor']}, pid={p['pid']}, uid={p['uid']}, "
              f"author={p['author'][:15]}, subj={p['subject'][:30] if p['subject'] else '(无)'}, "
              f"content_len={p['content_len']}")
    return len(posts) > 0


def test_search(page):
    """测试 4: 在线搜索"""
    print("\n" + "=" * 60)
    print("测试 4: 在线搜索 — thread.php?fid=780&search=1&key=赛马娘 (Playwright)")
    url = "https://bbs.nga.cn/thread.php?fid=780&search=1&key=%E8%B5%9B%E9%A9%AC%E5%A8%98"
    html, status = fetch_html(page, url)
    print(f"  status={status}, len={len(html)}")

    soup = BeautifulSoup(html, "lxml")
    count = 0
    for row in soup.select("tr.topicrow"):
        topic_a = row.select_one("a.topic")
        if topic_a:
            count += 1
            if count <= 3:
                print(f"     {topic_a.text.strip()[:50]}")

    print(f"  ✅ 搜索结果: {count} 条")
    return count > 0


# ============================================================
if __name__ == "__main__":
    print("启动 Playwright (headless Chromium)...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="zh-CN",
        )
        # 注入 cookie
        import json as _json
        from pathlib import Path as _Path
        _cookies_file = _Path(__file__).parent / "cookies.json"
        if _cookies_file.exists():
            context.add_cookies(_json.loads(_cookies_file.read_text()))
            print("已注入 cookie")
        page = context.new_page()

        results = {}
        for name, fn in [
            ("forum.php 版面列表", lambda: test_forum_php(page)),
            ("thread.php 主题列表", lambda: test_thread_list(page)),
            ("read.php 帖子内容", lambda: test_read_php(page)),
            ("在线搜索", lambda: test_search(page)),
        ]:
            try:
                results[name] = fn()
            except Exception as e:
                print(f"  ❌ 失败: {e}")
                import traceback
                traceback.print_exc()
                results[name] = False

        browser.close()

    print("\n" + "=" * 60)
    print("汇总:")
    for name, ok in results.items():
        print(f"  {'✅' if ok else '❌'} {name}")
    all_ok = all(results.values())
    print(f"\n{'🎉 全部通过! Python 端到端链路已打通' if all_ok else '⚠️ 有失败项'}")