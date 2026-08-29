"""NGA 版面搜索器 — 全版面本地全文搜索工具（CLI + Web 双模）。"""
from __future__ import annotations

import sys
from pathlib import Path

__version__ = "0.1.0"


def app_dir() -> Path:
    """exe 同级目录（打包时）或项目根目录（开发时）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent.parent


def data_dir() -> Path:
    """数据文件目录：打包时为 sys._MEIPASS，开发时为项目根目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent.parent
