"""
Gateway configuration loader.

Reads gateway_config.yaml for provider settings, routing rules, and feature flags.
"""
import os
import yaml
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

CONFIG_PATH = os.getenv("GATEWAY_CONFIG_PATH", "gateway_config.yaml")


@dataclass
class ProviderConfig:
    name: str
    api_key_env: str
    models: List[str] = field(default_factory=list)
    enabled: bool = True

    @property
    def api_key(self) -> Optional[str]:
        return os.getenv(self.api_key_env)


@dataclass
class RetryConfig:
    max_attempts: int = 3
    backoff_base_seconds: float = 1.0


@dataclass
class RoutingConfig:
    default_model: str = "gpt-4o-mini"
    fallback_chain: List[str] = field(default_factory=lambda: ["openai"])
    retry: RetryConfig = field(default_factory=RetryConfig)


@dataclass
class CacheConfig:
    enabled: bool = True
    ttl_seconds: int = 3600  # 1 hour default


@dataclass
class GatewayConfig:
    providers: Dict[str, ProviderConfig] = field(default_factory=dict)
    routing: RoutingConfig = field(default_factory=RoutingConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)


def load_config(path: str = CONFIG_PATH) -> GatewayConfig:
    """Load gateway configuration from YAML file. Falls back to defaults if file missing."""
    if not os.path.exists(path):
        return _default_config()

    with open(path, "r") as f:
        raw = yaml.safe_load(f) or {}

    providers = {}
    for name, pdata in raw.get("providers", {}).items():
        providers[name] = ProviderConfig(
            name=name,
            api_key_env=pdata.get("api_key_env", ""),
            models=pdata.get("models", []),
            enabled=pdata.get("enabled", True),
        )

    retry_raw = raw.get("routing", {}).get("retry", {})
    retry = RetryConfig(
        max_attempts=retry_raw.get("max_attempts", 3),
        backoff_base_seconds=retry_raw.get("backoff_base_seconds", 1.0),
    )

    routing = RoutingConfig(
        default_model=raw.get("routing", {}).get("default_model", "gpt-4o-mini"),
        fallback_chain=raw.get("routing", {}).get("fallback_chain", ["openai"]),
        retry=retry,
    )

    cache_raw = raw.get("cache", {})
    cache = CacheConfig(
        enabled=cache_raw.get("enabled", True),
        ttl_seconds=cache_raw.get("ttl_seconds", 3600),
    )

    return GatewayConfig(providers=providers, routing=routing, cache=cache)


def _default_config() -> GatewayConfig:
    """Sensible defaults when no config file exists."""
    return GatewayConfig(
        providers={
            "openai": ProviderConfig(
                name="openai",
                api_key_env="OPENAI_API_KEY",
                models=["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo", "gpt-4", "gpt-4-turbo"],
            ),
            "anthropic": ProviderConfig(
                name="anthropic",
                api_key_env="ANTHROPIC_API_KEY",
                models=["claude-sonnet-4", "claude-haiku-4"],
            ),
            "google": ProviderConfig(
                name="google",
                api_key_env="GOOGLE_API_KEY",
                models=["gemini-2.0-flash", "gemini-2.5-pro"],
            ),
        },
        routing=RoutingConfig(
            default_model="gpt-4o-mini",
            fallback_chain=["openai", "anthropic", "google"],
        ),
    )
