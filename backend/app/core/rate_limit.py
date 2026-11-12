"""Fixed-window rate limiting backed by Redis (falls back to in-process counters if Redis is down)."""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict

import redis
from fastapi import Request

from app.core.config import get_settings
from app.core.errors import AppError

log = logging.getLogger("supportflow.ratelimit")
_local: dict[str, int] = defaultdict(int)
_lock = threading.Lock()
_redis: redis.Redis | None = None


class RateLimited(AppError):
    status_code = 429
    code = "rate_limited"


def _client() -> redis.Redis | None:
    global _redis
    if _redis is None:
        try:
            _redis = redis.Redis.from_url(get_settings().redis_url, socket_timeout=0.5, socket_connect_timeout=0.5)
            _redis.ping()
        except redis.RedisError:
            _redis = None
    return _redis


def _hit(key: str, limit: int, window: int = 60) -> None:
    if get_settings().environment == "test":
        return
    bucket = f"rl:{key}:{int(time.time() // window)}"
    r = _client()
    count: int
    if r is not None:
        try:
            pipe = r.pipeline()
            pipe.incr(bucket)
            pipe.expire(bucket, window + 5)
            count = int(pipe.execute()[0])
        except redis.RedisError:
            r = None
    if r is None:
        with _lock:
            _local[bucket] += 1
            count = _local[bucket]
    if count > limit:
        raise RateLimited("Too many requests, slow down", details={"limit_per_minute": limit})


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def auth_limit(request: Request) -> None:
    _hit(f"auth:{_ip(request)}", get_settings().auth_rate_limit_per_minute)


def api_limit(request: Request) -> None:
    _hit(f"api:{_ip(request)}", get_settings().rate_limit_per_minute)
