"""HTML 安全清洗 — 白名单过滤，防止 XSS。"""
from __future__ import annotations

import re

# 允许的标签
_ALLOWED_TAGS = {
    "a", "img", "strong", "em", "b", "i", "u", "del", "s",
    "blockquote", "pre", "code", "ul", "ol", "li",
    "details", "summary", "table", "tr", "td", "th",
    "h4", "br", "div", "span", "p",
}

# 允许的协议
_ALLOWED_PROTOCOLS = {"http:", "https:", "//", "ftp:", "mailto:"}

# 允许的属性（按标签）
_ALLOWED_ATTRS: dict[str, set[str]] = {
    "a": {"href", "rel", "class"},
    "img": {"src", "alt", "title"},
    "details": {"class"},
    "summary": {"class"},
    "div": {"class", "style"},
    "span": {"class", "style"},
    "td": {"class"},
    "th": {"class"},
    "table": {"class"},
    "blockquote": {"class"},
    "pre": {"class"},
    "code": {"class"},
    "ul": {"class"},
    "ol": {"class"},
    "li": {"class"},
}

# 内联 style 中允许的 CSS 属性
_ALLOWED_CSS = {"color", "background-color", "font-weight", "font-style", "text-decoration"}


def sanitize_html(html: str) -> str:
    """白名单清洗 HTML，移除不安全标签/属性/样式。"""
    if not html:
        return ""

    # 移除 script / style / iframe / object / embed 等危险标签（含内容）
    html = re.sub(r'<(script|style|iframe|object|embed|form|input|link|meta)[\s\S]*?</\1>', '', html, flags=re.I)
    html = re.sub(r'<(script|style|iframe|object|embed|form|input|link|meta)\s[^>]*?/>', '', html, flags=re.I)

    # 处理每个标签，只保留白名单标签和属性
    def _clean_tag(m: re.Match) -> str:
        is_closing = m.group(1) == "/"
        tag = m.group(2).lower()
        if tag not in _ALLOWED_TAGS:
            return ""
        if is_closing:
            return f"</{tag}>"
        attrs_str = m.group(3) or ""
        cleaned = _clean_attrs(tag, attrs_str)
        self_closing = "/" if m.group(0).endswith("/>") else ""
        return f"<{tag}{cleaned}{self_closing}>"

    # 匹配开始标签和自闭合标签
    html = re.sub(r'<(/?)(\w+)((?:\s[^>]*?)?)\s*/?>', _clean_tag, html)

    return html


def _clean_attrs(tag: str, attrs_str: str) -> str:
    """清洗标签属性，只保留白名单属性并验证协议。"""
    allowed = _ALLOWED_ATTRS.get(tag, set())
    if not allowed:
        return ""

    result_parts: list[str] = []
    for m in re.finditer(r'([\w-]+)\s*=\s*"([^"]*)"', attrs_str):
        name = m.group(1).lower()
        value = m.group(2)
        if name not in allowed:
            continue
        if name in ("href", "src"):
            value = _clean_url(value)
        elif name == "style":
            value = _clean_style(value)
            if not value:
                continue
        result_parts.append(f'{name}="{value}"')

    return " " + " ".join(result_parts) if result_parts else ""


def _clean_url(url: str) -> str:
    """验证 URL 协议是否在白名单中。"""
    url = url.strip()
    if not url:
        return ""
    # 相对路径允许
    if url.startswith("/") or url.startswith("./") or url.startswith("../"):
        return url
    # 检查协议
    lower = url.lower()
    for proto in _ALLOWED_PROTOCOLS:
        if lower.startswith(proto):
            return url
    # 不安全的协议 → 替换为 #
    if ":" in url and not url.startswith("//"):
        return "#"
    return url


def _clean_style(style: str) -> str:
    """只保留白名单 CSS 属性。"""
    parts = style.split(";")
    cleaned = []
    for part in parts:
        if ":" not in part:
            continue
        prop, _, val = part.partition(":")
        prop = prop.strip().lower()
        if prop in _ALLOWED_CSS:
            cleaned.append(f"{prop}:{val.strip()}")
    return "; ".join(cleaned)