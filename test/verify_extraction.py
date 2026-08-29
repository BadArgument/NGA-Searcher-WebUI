"""
验证 NGA 数据提取方法 — 用真实的 HTTP 请求测试所有解析器
运行: uv run --with httpx --with beautifulsoup4 --with lxml test/verify_extraction.py
"""
import re
import json
import ast
import httpx
from bs4 import BeautifulSoup

COOKIE = "bbsmisccookies=%7B%22pv_count_for_insad%22%3A%7B0%3A-172%2C1%3A1787935856%7D%2C%22insad_views%22%3A%7B0%3A2%2C1%3A1787935856%7D%2C%22uisetting%22%3A%7B0%3A1%2C1%3A1788496576%7D%7D; ngacn0comUserInfo=BadArgument%09BadArgument%0939%0939%09%0910%090%094%090%090%09; ngaPassportUid=67245000; ngaPassportUrlencodedUname=BadArgument; ngacn0comUserInfoCheck=af2e646c5407cfc61c069478c898b93a; ngacn0comInfoCheckTime=1787904986"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Cookie": COOKIE,
}

def fetch(url: str) -> str:
    """获取 GBK 编码页面并解码"""
    r = httpx.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.content.decode("gbk", errors="replace")


# ============================================================
# 测试 1: 版面列表 — /forum.php
# ============================================================
def test_forum_php():
    print("=" * 60)
    print("测试 1: 版面列表 — /forum.php")
    html = fetch("https://bbs.nga.cn/forum.php")
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
        boards.append({
            "fid": int(m.group(1)),
            "name": link.text.strip(),
            "category": cat.text.strip() if cat else "",
        })

    # 分页信息
    page_match = re.search(r"__PAGE\s*=\s*\{[^}]+\}['\"]?\s*,?\s*([^;]*)", html)
    # 更精确的匹配
    page_match2 = re.search(r"__PAGE\s*=\s*\{0:'[^']*',1:(-?\d+),2:(\d+),3:(\d+)\}", html)

    print(f"  ✅ 版面数: {len(boards)}")
    for b in boards[:5]:
        print(f"     fid={b['fid']:>10}, 大区={b['category']:<20}, 版面={b['name']}")
    if len(boards) > 5:
        print(f"     ... 还有 {len(boards) - 5} 个版面")
    if page_match2:
        print(f"  ✅ 分页: total_pages={page_match2.group(3)}")
    return len(boards) > 0


# ============================================================
# 测试 2: 主题列表 — /thread.php?fid=780
# ============================================================
def test_thread_list():
    print("\n" + "=" * 60)
    print("测试 2: 主题列表 — /thread.php?fid=780")
    html = fetch("https://bbs.nga.cn/thread.php?fid=780")

    # 提取 fid
    fid_match = re.search(r"__CURRENT_FID=(\d+)", html)
    fid = int(fid_match.group(1)) if fid_match else None
    print(f"  fid={fid}")

    # 提取 topicArg.add() 调用
    pattern = re.compile(
        r"topicArg\.add\(\s*"
        r"(\d+),\s*"          # idx
        r"'(\d+)',\s*"         # tid
        r"'(\d*)',\s*"         # stid
        r"'(\d+)',\s*"         # uid
        r"'([^']*)',\s*"        # author
        r"'([^']*)',\s*"        # post_time
        r"'([^']*)',\s*"        # last_reply_short
        r"'([^']*)',\s*"        # last_reply
        r"(\d+),\s*"            # flag
        r"(\d+)"                # reply_count
    )

    threads = []
    for m in pattern.finditer(html):
        threads.append({
            "tid": int(m.group(2)),
            "stid": int(m.group(3)) if m.group(3) else 0,
            "uid": int(m.group(4)),
            "author": m.group(5),
            "post_time": m.group(6),
            "last_reply": m.group(8),
            "reply_count": int(m.group(10)),
        })

    print(f"  ✅ 主题数: {len(threads)}")
    for t in threads[:5]:
        print(f"     tid={t['tid']}, author={t['author']}, replies={t['reply_count']}, time={t['post_time']}")

    # 提取标题
    title_pattern = re.compile(
        r"<a\s+href='read\.php\?tid=(\d+)[^']*'\s+class='topic'[^>]*>([^<]*)</a>"
    )
    titles = {int(m.group(1)): m.group(2) for m in title_pattern.finditer(html)}
    if titles:
        print(f"  ✅ 标题数: {len(titles)}")
        for tid, title in list(titles.items())[:3]:
            print(f"     tid={tid}: {title}")

    # 分页
    page_match = re.search(r"__PAGE\s*=\s*\{0:'[^']*',1:(-?\d+),2:(\d+),3:(\d+)\}", html)
    if page_match:
        print(f"  ✅ 分页: current={page_match.group(2)}, total={page_match.group(3)}")

    return len(threads) > 0


