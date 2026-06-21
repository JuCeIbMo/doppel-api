"""Factory del client agent: atiende clientes finales vía WhatsApp."""

from __future__ import annotations

from agno.agent import Agent
from supabase import Client

from app.ai.factories.base import build_db, build_model, build_skills, build_whatsapp_tools, session_id_for
from app.ai.tools.client_tools import build_client_tools
from app.services import storefront
from app.services.erp.context import bot_context


def get_client_agent(
    *,
    tenant_id: str,
    user_phone: str,
    system_prompt: str,
    model_id: str | None,
    supabase: Client,
    wa_access_token: str = "",
    wa_phone_number_id: str = "",
) -> Agent:
    ctx = bot_context(tenant_id, actor="whatsapp_bot")
    tools = build_client_tools(ctx)
    wa_tools = build_whatsapp_tools(
        access_token=wa_access_token,
        phone_number_id=wa_phone_number_id,
        recipient_waid=user_phone,
        enable_send_image=True,
        enable_send_location=True,
        enable_send_reply_buttons=True,
        enable_send_list_message=True,
    )
    if wa_tools:
        tools.append(wa_tools)

    async def _business_info() -> dict:
        return await storefront.business_info(ctx)

    return Agent(
        model=build_model(model_id),
        db=build_db(),
        instructions=system_prompt,
        tools=tools,
        skills=build_skills(
            "catalogo-productos",
            "whatsapp-interactivo",
            "sales-diagnostico",
            "sales-presentacion",
            "sales-objecion",
            "sales-cierre",
        ),
        user_id=user_phone,
        session_id=session_id_for(tenant_id, user_phone),
        add_history_to_context=True,
        num_history_runs=5,
        markdown=False,
        dependencies={"business_info": _business_info},
        add_dependencies_to_context=True,
    )
