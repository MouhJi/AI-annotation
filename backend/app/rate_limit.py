import hashlib
import time
from collections import OrderedDict, deque
from threading import Lock
from fastapi import HTTPException, Request

class RateLimiter:
    def __init__(self): self.buckets = OrderedDict(); self.lock = Lock()
    def check(self, request: Request, action: str, account: str = "", limit: int = 10, window: int = 60):
        ip = request.client.host if request.client else "unknown"  # Do not trust forwarded headers.
        keys = [(action, "ip", ip)]
        if account: keys.append((action, "account", hashlib.sha256(account.casefold().encode()).hexdigest()))
        now = time.monotonic()
        with self.lock:
            for key in keys:
                bucket = self.buckets.setdefault(key, deque())
                while bucket and bucket[0] <= now-window: bucket.popleft()
                if len(bucket) >= limit: raise HTTPException(429, "Too many attempts. Please try again later.", headers={"Retry-After": str(window)})
                bucket.append(now); self.buckets.move_to_end(key)
            while len(self.buckets) > 10000: self.buckets.popitem(last=False)

limiter = RateLimiter()