# ============================================================
# 测试 3: 帖子内容 — /read.php?tid=47455536
# ============================================================
def test_read_php():
    print("\n" + "=" * 60)
    print("测试 3: 帖子内容 — /read.php?tid=47455536")
    html = fetch("https://bbs.nga.cn/read.php?tid=47455536")

    # 提取 userInfo
    user_match = re.search(
        r"commonui\.userInfo\.setAll\(\s*(\{[\s\S]*?\})\s*\)",
        html
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
            print(f"  ❌ userInfo JSON 解析失败: {e}")

    # 提取帖子
    soup = BeautifulSoup(html, "lxml")
    posts = []
    for row in soup.select("tr.postrow"):
        # UID
        author_link = row.select_one("a.author")
        uid = None
        if author_link:
            uid_match = re.search(r"uid=(\d+)", author_link.get("href", ""))
            uid = int(uid_match.group(1)) if uid_match else None

        # 作者名
        author = user_info.get(str(uid), {}).get("username", "") if uid else ""

        # 日期
        date_el = row.select_one("span[id^='postdate']")
        post_time = date_el.text.strip() if date_el else ""

        # 标题
        subj_el = row.select_one("h3[id^='postsubject']")
        subject = subj_el.text.strip() if subj_el else ""

        # 正文（原始 UBB）
        content_el = row.select_one("span.postcontent.ubbcode")
        content = str(content_el) if content_el else ""

        # 楼层
        row_id = row.get("id", "")
        floor_match = re.search(r"post1strow(\d+)", row_id)
        floor = int(floor_match.group(1)) if floor_match else 0

        # PID（从 anchor）
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
    for p in posts:
        print(f"     floor={p['floor']}, pid={p['pid']}, uid={p['uid']}, author={p['author']}, "
              f"time={p['post_time']}, subject={p['subject'][:30] if p['subject'] else '(无)'}, "
              f"content_len={p['content_len']}")

    return len(posts) > 0


# ============================================================
# 测试 4: __ALL_FORUM_DATA
# ============================================================
def test_all_forum_data():
    print("\n" + "=" * 60)
    print("测试 4: __ALL_FORUM_DATA — /thread.php?fid=780")
    html = fetch("https://bbs.nga.cn/thread.php?fid=780")

    m = re.search(r"__ALL_FORUM_DATA\s*=\s*(\[[\s\S]*?\]);", html)
    if not m:
        print("  ❌ 未找到 __ALL_FORUM_DATA")
        return False

    raw = m.group(1)

    # 预处理 JS 表达式
    raw = re.sub(r"(\d+)\s*\|\s*(\d+)",
                 lambda m2: str(int(m2.group(1)) | int(m2.group(2))), raw)
    raw = re.sub(r"'(-?\d+)'\s*\|\s*0", r"\1", raw)

    try:
        data = ast.literal_eval(raw)
    except Exception as e:
        print(f"  ❌ ast.literal_eval 失败: {e}")
        # 打印 raw 的前 500 字符用于调试
        print(f"  raw[:500]: {raw[:500]}")
        return False

    forums = []
    for r in data:
        if isinstance(r, list) and len(r) >= 5:
            forums.append({
                "fid": r[0], "name": r[1], "description": r[2],
                "group_id": r[3], "permissions": r[4],
            })

    print(f"  ✅ 版面数: {len(forums)}")
    for f in forums[:5]:
        print(f"     fid={f['fid']:>10}, group_id={f['group_id']}, name={f['name']}, "
              f"desc={f['description'][:30] if f['description'] else '(无)'}")
    if len(forums) > 5:
        print(f"     ... 还有 {len(forums) - 5} 个版面")

    # 与 forum.php 对照
    return len(forums) > 0


# ============================================================
# 测试 5: 在线搜索
# ============================================================
def test_online_search():
    print("\n" + "=" * 60)
    print("测试 5: 在线搜索 — /thread.php?fid=780&search=1&key=赛马娘")
    html = fetch("https://bbs.nga.cn/thread.php?fid=780&search=1&key=%E8%B5%9B%E9%A9%AC%E5%A8%98")

    has_search = "__SEARCHING=1" in html or "search=1" in html.lower()
    print(f"  {'✅' if has_search else '⚠️'} 搜索标记: {'有' if has_search else '无'}")

    # 验证 topicArg.add() 同样存在
    if "topicArg.add" in html:
        count = html.count("topicArg.add")
        print(f"  ✅ 搜索结果: {count} 条")
    else:
        print(f"  ⚠️ 无搜索结果")

    return "topicArg.add" in html


# ============================================================
# 主流程
# ============================================================
if __name__ == "__main__":
    results = {}
    try:
        results["forum.php 版面列表"] = test_forum_php()
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        results["forum.php 版面列表"] = False

    try:
        results["thread.php 主题列表"] = test_thread_list()
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        results["thread.php 主题列表"] = False

    try:
        results["read.php 帖子内容"] = test_read_php()
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        results["read.php 帖子内容"] = False

    try:
        results["__ALL_FORUM_DATA"] = test_all_forum_data()
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        results["__ALL_FORUM_DATA"] = False

    try:
        results["在线搜索"] = test_online_search()
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        results["在线搜索"] = False

    print("\n" + "=" * 60)
    print("汇总:")
    for name, ok in results.items():
        print(f"  {'✅' if ok else '❌'} {name}")
    all_ok = all(results.values())
    print(f"\n{'🎉 全部通过!' if all_ok else '⚠️ 有失败项'}")