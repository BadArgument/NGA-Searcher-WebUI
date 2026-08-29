"""速率控制：全局 Token Bucket（异步）。"""
from __future__ import annotations

import asyncio
import time


class TokenBucket:
    """全局共享 Token Bucket，限速请求。默认 3 req/s。"""

    def __init__(self, rate: float = 3.0, capacity: float = 16.0):
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.updated = time.monotonic()

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