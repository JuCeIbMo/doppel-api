"""Per-turn operational trace, persisted in doppel-api's existing `activity_log`
(via `log_activity`) instead of the ported project's own SQLite `Trace` table.

Full model/graph/tool-call observability is handled by the Langfuse callback
integration (`observability/langfuse.py`); this is just a small local record,
same best-effort guarantee as every other `log_activity` call in doppel-api.
"""

from app.ai_core.config.tenant import TenantConfig
from app.services.erp.context import bot_context, log_activity


def trace_turn(
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
    log_activity(
        bot_context(tenant.tenant_id, actor=actor),
        action="ai.turn",
        module="ai",
        detail={
            "thread_id": thread_id,
            "role": role,
            "subagent": subagent,
            "model": model,
            "input_text": input_text,
            "output_text": output_text,
            "tokens": tokens,
            "tools_called": tools_called,
            "latency_ms": latency_ms,
        },
    )
