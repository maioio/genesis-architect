"""LLM client - Claude via Anthropic SDK."""

from typing import Any

import anthropic


def ask(
    prompt: str,
    model: str = "claude-sonnet-4-6",
    api_key: str | None = None,
    history: list[dict] | None = None,
) -> str:
    """Send a prompt to Claude, optionally with prior conversation history.

    history is a list of {"role": "user"|"assistant", "content": str} dicts
    representing turns before this one. The new user prompt is appended last.
    """
    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    messages: list[dict[str, Any]] = list(history) if history else []
    messages.append({"role": "user", "content": prompt})

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=messages,  # type: ignore[arg-type]
    )
    for block in response.content:
        if getattr(block, "type", None) == "text":
            return block.text
    return ""
