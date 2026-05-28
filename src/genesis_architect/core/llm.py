"""LLM client via LiteLLM - works with Claude, OpenAI, Gemini, Ollama."""

from typing import Any


def ask(
    prompt: str,
    model: str = "claude-sonnet-4-6",
    api_key: str | None = None,
    history: list[dict] | None = None,
) -> str:
    """Send a prompt to the LLM, optionally with prior conversation history.

    history is a list of {"role": "user"|"assistant", "content": str} dicts
    representing turns before this one. The new user prompt is appended last.
    """
    try:
        from litellm import completion
    except ImportError:
        raise ImportError("Run: pip install genesis-architect[ai]")

    messages = list(history) if history else []
    messages.append({"role": "user", "content": prompt})

    kwargs: dict[str, Any] = {"model": model, "messages": messages}
    if api_key:
        kwargs["api_key"] = api_key

    response = completion(**kwargs)
    return response.choices[0].message.content or ""
