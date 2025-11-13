import tiktoken

def count_tokens_exact(text: str, model: str = "gpt-3.5-turbo") -> int:
    """
    Returns the *exact* token count using tiktoken.
    """
    encoding = tiktoken.encoding_for_model(model)
    return len(encoding.encode(text))

def estimate_cost(text: str, model: str = "gpt-3.5-turbo", use_exact=True):
    """
    Estimate total tokens and approximate cost for the given model.
    Rates are based on OpenAI's October 2025 pricing.
    """
    # Token counting
    tokens = count_tokens_exact(text, model)
    # Approx per-1K token prices (as of 2025)
    pricing = {
        "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},  # per 1K tokens
        "gpt-4-turbo": {"input": 0.01, "output": 0.03},
    }

    if model not in pricing:
        raise ValueError(f"Unknown model '{model}'. Use one of: {list(pricing.keys())}")

    input_cost = (tokens / 1000) * pricing[model]["input"]
    output_cost = (tokens / 1000) * pricing[model]["output"]
    total_cost = input_cost + output_cost  # rough combined estimate

    return {
        "model": model,
        "tokens": tokens,
        "estimated_cost_usd": round(total_cost, 6)
    }


# Example usage:
if __name__ == "__main__":
    sample_text = """You miss 100% of the shots you don’t take. – Wayne Gretzky"""
    result = estimate_cost(sample_text, model="gpt-4-turbo")
    print(result)