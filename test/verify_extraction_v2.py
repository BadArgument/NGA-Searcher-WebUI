"""
修正后的 NGA 数据提取验证 — 基于实际 HTML 结构
运行: uv run --with beautifulsoup4 --with lxml test/verify_extraction_v2.py
"""
import re
import json
import ast
from bs4 import BeautifulSoup
from pathlib import Path

TEST_DIR = Path(__file__).parent


def read_file(name: str) -> str:
    return (TEST_DIR / name).read_text(encoding="utf-8", errors="replace")


# ============================================================
# 测试 1: 版面列表 — forum.php
# ============================================================
def test_forum_php():
    print("=" * 60)
    print("测试 1: 版面列表 — forum.php")
    html = read_file("forum_php.html")
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
        # 跳过 "访客不能直接访问"
        if "javascript:void" in href:
            continue
        boards.append({
            "fid": int(m.group(1)),
            "name": link.text.strip(),
            "category": cat.text.strip() if cat else "",
        })

    print(f"  ✅ 版面数: {len(boards)}")
    for b in boards[:5]:
        print(f"     fid={b['fid']:>10}, 大区={b['category']:<20}, 版面={b['name']}")
    if len(boards) > 5:
        print(f"     ... 还有 {len(boards) - 5} 个")

    # 分页
    page_match = re.search(r"__PAGE\s*=\s*\{0:'[^']*',1:(-?\d+),2:(\d+),3:(\d+)\}", html)
    if page_match:
        print(f"  ✅ 分页: current={page_match.group(2)}, total={page_match.group(3)}")

    return len(boards) > 0


# ============================================================
# 测试 2: 主题列表 — thread.php (HTML 直接解析，不用 topicArg.add)
# ============================================================
def test_thread_list():
    print("\n" + "=" * 60)
    print("测试 2: 主题列表 — thread.php?fid=780 (HTML 直接解析)")

    html = read_file("thread_php_fid780.html")
    soup = BeautifulSoup(html, "lxml")

    # 提取 fid
    fid_match = re.search(r"__CURRENT_FID=(\d+)", html)
    fid = int(fid_match.group(1)) if fid_match else None
    print(f"  fid={fid}")

    threads = []
    for row in soup.select("tr.topicrow"):
        # tid + subject
        topic_a = row.select_one("a.topic")
        if not topic_a:
            continue
        href = topic_a.get("href", "")
        tid_match = re.search(r"tid=(\d+)", href)
        if not tid_match:
            continue
        tid = int(tid_match.group(1))
        subject = topic_a.text.strip()

        # uid + author
        author_a = row.select_one("a.author")
        uid = 0
        author = ""
        if author_a:
            author_href = author_a.get("href", "")
            uid_match = re.search(r"uid=(\d+)", author_href)
            uid = int(uid_match.group(1)) if uid_match else 0
            author = author_a.text.strip()

        # reply_count
        replies_a = row.select_one("a.replies")
        reply_count = 0
        if replies_a:
            t = replies_a.text.strip()
            reply_count = int(t) if t.isdigit() else 0

        # post_time (Unix timestamp)
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
        print(f"     tid={t['tid']}, author={t['author']}, "
              f"replies={t['reply_count']}, time={t['post_time']}, "
              f"subject={t['subject'][:40]}")

    # 分页
    page_match = re.search(r"__PAGE\s*=\s*\{0:'[^']*',1:(-?\d+),2:(\d+),3:(\d+)\}", html)
    if page_match:
        print(f"  ✅ 分页: current={page_match.group(2)}, total={page_match.group(3)}")

    return len(threads) > 0


