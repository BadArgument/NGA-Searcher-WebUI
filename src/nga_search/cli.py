"""入口 — 默认启动 WebUI。"""
from __future__ import annotations

import argparse
import sys
import threading
import webbrowser

from .auth import AuthError
from .indexer import Indexer
from .store import Store


def _gc_loop():
    """后台 GC 线程：每 30 分钟清理超过 7 天未访问的帖子。"""
    import time as _time
    while True:
        _time.sleep(1800)
        try:
            store = Store()
            n = store.gc_cleanup(max_age_days=7)
            store.close()
            if n > 0:
                print(f"[GC] 清理了 {n} 条过期帖子")
        except Exception as e:
            print(f"[GC] 清理出错: {e}")


def main():
    p = argparse.ArgumentParser(prog="nga-search", description="NGA 论坛搜索 WebUI")
    p.add_argument("--port", type=int, default=8765, help="HTTP 端口（默认 8765）")
    p.add_argument("--host", type=str, default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    p.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    args = p.parse_args()

    store = Store()
    try:
        boards = store.get_boards()
        if not boards:
            print("[启动] 初始化版面列表...")
            indexer = Indexer(store)
            try:
                n = indexer.discover_boards()
                print(f"[启动] 发现 {n} 个版面")
            except AuthError:
                print("[ERR] Cookie 已过期，请更新 AUTH 文件", file=sys.stderr)
                sys.exit(1)
            except Exception as e:
                print(f"[WARN] 版面列表初始化失败: {e}，继续启动服务")
    finally:
        store.close()

    if not args.no_open:
        webbrowser.open(f"http://localhost:{args.port}")

    from .web import create_app
    app = create_app()

    t = threading.Thread(target=_gc_loop, daemon=True)
    t.start()

    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")