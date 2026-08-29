"""导出：UBB → HTML / UBB 原文。"""
from __future__ import annotations

import html
import re

from .emotes import SMILES, SMILE_BASE
from .models import Post
from .store import Store


def export_posts(store: Store, tid: int, fmt: str = "html") -> str:
    """导出帖子全部楼层。fmt: html | ubb"""
    if fmt not in ("html", "ubb"):
        raise ValueError(f"不支持的导出格式: {fmt}（仅支持 html|ubb）")
    posts = store.get_posts(tid)
    thread = store.get_thread(tid)
    title = None
    if thread:
        title = thread.get("subject") if isinstance(thread, dict) else thread.subject
    if not title:
        title = f"tid={tid}"

    if fmt == "html":
        return _to_html(title, posts)
    return _to_ubb(title, posts)


# ============================================================
# HTML 导出
# ============================================================
_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body {{ font-family: -apple-system, "Microsoft YaHei", sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background: #f5f5f5; }}
.post {{ background: #fff; margin: 12px 0; padding: 16px; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }}
.header {{ color: #666; font-size: 13px; margin-bottom: 8px; }}
.floor {{ color: #999; }}
.content {{ line-height: 1.7; }}
blockquote {{ border-left: 3px solid #ddd; margin: 8px 0; padding: 4px 12px; color: #666; background: #fafafa; }}
details.collapse-box {{ border: 1px solid #e0e0e0; border-radius: 10px; margin: 8px 0; background: #fafbfc; overflow: hidden; }}
details.collapse-box summary.collapse-summary {{ cursor: pointer; padding: 8px 12px; background: #f0f1f3; border-bottom: 1px solid #e0e0e0; user-select: none; font-size: 14px; color: #333; font-weight: 500; }}
details.collapse-box[open] summary.collapse-summary {{ border-radius: 10px 10px 0 0; }}
details.collapse-box summary.collapse-summary::marker {{ content: ''; }}
details.collapse-box summary.collapse-summary::before {{ content: "▸ "; color: #999; }}
details.collapse-box[open] summary.collapse-summary::before {{ content: "▾ "; color: #999; }}
details.collapse-box .collapse-body {{ padding: 10px 12px; }}
img {{ max-width: 100%; }}
a {{ color: #1890ff; }}
del {{ color: #999; }}
pre {{ background: #f6f6f6; padding: 10px; overflow-x: auto; border-radius: 4px; }}
code {{ font-family: Menlo, Consolas, monospace; }}
ul, ol {{ padding-left: 24px; }}
h1 {{ font-size: 20px; }}
</style>
</head>
<body>
<h1>{title}</h1>
{body}
</body>
</html>"""


def _to_html(title: str, posts: list[Post]) -> str:
    body = ""
    for p in posts:
        content = ubb_to_html(p.content)
        body += (
            f'<div class="post">'
            f'<div class="header">'
            f'<span class="floor">#{p.floor}</span> '
            f'<strong>{_esc(p.author)}</strong> · '
            f'<span>{_ts_to_date(p.post_time)}</span>'
            f'</div>'
            f'<div class="content">{content}</div>'
            f'</div>\n'
        )
    return _HTML_TEMPLATE.format(title=_esc(title), body=body)


# ============================================================
# UBB 原文导出
# ============================================================
def _to_ubb(title: str, posts: list[Post]) -> str:
    lines = [title, "=" * len(title), ""]
    for p in posts:
        lines.append(f"#{p.floor} [{p.author}] {_ts_to_date(p.post_time)}")
        content = (p.content or "")
        # <br/> → \n, HTML 实体 → 对应符号
        content = re.sub(r'<br\s*/?>', '\n', content, flags=re.I)
        content = html.unescape(content)
        lines.append(content)
        lines.append("")
    return "\n".join(lines)


# ============================================================
# UBB → HTML 转换器
# ============================================================
NGA_BBS = "https://bbs.nga.cn"
# NGA 附件查看域名（当前生效），相对路径 ./mon_... 拼接在这里
NGA_ATTACH_BASE = "https://img.nga.cn/attachments"


def _resolve_media_url(url: str) -> str:
    """把 [img] 里的 src 解析为完整可访问 URL（去除本地代理依赖）。"""
    p = (url or "").strip()
    if not p:
        return p
    if p.startswith("http://") or p.startswith("https://"):
        return p
    rel = p[2:] if p.startswith("./") else p
    if rel.startswith("attachments/"):
        return f"https://img.nga.cn/{rel}"
    if rel.startswith("mon_") or rel.startswith("upload/"):
        return f"{NGA_ATTACH_BASE}/{rel}"
    # 其他相对路径（本地静态资源等）原样返回
    return p


def _smile_img(prefix: str, name: str) -> str:
    """[s:prefix:name] 表情 → <img>。未知表情返回空字符串。"""
    f = SMILES.get(prefix, {}).get(name)
    if not f:
        return ""
    return f'<img src="{SMILE_BASE}/{f}" alt="{name}" title="{name}">'


def ubb_to_html(text: str) -> str:
    """NGA UBB 格式 -> HTML。NGA 内容已含 HTML，不额外转义。"""
    if not text:
        return ""
    s = text.replace("\r\n", "\n")

    # ---- 1. 块级容器（支持嵌套，循环处理） ----
    # [quote]...[/quote]
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r'\[quote\]([\s\S]*?)\[/quote\]',
                   r'<blockquote>\1</blockquote>', s)
    # [collapse]...[/collapse] 与 [collapse=标题]...[/collapse]
    prev = None
    while prev != s:
        prev = s
        s = re.sub(
            r'\[collapse(?:=([^\]]*))?\]([\s\S]*?)\[/collapse\]',
            lambda m: f'<details class="collapse-box"><summary class="collapse-summary">{m.group(1) or "展开"}</summary><div class="collapse-body">{m.group(2)}</div></details>',
            s,
        )

    # ---- 2. 块级元素 ----
    s = re.sub(r'\[code\]([\s\S]*?)\[/code\]', r'<pre><code>\1</code></pre>', s, flags=re.S)
    s = re.sub(r'\[list\]([\s\S]*?)\[/list\]', r'<ul>\1</ul>', s, flags=re.S)
    s = re.sub(r'\[list=([^\]]+)\]([\s\S]*?)\[/list\]', r'<ol>\2</ol>', s, flags=re.S)
    s = re.sub(r'\[\*\]([^\n]*)', r'<li>\1</li>', s)
    s = re.sub(r'\[table\]([\s\S]*?)\[/table\]', r'<table>\1</table>', s, flags=re.S)
    s = re.sub(r'\[tr\]([\s\S]*?)\[/tr\]', r'<tr>\1</tr>', s, flags=re.S)
    s = re.sub(r'\[td\]([\s\S]*?)\[/td\]', r'<td>\1</td>', s, flags=re.S)
    s = re.sub(r'\[th\]([\s\S]*?)\[/th\]', r'<th>\1</th>', s, flags=re.S)
    s = re.sub(r'\[h\]([\s\S]*?)\[/h\]', r'<h4>\1</h4>', s, flags=re.S)
    s = re.sub(r'\[ah\]([\s\S]*?)\[/ah\]', r'<h4>\1</h4>', s, flags=re.S)

    # ---- 3. 图片 / 附件 ----
    s = re.sub(
        r'\[img\]([\s\S]*?)\[/img\]',
        lambda m: f'<img src="{_resolve_media_url(m.group(1))}" alt="图片">',
        s,
    )

    # ---- 4. 链接 ----
    s = re.sub(r'\[pid=(\d+(?:,\d+)*)[^\]]*\]([\s\S]*?)\[/pid\]',
               r'<a href="{0}/read.php?pid=\1">\2</a>'.format(NGA_BBS), s, flags=re.S)
    s = re.sub(r'\[tid=(\d+)[^\]]*\]([\s\S]*?)\[/tid\]',
               rf'<a href="{NGA_BBS}/read.php?tid=\1">\2</a>', s, flags=re.S)
    s = re.sub(r'\[uid=(\d+)\]([\s\S]*?)\[/uid\]',
               rf'<a href="{NGA_BBS}/nuke.php?func=ucp&uid=\1">\2</a>', s, flags=re.S)
    s = re.sub(r'\[url=([^\]]+)\]([\s\S]*?)\[/url\]',
               r'<a href="\1" rel="nofollow">\2</a>', s, flags=re.S)
    s = re.sub(r'\[url\]([\s\S]*?)\[/url\]',
               r'<a href="\1" rel="nofollow">\1</a>', s, flags=re.S)

    # ---- 5. 行内样式 ----
    s = re.sub(r'\[b\]([\s\S]*?)\[/b\]', r'<strong>\1</strong>', s, flags=re.S)
    s = re.sub(r'\[i\]([\s\S]*?)\[/i\]', r'<em>\1</em>', s, flags=re.S)
    s = re.sub(r'\[u\]([\s\S]*?)\[/u\]', r'<u>\1</u>', s, flags=re.S)
    s = re.sub(r'\[del\]([\s\S]*?)\[/del\]', r'<del>\1</del>', s, flags=re.S)
    s = re.sub(r'\[s\]([\s\S]*?)\[/s\]', r'<del>\1</del>', s, flags=re.S)
    s = re.sub(r'\[color=([^\]]+)\]([\s\S]*?)\[/color\]',
               r'<span style="color:\1">\2</span>', s, flags=re.S)
    s = re.sub(r'\[size=([^\]]+)\]([\s\S]*?)\[/size\]',
               r'<span style="font-size:\1">\2</span>', s, flags=re.S)
    s = re.sub(r'\[font=([^\]]+)\]([\s\S]*?)\[/font\]',
               r'<span style="font-family:\1">\2</span>', s, flags=re.S)
    s = re.sub(r'\[align=([^\]]+)\]([\s\S]*?)\[/align\]',
               r'<div style="text-align:\1">\2</div>', s, flags=re.S)

    # ---- 6. 表情 [s:prefix:name] ----
    s = re.sub(r'\[s:([a-z0-9]+):([^\]]*)\]',
               lambda m: _smile_img(m.group(1).lower(), m.group(2).strip()), s)

    # ---- 7. 清理残留未知标签 ----
    s = re.sub(r'\[/?[a-z][a-z0-9]*(?:=[^\]]*)?\]', '', s)

    # ---- 8. HTML 安全清洗 ----
    from .sanitizer import sanitize_html
    s = sanitize_html(s)

    return s


# ============================================================
# 工具函数
# ============================================================
def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _ts_to_date(ts: int) -> str:
    if not ts:
        return ""
    import datetime
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
