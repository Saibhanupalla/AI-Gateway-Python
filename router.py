"""
Core routing engine — resolves model → provider, handles retry with exponential
backoff, automatic fallback to alternate providers, and circuit-breaker logic.
"""
import logging
import time
from typing import List, Optional

from providers import LLMMessage, LLMResponse, get_provider, all_providers
from config import GatewayConfig, load_config

# Import provider modules so they self-register
import providers.openai_provider     # noqa: F401
import providers.anthropic_provider  # noqa: F401
import providers.google_provider     # noqa: F401

logger = logging.getLogger("ai_gateway.router")


class CircuitBreaker:
    """Simple circuit breaker: after `threshold` consecutive failures,
    the circuit opens for `recovery_seconds`."""

    def __init__(self, threshold: int = 3, recovery_seconds: float = 60):
        self.threshold = threshold
        self.recovery_seconds = recovery_seconds
        self._failures: dict[str, int] = {}
        self._open_until: dict[str, float] = {}

    def is_open(self, provider_name: str) -> bool:
        until = self._open_until.get(provider_name, 0)
        if time.time() < until:
            return True
        # Half-open: allow one attempt
        if until > 0 and time.time() >= until:
            self._open_until.pop(provider_name, None)
            self._failures[provider_name] = 0
        return False

    def record_success(self, provider_name: str):
        self._failures[provider_name] = 0
        self._open_until.pop(provider_name, None)

    def record_failure(self, provider_name: str):
        count = self._failures.get(provider_name, 0) + 1
        self._failures[provider_name] = count
        if count >= self.threshold:
            self._open_until[provider_name] = time.time() + self.recovery_seconds
            logger.warning(
                f"Circuit OPEN for provider '{provider_name}' — "
                f"{count} consecutive failures. "
                f"Will retry in {self.recovery_seconds}s."
            )


# Module-level circuit breaker (shared across requests)
_circuit_breaker = CircuitBreaker()


def _resolve_provider_for_model(model: str, config: GatewayConfig) -> Optional[str]:
    """Return the provider name that supports the given model, per config."""
    for pname, pconf in config.providers.items():
        if pconf.enabled and model in pconf.models:
            return pname
    return None


def route_request(
    model: str,
    messages: List[LLMMessage],
    config: Optional[GatewayConfig] = None,
) -> LLMResponse:
    """
    Route a completion request through the gateway.

    1. Resolve model → provider
    2. Retry with exponential backoff on transient failures
    3. Fall back to next provider in the fallback chain on hard failures
    4. Circuit-break providers with repeated failures

    Raises RuntimeError if all providers fail.
    """
    if config is None:
        config = load_config()

    # Determine primary provider for the requested model
    primary = _resolve_provider_for_model(model, config)
    if primary is None:
        # Model not found in any configured provider — use first in fallback chain
        primary = config.routing.fallback_chain[0] if config.routing.fallback_chain else None

    # Build ordered attempt list: primary first, then fallback chain (deduplicated)
    attempt_order: list[str] = []
    if primary:
        attempt_order.append(primary)
    for fb in config.routing.fallback_chain:
        if fb not in attempt_order:
            attempt_order.append(fb)

    last_error: Optional[Exception] = None

    for provider_name in attempt_order:
        if _circuit_breaker.is_open(provider_name):
            logger.info(f"Skipping provider '{provider_name}' — circuit is open")
            continue

        provider = get_provider(provider_name)
        if provider is None:
            logger.warning(f"Provider '{provider_name}' not registered, skipping")
            continue

        pconf = config.providers.get(provider_name)
        if not pconf or not pconf.api_key:
            logger.info(f"No API key for provider '{provider_name}', skipping")
            continue

        # Determine which model to use for this provider
        # If original model isn't supported by this fallback provider, use its first model
        use_model = model
        if use_model not in (pconf.models or []):
            use_model = pconf.models[0] if pconf.models else model

        # Retry with exponential backoff
        for attempt in range(1, config.routing.retry.max_attempts + 1):
            try:
                logger.info(
                    f"Attempt {attempt}/{config.routing.retry.max_attempts} "
                    f"→ provider='{provider_name}', model='{use_model}'"
                )
                response = provider.complete(
                    model=use_model,
                    messages=messages,
                    api_key=pconf.api_key,
                )
                _circuit_breaker.record_success(provider_name)
                return response

            except Exception as e:
                last_error = e
                logger.warning(
                    f"Attempt {attempt} failed for '{provider_name}': {e}"
                )
                if attempt < config.routing.retry.max_attempts:
                    sleep_time = config.routing.retry.backoff_base_seconds * (2 ** (attempt - 1))
                    time.sleep(sleep_time)

        # All retries exhausted for this provider
        _circuit_breaker.record_failure(provider_name)
        logger.error(f"All retries exhausted for provider '{provider_name}'")

    raise RuntimeError(
        f"All providers failed. Last error: {last_error}"
    )
