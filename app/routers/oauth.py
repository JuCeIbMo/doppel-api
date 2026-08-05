"""HTTP boundary for WhatsApp Embedded Signup."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from app.dependencies import get_current_user
from app.models.schemas import OAuthExchangeRequest, OAuthExchangeResponse
from app.whatsapp.onboarding import (
    OnboardingError,
    onboard_whatsapp,
    run_smb_sync,
)

router = APIRouter(tags=["OAuth"])


@router.post("/oauth/exchange", response_model=OAuthExchangeResponse)
async def oauth_exchange(
    request: Request,
    data: OAuthExchangeRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
):
    try:
        result = await onboard_whatsapp(
            request.app.state.http_client,
            code=data.code,
            waba_id=data.waba_id,
            supplied_phone_id=data.phone_number_id,
            is_coexistence=data.is_coexistence,
            user_id=str(current_user.id),
            user_email=current_user.email,
        )
    except OnboardingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    if result.sync_task:
        background_tasks.add_task(
            run_smb_sync,
            result.sync_task.phone_number_id,
            result.sync_task.access_token,
        )
    return OAuthExchangeResponse(
        success=True,
        tenant_id=result.tenant_id,
        message="WhatsApp conectado exitosamente",
        display_phone=result.display_phone,
        business_name=result.business_name,
        requires_manager_setup=result.requires_manager_setup,
    )
