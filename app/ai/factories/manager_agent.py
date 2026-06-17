"""Factory del manager agent: atiende admins, con tools ERP de escritura/lectura."""

from __future__ import annotations

from agno.agent import Agent
from agno.tools.whatsapp import WhatsAppTools
from supabase import Client

from app.ai.factories.base import build_db, build_model, build_skills, build_whatsapp_tools, session_id_for
from app.ai.tools.manager_tools import build_manager_tools


def get_manager_agent(
    *,
    tenant_id: str,
    user_phone: str,
    system_prompt: str,
    model_id: str | None,
    supabase: Client,
    wa_access_token: str = "",
    wa_phone_number_id: str = "",
) -> Agent:
    tools = build_manager_tools(supabase, tenant_id)
    wa_tools = build_whatsapp_tools(
        access_token=wa_access_token,
        phone_number_id=wa_phone_number_id,
        recipient_waid=user_phone,
        enable_send_image=True,
        enable_send_document=True,
        enable_send_location=True,
        enable_send_reply_buttons=True,
        enable_send_list_message=True,
        enable_send_reaction=True,
    )
    if wa_tools:
        tools.append(wa_tools)
    return Agent(
        model=build_model(model_id),
        db=build_db(),
        instructions=system_prompt,
        tools=tools,
        skills=build_skills("erp-manager", "whatsapp-interactivo"),
        user_id=user_phone,
        session_id=session_id_for(tenant_id, user_phone),
        add_history_to_context=True,
        num_history_runs=8,
        markdown=False,
    )
