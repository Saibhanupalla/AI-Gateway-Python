"""
Centralized token counting and cost estimation for all LLM providers.

All pricing logic lives here — no other file should define its own cost tables.
Rates are approximate and should be updated as providers change pricing.
"""
import tiktoken


# Pricing per 1K tokens as of early 2026 (approximate)
PRICING = {
    # OpenAI
    "gpt-3.5-turbo":    {"input": 0.0005,  "output": 0.0015},
    "gpt-4":            {"input": 0.03,     "output": 0.06},
    "gpt-4-turbo":      {"input": 0.01,     "output": 0.03},
    "gpt-4o":           {"input": 0.005,    "output": 0.015},
    "gpt-4o-mini":      {"input": 0.00015,  "output": 0.0006},
    # Anthropic (approximate per-1K rates)
    "claude-sonnet-4":  {"input": 0.003,    "output": 0.015},
    "claude-haiku-4":   {"input": 0.0008,   "output": 0.004},
    # Google (approximate per-1K rates)
    "gemini-2.0-flash": {"input": 0.0001,   "output": 0.0004},
    "gemini-2.5-pro":   {"input": 0.00125,  "output": 0.01},
}

DEFAULT_MODEL = "gpt-4o-mini"


def count_tokens(text: str, model: str = DEFAULT_MODEL) -> int:
    """Count exact tokens using tiktoken. Falls back to cl100k_base for unknown models."""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        # For non-OpenAI models, use cl100k_base as a reasonable approximation
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))


def estimate_cost(
    input_text: str,
    output_text: str = "",
    model: str = DEFAULT_MODEL,
) -> dict:
    """
    Estimate token counts and cost for a prompt/response pair.

    Returns:
        {
            "model": str,
            "input_tokens": int,
            "output_tokens": int,
            "total_tokens": int,
            "input_cost_usd": float,
            "output_cost_usd": float,
            "total_cost_usd": float,
        }
    """
    input_tokens = count_tokens(input_text, model)
    output_tokens = count_tokens(output_text, model) if output_text else 0
    total_tokens = input_tokens + output_tokens

    rates = PRICING.get(model, PRICING[DEFAULT_MODEL])
    input_cost = (input_tokens / 1000) * rates["input"]
    output_cost = (output_tokens / 1000) * rates["output"]
    total_cost = input_cost + output_cost

    return {
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "input_cost_usd": round(input_cost, 8),
        "output_cost_usd": round(output_cost, 8),
        "total_cost_usd": round(total_cost, 8),
    }


# Quick test
if __name__ == "__main__":
    sample = "You miss 100% of the shots you don't take. — Wayne Gretzky"
    result = estimate_cost(sample, "That's a great quote!", model="gpt-4o")
    print(result)