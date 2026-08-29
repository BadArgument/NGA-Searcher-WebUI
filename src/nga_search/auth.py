"""认证：从 AUTH 文件加载 Cookie，校验有效性。"""
from __future__ import annotations

import sys
from pathlib import Path

from . import app_dir

AUTH_PATH = app_dir() / "AUTH"


class AuthError(Exception):
    """认证失败 / Cookie 过期。"""


def load_cookie() -> str:
    """从 AUTH 文件加载用户 Cookie。"""
    if not AUTH_PATH.exists():
        raise AuthError(
            f"未找到 {AUTH_PATH}。\n"
            "  请浏览器登录 NGA → F12 → Network → 请求标头 → 复制 Cookie 整段 →\n"
            f"  粘贴到 {AUTH_PATH}"
        )
    cookie = AUTH_PATH.read_text(encoding="utf-8").strip()
    if not cookie or cookie.startswith("#"):
        raise AuthError(f"{AUTH_PATH} 为空或只有注释")
    return cookie


def cookie_header(cookie: str | None = None) -> dict[str, str]:
    """构造 Cookie 请求头。"""
    c = cookie or load_cookie()
    return {"Cookie": c}


def has_cookie() -> bool:
    return AUTH_PATH.exists() and bool(AUTH_PATH.read_text().strip())


def save_cookie(cookie: str) -> None:
    AUTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUTH_PATH.write_text(cookie.strip())


def verify() -> None:
    """校验 cookie 是否有效。"""
    import httpx

    from .crawler import UA

    if not has_cookie():
        raise AuthError("未登录。请将浏览器 Cookie 粘贴到 AUTH 文件")
    cookie = load_cookie()
    try:
        r = httpx.get(
            "https://bbs.nga.cn/thread.php?fid=7&__output=11",
            headers={"Cookie": cookie, "User-Agent": UA},
            timeout=10,
        )
        if "ERROR:15" in r.text or "访客" in r.text:
            raise AuthError("Cookie 已过期，请更新 AUTH 文件")
    except AuthError:
        raise
    except Exception:
        pass