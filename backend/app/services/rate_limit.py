"""In-memory rate limiting for the Gemini-backed assistant endpoint — the
one endpoint in this app that costs real money per call and has no auth in
front of it. There's no user-login system here (out of scope), so this is
IP-based, not account-based; it's meant to bound worst-case cost exposure
if this ever becomes reachable by more than one person, not to be a real
multi-tenant rate limiter.

Two independent limits, both simple fixed-window counters (not sliding —
a request right at a window boundary can theoretically get slightly more
than the nominal rate; deliberately not solving that precisely for a
cost-exposure guard):
  - PER_IP_LIMIT requests per PER_IP_WINDOW_SECONDS, per client IP.
  - GLOBAL_DAILY_LIMIT requests per rolling day, across all clients — a
    hard circuit breaker so a single day's total Gemini spend has a known
    ceiling regardless of how traffic is distributed across IPs.

In-memory only: resets on backend restart, and doesn't work across
multiple backend processes. That's an accepted limitation for a
single-process dev app, not a production-grade rate limiter — a real
deployment would need Redis or similar shared state.
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field

PER_IP_LIMIT = 10
PER_IP_WINDOW_SECONDS = 60
GLOBAL_DAILY_LIMIT = 200
DAY_SECONDS = 86400


@dataclass
class _Bucket:
    count: int = 0
    window_start: float = field(default_factory=time.time)


class RateLimiter:
    def __init__(self):
        self._per_ip: dict[str, _Bucket] = defaultdict(_Bucket)
        self._global = _Bucket()

    def check(self, client_ip: str) -> tuple[bool, str | None]:
        """Returns (allowed, reason_if_denied)."""
        now = time.time()

        global_bucket = self._global
        if now - global_bucket.window_start > DAY_SECONDS:
            global_bucket.count = 0
            global_bucket.window_start = now
        if global_bucket.count >= GLOBAL_DAILY_LIMIT:
            return False, f"Daily request limit ({GLOBAL_DAILY_LIMIT}) reached for this assistant. Try again tomorrow."

        ip_bucket = self._per_ip[client_ip]
        if now - ip_bucket.window_start > PER_IP_WINDOW_SECONDS:
            ip_bucket.count = 0
            ip_bucket.window_start = now
        if ip_bucket.count >= PER_IP_LIMIT:
            return False, f"Rate limit ({PER_IP_LIMIT} requests/{PER_IP_WINDOW_SECONDS}s) reached. Try again shortly."

        global_bucket.count += 1
        ip_bucket.count += 1
        return True, None


assistant_rate_limiter = RateLimiter()
