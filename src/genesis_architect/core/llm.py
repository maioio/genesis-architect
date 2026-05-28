"""LLM client via LiteLLM - works with Claude, OpenAI, Gemini, Ollama."""

from typing import Any


def ask(prompt: str, model: str = "claude-sonnet-4-6", api_key: str | None = None) -> str:
    try:
        from litellm import completion
    except ImportError:
        raise ImportError("Run: pip install genesis-architect[ai]")

    kwargs: dict[str, Any] = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    if api_key:
        kwargs["api_key"] = api_key

    response = completion(**kwargs)
    return response.choices[0].message.content or ""
