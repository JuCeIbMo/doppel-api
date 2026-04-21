import logging
import asyncio

import anthropic

from app.config import settings

logger = logging.getLogger("doppel.ai_bot")

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


async def generate_response(
    system_prompt: str,
    conversation: list[dict],
    model: str = "claude-sonnet-4-20250514",
) -> str:
    """
    Generate an AI response using Anthropic.

    Args:
        system_prompt: The bot's personality/instructions.
        conversation: List of {"role": "user"|"assistant", "content": "..."} in chronological order.
        model: Anthropic model ID.

    Returns:
        The generated response text.
    """
    last_error: Exception | None = None

    for attempt in range(settings.ANTHROPIC_API_RETRIES):
        try:
            response = await _get_client().messages.create(
                model=model,
                max_tokens=1024,
                system=system_prompt,
                messages=conversation,
            )
            return response.content[0].text
        except Exception as exc:
            last_error = exc
            if attempt == settings.ANTHROPIC_API_RETRIES - 1:
                raise
            logger.warning("Anthropic request failed, retrying attempt=%s", attempt + 1)
            await asyncio.sleep(0.5)

    if last_error is not None:
        raise last_error
    raise RuntimeError("Anthropic request failed without an exception")
