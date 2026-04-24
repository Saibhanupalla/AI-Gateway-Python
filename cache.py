"""
Response caching with exact-match hash lookups and configurable TTL.

Caches LLM responses keyed by hash(model + prompt) to avoid redundant API calls.
"""
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlmodel import select
from database import get_session, CacheEntry

logger = logging.getLogger("ai_gateway.cache")


def _cache_key(model: str, prompt: str) -> str:
    """Generate a deterministic hash key from model + prompt."""
    raw = f"{model}::{prompt}"
    return hashlib.sha256(raw.encode()).hexdigest()


def get_cached_response(model: str, prompt: str, ttl_seconds: int = 3600) -> Optional[dict]:
    """
    Look up a cached response. Returns None on cache miss or expired entry.

    Returns:
        {
            "llm_response": str,
            "model": str,
            "tokens_used": int,
            "cost_usd": float,
            "provider": str,
            "cache_hit": True,
        }
    """
    key = _cache_key(model, prompt)
    session = get_session()
    try:
        entry = session.exec(
            select(CacheEntry).where(CacheEntry.cache_key == key)
        ).first()

        if entry is None:
            return None

        # Check TTL
        if entry.created_at:
            created = datetime.fromisoformat(entry.created_at)
            if datetime.now(timezone.utc) - created > timedelta(seconds=ttl_seconds):
                # Expired — delete and return miss
                session.delete(entry)
                session.commit()
                logger.info(f"Cache expired for key={key[:12]}…")
                return None

        logger.info(f"Cache HIT for key={key[:12]}…")
        return {
            "llm_response": entry.response_text,
            "model": entry.model,
            "tokens_used": entry.tokens_used or 0,
            "cost_usd": entry.cost_usd or 0.0,
            "provider": entry.provider or "cached",
            "cache_hit": True,
        }
    finally:
        session.close()


def store_cached_response(
    model: str,
    prompt: str,
    response_text: str,
    tokens_used: int = 0,
    cost_usd: float = 0.0,
    provider: str = "",
):
    """Store a response in the cache."""
    key = _cache_key(model, prompt)
    session = get_session()
    try:
        # Upsert: delete old entry if exists
        existing = session.exec(
            select(CacheEntry).where(CacheEntry.cache_key == key)
        ).first()
        if existing:
            session.delete(existing)

        entry = CacheEntry(
            cache_key=key,
            model=model,
            prompt_hash=key,
            response_text=response_text,
            tokens_used=tokens_used,
            cost_usd=cost_usd,
            provider=provider,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        session.add(entry)
        session.commit()
        logger.info(f"Cache STORE for key={key[:12]}…")
    finally:
        session.close()
