"""JSON 解析：__output=11 API 响应 → 数据模型。零 HTML 解析。"""
from __future__ import annotations

from .models import Board, Post, Thread


# ============================================================
# 版面列表 — forum.php?__output=11
# ============================================================
def parse_boards(data: list[dict]) -> list[Board]:
    """解析版面列表 JSON。
    data: [{fid, name, descrip, url, parent: {fid, name}}]
    """
    result = []
    for b in data:
        if b.get("denied"):
            continue
        parent = b.get("parent") or {}
        name = b.get("name", "")
        if not isinstance(name, str):
            name = ""
        parent_name = parent.get("name", "")
        if not isinstance(parent_name, str):
            parent_name = ""
        result.append(Board(
            fid=b["fid"],
            name=name,
            parent_fid=parent.get("fid", 0),
            parent_name=parent_name,
            description=b.get("descrip") or "",
        ))
    return result


# ============================================================
# 主题列表 — thread.php?fid=X&page=N&__output=11
# ============================================================
def parse_threads(data: dict, fid: int) -> list[Thread]:
    """解析主题列表 JSON。
    data: {__T: [{tid, fid, author, authorid, subject, postdate, lastpost, replies}], ...}
    """
    result = []
    for t in data.get("__T", []) or []:
        subject = t.get("subject", "")
        if not isinstance(subject, str):
            subject = ""
        author = t.get("author", "")
        if not isinstance(author, str):
            author = ""
        parent = t.get("parent", {}) or {}
        stid = parent.get("1", 0) if isinstance(parent, dict) else 0
        result.append(Thread(
            tid=t["tid"],
            fid=t.get("fid", fid),
            authorid=t.get("authorid", 0),
            author=author,
            subject=subject,
            reply_count=t.get("replies", 0),
            post_time=t.get("postdate", 0),
            last_reply_time=t.get("lastpost", 0),
            type=t.get("type", 0),
            stid=stid,
        ))
    return result


# ============================================================
# 回复搜索结果 — thread.php?key=...&content=8&__output=11
# ============================================================
def parse_search_posts(data: dict) -> tuple[list[Post], list[dict]]:
    """解析回复搜索结果 JSON。
    data: {__T: [{tid, fid, author, authorid, subject, ..., __P: {pid, authorid, content, postdate}}], ...}
    每个 __T 条目含一个 __P 字段，表示匹配到的回复帖子。
    返回 (posts, thread_dicts)，thread_dicts 按 tid 去重。
    """
    result = []
    seen_tids: set[int] = set()
    thread_dicts: list[dict] = []
    for t in data.get("__T", []) or []:
        # 提取线程信息（去重）
        tid = t.get("tid", 0)
        if tid and tid not in seen_tids:
            seen_tids.add(tid)
            subject = t.get("subject", "")
            if not isinstance(subject, str):
                subject = ""
            thread_dicts.append({
                "pid": tid,
                "tid": tid,
                "fid": t.get("fid", 0),
                "authorid": t.get("authorid", 0),
                "author": t.get("author", "") or "",
                "subject": subject,
                "content": subject,
                "post_time": t.get("postdate", 0),
                "reply_count": t.get("replies", 0),
                "fetch_state": 1,
            })

        pp = t.get("__P") or {}
        if not pp:
            continue
        if pp.get("denied"):
            continue
        content = pp.get("content", "")
        if not isinstance(content, str):
            content = ""
        result.append(Post(
            pid=pp.get("pid", 0),
            tid=tid,
            fid=t.get("fid", 0),
            authorid=pp.get("authorid", 0),
            author="",  # __P 不含 author，后续从 users 或 thread 补充
            subject=pp.get("subject", "") or "",
            content=content,
            post_time=pp.get("postdate", 0),
            floor=0,
            is_topic=0,
        ))
    return result, thread_dicts


# ============================================================
# 帖子内容 — read.php?tid=X&page=N&__output=11
# ============================================================
def parse_posts(data: dict) -> list[Post]:
    """解析帖子内容 JSON。
    data: {__R: [{pid, tid, fid, lou, authorid, subject, content, postdate, postdatetimestamp}],
           __U: {uid: {username, ...}}}
    """
    users = data.get("__U", {}) or {}
    result = []
    for p in data.get("__R", []) or []:
        uid = p.get("authorid", 0)
        uid_str = str(uid)
        user = users.get(uid_str, {}) if uid_str in users else {}
        author = user.get("username", "") or p.get("author", "")
        result.append(Post(
            pid=p.get("pid", 0),
            tid=p.get("tid", 0),
            fid=p.get("fid", 0),
            authorid=uid,
            author=author,
            subject=p.get("subject", ""),
            content=p.get("content", ""),
            post_time=p.get("postdatetimestamp", 0),
            floor=p.get("lou", 0),
            is_topic=1 if p.get("lou", 0) == 0 else 0,
        ))
    return result