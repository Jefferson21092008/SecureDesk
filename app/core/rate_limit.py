from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from hashlib import sha256
from math import ceil
from threading import Lock
from time import monotonic

from fastapi import HTTPException, Request, status


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    @staticmethod
    def _validate(limit: int, window_seconds: int) -> None:
        if limit < 1:
            raise ValueError("Rate limit must be at least 1")
        if window_seconds < 1:
            raise ValueError("Rate limit window must be at least 1 second")

    @staticmethod
    def _prune(events: deque[float], now: float, window_seconds: int) -> None:
        threshold = now - window_seconds
        while events and events[0] <= threshold:
            events.popleft()

    @staticmethod
    def _retry_after(events: deque[float], now: float, window_seconds: int) -> int:
        if not events:
            return 1
        return max(1, ceil(window_seconds - (now - events[0])))

    def consume(self, key: str, limit: int, window_seconds: int) -> RateLimitDecision:
        self._validate(limit, window_seconds)
        now = monotonic()

        with self._lock:
            events = self._events[key]
            self._prune(events, now, window_seconds)

            if len(events) >= limit:
                return RateLimitDecision(
                    allowed=False,
                    limit=limit,
                    remaining=0,
                    retry_after=self._retry_after(events, now, window_seconds),
                )

            events.append(now)
            return RateLimitDecision(
                allowed=True,
                limit=limit,
                remaining=max(0, limit - len(events)),
                retry_after=0,
            )

    def inspect(self, key: str, limit: int, window_seconds: int) -> RateLimitDecision:
        self._validate(limit, window_seconds)
        now = monotonic()

        with self._lock:
            events = self._events[key]
            self._prune(events, now, window_seconds)
            blocked = len(events) >= limit
            return RateLimitDecision(
                allowed=not blocked,
                limit=limit,
                remaining=max(0, limit - len(events)),
                retry_after=self._retry_after(events, now, window_seconds) if blocked else 0,
            )

    def record(self, key: str, window_seconds: int) -> None:
        if window_seconds < 1:
            raise ValueError("Rate limit window must be at least 1 second")
        now = monotonic()

        with self._lock:
            events = self._events[key]
            self._prune(events, now, window_seconds)
            events.append(now)

    def clear(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


rate_limiter = SlidingWindowRateLimiter()


def client_ip(request: Request) -> str:
    # Do not trust X-Forwarded-For by default: clients can spoof it unless the
    # application is behind a configured trusted proxy.
    if request.client is None or not request.client.host:
        return "unknown"
    return request.client.host


def identifier_digest(value: str) -> str:
    normalized = value.strip().lower()
    return sha256(normalized.encode("utf-8")).hexdigest()


def rate_limit_exception(detail: str, decision: RateLimitDecision) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=detail,
        headers={
            "Retry-After": str(decision.retry_after),
            "X-RateLimit-Limit": str(decision.limit),
            "X-RateLimit-Remaining": "0",
        },
    )
