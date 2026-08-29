"""Jinja2 模板引擎 — 模块级单例，页面路由和 API 渲染共用。"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import data_dir

TEMPLATES_DIR = data_dir() / "web" / "templates"

_jinja: Environment | None = None


def get_env() -> Environment:
    global _jinja
    if _jinja is None:
        _jinja = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(["html", "xml"]),
        )
        _jinja.filters["format_time"] = (
            lambda ts: _dt.datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M")
            if ts else ""
        )
    return _jinja