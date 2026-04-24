"""Google Gemini provider adapter."""
from typing import List
from providers import LLMProvider, LLMMessage, LLMResponse, register_provider


class GoogleProvider(LLMProvider):
    name = "google"

    SUPPORTED_MODELS = [
        "gemini-2.0-flash",
        "gemini-2.5-pro",
    ]

    def complete(
        self,
        model: str,
        messages: List[LLMMessage],
        api_key: str,
        **kwargs,
    ) -> LLMResponse:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        gmodel = genai.GenerativeModel(model)

        # Convert messages to Gemini format
        # Gemini uses a flat content list; combine all user messages
        combined = "\n".join(m.content for m in messages)
        response = gmodel.generate_content(combined)
        content = response.text if response.text else ""

        return LLMResponse(
            content=content,
            model=model,
            provider=self.name,
            raw=None,
        )

    def list_models(self) -> List[str]:
        return self.SUPPORTED_MODELS


register_provider(GoogleProvider())
