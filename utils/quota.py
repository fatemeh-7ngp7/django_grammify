# utils/quota.py
"""
Quota service for Grammify.

Quota rules
-----------
Anonymous user:
  - Only 'correct' mode is allowed.
  - 3 requests per day (keyed by IP address).

Authenticated user (free plan):
  - All modes allowed.
  - 20 requests per day (keyed by user ID).

Authenticated user (pro plan):
  - All modes allowed.
  - 200 requests per day (keyed by user ID).

All counters reset at midnight UTC (TTL = seconds until end of day).
Redis INCR + EXPIRE is atomic and self-cleaning — no cron needed.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

import redis
from django.conf import settings

logger = logging.getLogger(__name__)

_pool: redis.ConnectionPool | None = None


def _get_redis() -> redis.Redis:
    global _pool
    if _pool is None:
        _pool = redis.ConnectionPool.from_url(
            settings.REDIS_QUOTA_URL,
            decode_responses=True,
            max_connections=20,
        )
    return redis.Redis(connection_pool=_pool)


def _seconds_until_midnight_utc() -> int:
    """Return the number of seconds until midnight UTC."""
    now = datetime.now(timezone.utc)
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((midnight - now).total_seconds()))


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


@dataclass
class QuotaResult:
    allowed: bool
    limit: int
    used: int
    remaining: int
    reason: Optional[str] = None

    @property
    def resets_in_seconds(self) -> int:
        return _seconds_until_midnight_utc()


def check_and_increment(
    *,
    user_id: Optional[int],
    user_plan: Optional[str],
    ip: str,
    mode: str,
) -> QuotaResult:
    """
    Check the quota for this request and increment the counter if allowed.

    Args:
        user_id:   Authenticated user's PK, or None for anonymous.
        user_plan: 'free' | 'pro' | None for anonymous.
        ip:        Client IP address (used as anonymous key).
        mode:      Processing mode ('correct', 'improve', etc.)

    Returns:
        QuotaResult with allowed=True if the request may proceed.
    """
    is_anonymous = user_id is None

    # --- Mode gate for anonymous users ---
    if is_anonymous and mode not in settings.ANON_ALLOWED_MODES:
        return QuotaResult(
            allowed=False,
            limit=settings.ANON_DAILY_LIMIT,
            used=0,
            remaining=0,
            reason=(
                f"Mode '{mode}' requires a registered account. "
                f"Anonymous users may only use: {', '.join(sorted(settings.ANON_ALLOWED_MODES))}."
            ),
        )

    # --- Build Redis key ---
    if is_anonymous:
        # Hash the IP so raw IPs are never stored in Redis.
        ip_hash = hashlib.sha256(ip.encode()).hexdigest()[:16]
        key = f"quota:anon:{ip_hash}:{_today_utc()}"
        limit = settings.ANON_DAILY_LIMIT
    else:
        key = f"quota:user:{user_id}:{_today_utc()}"
        limit = (
            settings.PRO_DAILY_LIMIT
            if user_plan == "pro"
            else settings.FREE_DAILY_LIMIT
        )

    # --- Atomic increment + TTL ---
    try:
        r = _get_redis()
        count = r.incr(key)
        if count == 1:
            # First use today — set TTL to end of day so the key self-expires.
            r.expire(key, _seconds_until_midnight_utc())
    except redis.RedisError as exc:
        # Fail open: Redis is unavailable, allow the request and log.
        logger.error("Redis unavailable during quota check: %s", exc)
        return QuotaResult(allowed=True, limit=limit, used=0, remaining=limit)

    remaining = max(0, limit - count)

    if count > limit:
        # Decrement so the counter doesn't silently grow past the limit.
        try:
            r.decr(key)
        except redis.RedisError:
            pass

        subject = "Your" if not is_anonymous else "Anonymous"
        return QuotaResult(
            allowed=False,
            limit=limit,
            used=limit,
            remaining=0,
            reason=(
                f"{subject} daily limit of {limit} request(s) has been reached. "
                "Resets at midnight UTC."
                + ("" if not is_anonymous else " Register for a higher limit.")
            ),
        )

    return QuotaResult(allowed=True, limit=limit, used=count, remaining=remaining)


def get_usage(*, user_id: Optional[int], user_plan: Optional[str], ip: str) -> QuotaResult:
    """Read the current quota usage without incrementing — used by /me endpoint."""
    is_anonymous = user_id is None

    if is_anonymous:
        ip_hash = hashlib.sha256(ip.encode()).hexdigest()[:16]
        key = f"quota:anon:{ip_hash}:{_today_utc()}"
        limit = settings.ANON_DAILY_LIMIT
    else:
        key = f"quota:user:{user_id}:{_today_utc()}"
        limit = (
            settings.PRO_DAILY_LIMIT if user_plan == "pro" else settings.FREE_DAILY_LIMIT
        )

    try:
        raw = _get_redis().get(key)
        count = int(raw) if raw else 0
    except redis.RedisError:
        count = 0

    return QuotaResult(
        allowed=count < limit,
        limit=limit,
        used=count,
        remaining=max(0, limit - count),
    )
