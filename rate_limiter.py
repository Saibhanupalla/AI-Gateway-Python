"""
Token-aware rate limiter.

Enforces per-user, per-department, and global token/request budgets
stored in the RateLimit database table.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlmodel import select, col
from database import get_session, RateLimit, RateLimitUsage

logger = logging.getLogger("ai_gateway.rate_limiter")


class RateLimitExceeded(Exception):
    """Raised when a rate limit is hit."""
    def __init__(self, message: str, retry_after_seconds: int = 60):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


def _get_window_start(window: str) -> datetime:
    """Return the start-of-window datetime for 'minute', 'hour', or 'day'."""
    now = datetime.now(timezone.utc)
    if window == "minute":
        return now.replace(second=0, microsecond=0)
    elif window == "hour":
        return now.replace(minute=0, second=0, microsecond=0)
    elif window == "day":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def check_rate_limit(
    username: str,
    department: Optional[str] = None,
) -> None:
    """
    Check all applicable rate limits for a user.
    Raises RateLimitExceeded if any limit is breached.
    """
    session = get_session()
    try:
        # Fetch all potentially matching rules
        rules = session.exec(select(RateLimit)).all()
        for rule in rules:
            # Does this rule apply?
            if rule.scope == "user" and rule.target != username:
                continue
            if rule.scope == "department" and rule.target != department:
                continue
            # scope == "global" applies to everyone

            window_start = _get_window_start(rule.window)

            # Sum usage in current window
            query = select(RateLimitUsage).where(
                RateLimitUsage.rate_limit_id == rule.id,
                col(RateLimitUsage.timestamp) >= window_start.isoformat(),
            )
            if rule.scope == "user":
                query = query.where(RateLimitUsage.username == username)
            # For department/global, sum all matching usage rows

            usages = session.exec(query).all()
            total_tokens = sum(u.tokens_used for u in usages)
            total_requests = len(usages)

            if rule.max_tokens and total_tokens >= rule.max_tokens:
                raise RateLimitExceeded(
                    f"Token limit exceeded ({total_tokens}/{rule.max_tokens}) "
                    f"for {rule.scope}={rule.target or 'all'} per {rule.window}",
                    retry_after_seconds=_seconds_until_window_end(rule.window),
                )
            if rule.max_requests and total_requests >= rule.max_requests:
                raise RateLimitExceeded(
                    f"Request limit exceeded ({total_requests}/{rule.max_requests}) "
                    f"for {rule.scope}={rule.target or 'all'} per {rule.window}",
                    retry_after_seconds=_seconds_until_window_end(rule.window),
                )
    finally:
        session.close()


def record_usage(
    username: str,
    tokens_used: int,
    department: Optional[str] = None,
):
    """Record a request's token usage against all applicable rate limit rules."""
    session = get_session()
    try:
        rules = session.exec(select(RateLimit)).all()
        for rule in rules:
            if rule.scope == "user" and rule.target != username:
                continue
            if rule.scope == "department" and rule.target != department:
                continue

            usage = RateLimitUsage(
                rate_limit_id=rule.id,
                username=username,
                tokens_used=tokens_used,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            session.add(usage)
        session.commit()
    finally:
        session.close()


def _seconds_until_window_end(window: str) -> int:
    now = datetime.now(timezone.utc)
    if window == "minute":
        return 60 - now.second
    elif window == "hour":
        return 3600 - (now.minute * 60 + now.second)
    elif window == "day":
        return 86400 - (now.hour * 3600 + now.minute * 60 + now.second)
    return 60
