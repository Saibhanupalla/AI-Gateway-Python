"""Anthropic (Claude) provider adapter."""
from typing import List
from providers import LLMProvider, LLMMessage, LLMResponse, register_provider


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    SUPPORTED_MODELS = [
        "claude-sonnet-4",
        "claude-haiku-4",
        "claude-opus-4",
    ]

    def complete(
        self,
        model: str,
        messages: List[LLMMessage],
        api_key: str,
        **kwargs,
    ) -> LLMResponse:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)

        # Anthropic separates system messages from the messages list
        system_msg = None
        user_messages = []
        for m in messages:
            if m.role == "system":
                system_msg = m.content
            else:
                user_messages.append({"role": m.role, "content": m.content})

        create_kwargs = {
            "model": model,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "messages": user_messages,
        }
        if system_msg:
            create_kwargs["system"] = system_msg

        response = client.messages.create(**create_kwargs)
        content = response.content[0].text if response.content else ""

        return LLMResponse(
            content=content,
            model=model,
            provider=self.name,
            raw=response.model_dump() if hasattr(response, "model_dump") else None,
        )

    def list_models(self) -> List[str]:
        return self.SUPPORTED_MODELS


register_provider(AnthropicProvider())
