"""Centralized DeepSeek chat-model factory.

Every agent in the core builds its chat model through :func:`build_chat_model`
so credentials, retries and timeouts live in exactly one place. Configuration
can be overridden with environment variables:

- ``DEEPSEEK_API_KEY`` (required): DeepSeek API key.
- ``DEEPSEEK_API_BASE``: optional DeepSeek API base URL.
- ``LLM_MODEL``: default model for every role (default ``deepseek-v4-flash``).
- ``LLM_MODEL_ROUTER`` / ``LLM_MODEL_PUBLIC`` / ``LLM_MODEL_ADMIN``: per-role overrides.
"""

import os
from typing import Literal

from langchain_deepseek import ChatDeepSeek

DEFAULT_MODEL = "deepseek-v4-flash"

ModelRole = Literal["router", "public", "admin"]


def resolve_model_name(role: ModelRole) -> str:
    """Return the configured model name for a role (env override or default)."""
    return (
        os.getenv(f"LLM_MODEL_{role.upper()}")
        or os.getenv("LLM_MODEL")
        or DEFAULT_MODEL
    )


def build_chat_model(role: ModelRole, *, temperature: float) -> ChatDeepSeek:
    """Build the chat model for an agent role with sane production defaults.

    Fails fast with a clear error when credentials are missing, and retries
    transient provider errors instead of killing the turn.
    """
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY is not set. Add it to your environment or .env file; "
            "the agent core cannot build any chat model without it."
        )

    model_name = resolve_model_name(role)
    return ChatDeepSeek(
        model=model_name,
        api_key=api_key,
        temperature=temperature,
        extra_body={"thinking": {"type": "disabled"}},
        max_retries=3,
        timeout=60.0,
    )