# ============================================================
# 测试 3: 帖子内容 — read.php
# ============================================================
def test_read_php():
    print("\n" + "=" * 60)
    print("测试 3: 帖子内容 — read.php?tid=47455536")

    html = read_file("read_php_tid47455536.html")
    soup = BeautifulSoup(html, "lxml")

    # 提取 userInfo JSON
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

    posts = []
    for row in soup.select("tr.postrow"):
        # UID — 从 a.author href
        author_link = row.select_one("a.author")
        uid = None
        if author_link:
            uid_match = re.search(r"uid=(\d+)", author_link.get("href", ""))
            uid = int(uid_match.group(1)) if uid_match else None

        # 作者名 — 从 userInfo JSON 查找（a.author 的 text 是空的，由 JS 填充）
        author = user_info.get(str(uid), {}).get("username", "") if uid else ""

        # 日期
        date_el = row.select_one("span[id^='postdate']")
        post_time = date_el.text.strip() if date_el else ""

        # 标题（仅主帖有）
        subj_el = row.select_one("h3[id^='postsubject']")
        subject = subj_el.text.strip() if subj_el else ""

        # 正文（原始 UBB）
        # 正文（原始 UBB）— 主帖是 <p>，回复是 <span>
        content_el = row.select_one("p.postcontent.ubbcode, span.postcontent.ubbcode")
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
    for p in posts[:5]:
        print(f"     floor={p['floor']}, pid={p['pid']}, uid={p['uid']}, "
              f"author={p['author']}, time={p['post_time']}, "
              f"subj={p['subject'][:30] if p['subject'] else '(无)'}, "
              f"content_len={p['content_len']}")

    return len(posts) > 0


# ============================================================
# 测试 4: __ALL_FORUM_DATA
# ============================================================
def test_all_forum_data():
    print("\n" + "=" * 60)
    print("测试 4: __ALL_FORUM_DATA")

    html = read_file("thread_php_fid780.html")
    m = re.search(r"__ALL_FORUM_DATA\s*=\s*(\{[\s\S]*?\});", html)
    if not m:
        print("  ❌ 未找到 __ALL_FORUM_DATA")
        return False

    raw = m.group(1)
    print(f"  raw 长度: {len(raw)}")

    # 预处理 JS 表达式：68|2 → 70, '542'|0 → 542
    raw = re.sub(r"(\d+)\s*\|\s*(\d+)",
                 lambda m2: str(int(m2.group(1)) | int(m2.group(2))), raw)
    raw = re.sub(r"'(-?\d+)'\s*\|\s*0", r"\1", raw)
    # 清理 GBK 乱码字符（U+FFFD）
    raw = raw.replace('\ufffd', '')

    try:
        data = json.loads(raw)  # 注意：这是 dict 格式，不是 list
    except json.JSONDecodeError:
        # 尝试 ast.literal_eval
        try:
            data = ast.literal_eval(raw)
        except Exception as e:
            print(f"  ❌ 解析失败: {e}")
            print(f"  raw[:300]: {raw[:300]}")
            return False

    if isinstance(data, dict):
        count = 0
        for k, v in data.items():
            if isinstance(v, list) and len(v) >= 3:
                count += 1
                if count <= 3:
                    print(f"     key={k}: fid={v[0]}, name={v[1]}, desc={v[2][:20] if v[2] else '(无)'}")
        print(f"  ✅ 版面数: {count}")
        return count > 0
    else:
        print(f"  ❌ 意外格式: {type(data)}")
        return False


# ============================================================
# 主流程
# ============================================================
if __name__ == "__main__":
    results = {}
    for name, fn in [
        ("forum.php 版面列表", test_forum_php),
        ("thread.php 主题列表", test_thread_list),
        ("read.php 帖子内容", test_read_php),
        ("__ALL_FORUM_DATA", test_all_forum_data),
    ]:
        try:
            results[name] = fn()
        except Exception as e:
            print(f"  ❌ 失败: {e}")
            import traceback
            traceback.print_exc()
            results[name] = False

    print("\n" + "=" * 60)
    print("汇总:")
    for name, ok in results.items():
        print(f"  {'✅' if ok else '❌'} {name}")
    all_ok = all(results.values())
    print(f"\n{'🎉 全部通过!' if all_ok else '⚠️ 有失败项'}")