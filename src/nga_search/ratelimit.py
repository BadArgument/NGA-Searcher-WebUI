"""速率控制：全局 Token Bucket（同步 + 异步）。"""
from __future__ import annotations

import asyncio
import threading
import time


class TokenBucket:
    """全局共享 Token Bucket，限速请求。默认 2 req/s。线程安全。"""

    def __init__(self, rate: float = 2.0, capacity: float = 4.0):
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.updated = time.monotonic()
        self._lock = threading.Lock()

    async def acquire(self):
        while True:
            now = time.monotonic()
            elapsed = now - self.updated
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.updated = now
            if self.tokens >= 1:
                self.tokens -= 1
                return
            await asyncio.sleep(min(0.1, (1 - self.tokens) / self.rate))

    def acquire_sync(self):
        """同步版本，线程安全。"""
        while True:
            with self._lock:
                now = time.monotonic()
                elapsed = now - self.updated
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
                self.updated = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
            time.sleep(min(0.1, (1 - self.tokens) / self.rate))