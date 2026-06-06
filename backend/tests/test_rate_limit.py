import pytest
from app.rate_limit import RateLimiter


def test_allows_under_limit():
    rl = RateLimiter(max_attempts=3, window_seconds=60)
    assert rl.check("1.1.1.1") is True
    assert rl.check("1.1.1.1") is True
    assert rl.check("1.1.1.1") is True


def test_blocks_at_limit():
    rl = RateLimiter(max_attempts=3, window_seconds=60)
    for _ in range(3):
        rl.check("1.1.1.1")
    assert rl.check("1.1.1.1") is False


def test_separate_ips_tracked_separately():
    rl = RateLimiter(max_attempts=2, window_seconds=60)
    assert rl.check("1.1.1.1") is True
    assert rl.check("1.1.1.1") is True
    assert rl.check("2.2.2.2") is True


def test_window_expires(monkeypatch):
    fake_time = [1000.0]

    def fake_monotonic():
        return fake_time[0]

    monkeypatch.setattr("app.rate_limit.monotonic", fake_monotonic)
    rl = RateLimiter(max_attempts=2, window_seconds=60)
    rl.check("1.1.1.1")
    rl.check("1.1.1.1")
    assert rl.check("1.1.1.1") is False
    fake_time[0] += 61
    assert rl.check("1.1.1.1") is True
