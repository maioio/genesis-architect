"""LLM client - routes to Claude, GPT-4, Gemini, Ollama, and more via LiteLLM.

`model` selects the provider (LiteLLM's model-string convention):
  "claude-sonnet-4-6"  (default)  -> Anthropic
  "gpt-4o"                        -> OpenAI
  "gemini/gemini-2.0-flash"       -> Google
  "ollama/llama3"                 -> local Ollama, no api_key needed

See https://docs.litellm.ai/docs/providers for the full provider list.
"""

from typing import Any

import litellm


class LLMError(RuntimeError):
    """Raised when the LLM call itself fails — bad/expired key, rate limit,
    network error, unsupported model, etc. Wraps whatever LiteLLM/the
    underlying provider SDK raised (all subclass openai.OpenAIError) so
    callers only need to know about this one exception, not every provider's
    own exception hierarchy."""


def ask(
    prompt: str,
    model: str = "claude-sonnet-4-6",
    api_key: str | None = None,
    history: list[dict] | None = None,
) -> str:
    """Send a prompt to an LLM, optionally with prior conversation history.

    history is a list of {"role": "user"|"assistant", "content": str} dicts
    representing turns before this one. The new user prompt is appended last.

    api_key, when given, is passed straight through to whichever provider
    `model` selects — local providers like Ollama don't need one.
    """
    messages: list[dict[str, Any]] = list(history) if history else []
    messages.append({"role": "user", "content": prompt})

    kwargs: dict[str, Any] = {"model": model, "messages": messages, "max_tokens": 4096}
    if api_key:
        kwargs["api_key"] = api_key

    try:
        response = litellm.completion(**kwargs)
    except Exception as exc:
        raise LLMError(f"LLM call to '{model}' failed: {exc}") from exc

    if not response.choices:
        return ""
    return response.choices[0].message.content or ""
