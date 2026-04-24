"""OpenAI provider adapter."""
from typing import List
from openai import OpenAI
from providers import LLMProvider, LLMMessage, LLMResponse, register_provider


class OpenAIProvider(LLMProvider):
    name = "openai"

    SUPPORTED_MODELS = [
        "gpt-3.5-turbo",
        "gpt-4",
        "gpt-4-turbo",
        "gpt-4o",
        "gpt-4o-mini",
    ]

    def complete(
        self,
        model: str,
        messages: List[LLMMessage],
        api_key: str,
        **kwargs,
    ) -> LLMResponse:
        client = OpenAI(api_key=api_key)
        formatted = [{"role": m.role, "content": m.content} for m in messages]
        completion = client.chat.completions.create(
            model=model,
            messages=formatted,
            **kwargs,
        )
        content = completion.choices[0].message.content or ""
        return LLMResponse(
            content=content,
            model=model,
            provider=self.name,
            raw=completion.model_dump() if hasattr(completion, "model_dump") else None,
        )

    def list_models(self) -> List[str]:
        return self.SUPPORTED_MODELS


# Auto-register on import
register_provider(OpenAIProvider())
