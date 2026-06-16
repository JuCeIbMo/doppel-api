"""Factory del client agent: atiende clientes finales, solo tools read-only."""

from __future__ import annotations

from agno.agent import Agent
from supabase import Client

from app.ai.factories.base import build_db, build_model, session_id_for
from app.ai.tools.client_tools import build_client_tools


def get_client_agent(
    *,
    tenant_id: str,
    user_phone: str,
    system_prompt: str,
    model_id: str | None,
    supabase: Client,
) -> Agent:
    return Agent(
        model=build_model(model_id),
        db=build_db(),
        instructions=system_prompt,
        tools=build_client_tools(supabase, tenant_id),
        user_id=user_phone,
        session_id=session_id_for(tenant_id, user_phone),
        add_history_to_context=True,
        num_history_runs=5,
        markdown=False,
    )
