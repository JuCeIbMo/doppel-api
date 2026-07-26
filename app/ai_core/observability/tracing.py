"""Per-turn operational trace, persisted in doppel-api's existing `activity_log`
(via `log_activity`) instead of the ported project's own SQLite `Trace` table.

Full model/graph/tool-call observability is handled by the Langfuse callback
integration (`observability/langfuse.py`); this is just a small local record,
same best-effort guarantee as every other `log_activity` call in doppel-api.
"""

from app.ai_core.config.tenant import TenantConfig
from app.services.erp.context import bot_context, log_activity

# `activity_log` is an audit table with no retention policy, and this writes one
# row per turn of a real WhatsApp conversation. Storing the full text kept an
# unbounded, indefinite copy of every customer's messages. A prefix is enough to
# recognise a turn while debugging; the full I/O lives in Langfuse when it is
# configured, which is the tool built for it.
MAX_TRACED_TEXT = 120


def _truncate(text: str) -> str:
    text = text or ""
    return text if len(text) <= MAX_TRACED_TEXT else text[:MAX_TRACED_TEXT] + "…"


async def trace_turn(
    tenant: TenantConfig,
    thread_id: str,
    role: str,
    subagent: str,
    model: str,
    input_text: str,
    output_text: str,
    tokens: int,
    tools_called: str,
    latency_ms: int,
) -> None:
    actor = "whatsapp_bot" if role == "public" else "admin_bot"
    await log_activity(
        bot_context(tenant.tenant_id, actor=actor),
        action="ai.turn",
        module="ai",
        detail={
            "thread_id": thread_id,
            "role": role,
            "subagent": subagent,
            "model": model,
            "input_text": _truncate(input_text),
            "input_chars": len(input_text or ""),
            "output_text": _truncate(output_text),
            "output_chars": len(output_text or ""),
            "tokens": tokens,
            "tools_called": tools_called,
            "latency_ms": latency_ms,
        },
    )
