# utils/metrics.py
"""
Prometheus metrics — identical to the Flask version, reused here.
All metrics are module-level singletons to avoid duplicate registration.
"""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

tasks_submitted = Counter(
    "grammify_tasks_submitted_total",
    "Total tasks submitted to the Celery queue.",
    ["mode"],
)

tasks_completed = Counter(
    "grammify_tasks_completed_total",
    "Total tasks completed.",
    ["mode", "status"],
)

gemini_duration = Histogram(
    "grammify_gemini_duration_seconds",
    "Time spent waiting for the Gemini API.",
    ["mode"],
    buckets=(1, 2, 5, 10, 15, 20, 30, 45, 60, 90, 120),
)

rate_limit_exceeded = Counter(
    "grammify_rate_limit_exceeded_total",
    "Requests rejected by the rate limiter.",
)

quota_exceeded = Counter(
    "grammify_quota_exceeded_total",
    "Requests rejected by the quota gate.",
    ["user_type"],  # anon | free | pro
)

redis_connected = Gauge(
    "grammify_redis_connected",
    "Redis connectivity status (1=up, 0=down).",
)

auth_registrations = Counter(
    "grammify_auth_registrations_total",
    "Total successful user registrations.",
)

auth_logins = Counter(
    "grammify_auth_logins_total",
    "Total successful user logins.",
)
