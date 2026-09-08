"""Tests for the assistant's rate limiter — pure logic, no network or
warehouse needed. Uses fresh RateLimiter instances (not the shared
assistant_rate_limiter singleton) so tests don't interfere with each other."""

from app.services.rate_limit import GLOBAL_DAILY_LIMIT, PER_IP_LIMIT, RateLimiter


def test_allows_requests_under_the_per_ip_limit():
    limiter = RateLimiter()
    for _ in range(PER_IP_LIMIT):
        allowed, reason = limiter.check("1.2.3.4")
        assert allowed is True
        assert reason is None


def test_denies_requests_over_the_per_ip_limit():
    limiter = RateLimiter()
    for _ in range(PER_IP_LIMIT):
        limiter.check("1.2.3.4")
    allowed, reason = limiter.check("1.2.3.4")
    assert allowed is False
    assert "Rate limit" in reason


def test_per_ip_limits_are_independent_across_ips():
    limiter = RateLimiter()
    for _ in range(PER_IP_LIMIT):
        limiter.check("1.2.3.4")
    # A different IP should still be allowed even though 1.2.3.4 is maxed out.
    allowed, _ = limiter.check("5.6.7.8")
    assert allowed is True


def test_global_daily_limit_applies_across_all_ips():
    limiter = RateLimiter()
    # One request per unique IP, so no single IP ever gets close to
    # PER_IP_LIMIT — only the global daily cap can be the thing that trips.
    denied_reason = None
    for i in range(GLOBAL_DAILY_LIMIT + 5):
        ip = f"10.{i // 65536}.{(i // 256) % 256}.{i % 256}"
        allowed, reason = limiter.check(ip)
        if not allowed:
            denied_reason = reason
            break
    assert denied_reason is not None
    assert "Daily" in denied_reason
