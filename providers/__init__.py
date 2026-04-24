"""
Base class and registry for LLM provider adapters.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Optional


@dataclass
class LLMMessage:
    role: str       # "system", "user", "assistant"
    content: str


@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str
    raw: Optional[dict] = None


class LLMProvider(ABC):
    """Abstract base class for all LLM provider adapters."""

    name: str = "base"

    @abstractmethod
    def complete(
        self,
        model: str,
        messages: List[LLMMessage],
        api_key: str,
        **kwargs,
    ) -> LLMResponse:
        """Send a completion request and return the response."""
        ...

    @abstractmethod
    def list_models(self) -> List[str]:
        """Return the list of supported model identifiers."""
        ...


# Global registry: provider_name -> LLMProvider instance
_registry: Dict[str, LLMProvider] = {}


def register_provider(provider: LLMProvider):
    _registry[provider.name] = provider


def get_provider(name: str) -> Optional[LLMProvider]:
    return _registry.get(name)


def all_providers() -> Dict[str, LLMProvider]:
    return dict(_registry)
