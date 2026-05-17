import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, HttpUrl

from app.config import settings
from app.security import decrypt_token
from app.services import meta_api
from app.services.manager_tools import normalize_phone
from app.services.supabase_client import get_supabase

router = APIRouter(prefix="/integrations/asistpro", tags=["Asistpro"])
security = HTTPBearer()
logger = logging.getLogger("doppel.asistpro")


class AsistproTextMessageRequest(BaseModel):
    to: str = Field(min_length=4)
    text: str = Field(min_length=1, max_length=4096)
    phone_number_id: str | None = None


class AsistproImageMessageRequest(BaseModel):
    to: str = Field(min_length=4)
    image_url: HttpUrl
    caption: str | None = Field(default=None, max_length=1024)
    phone_number_id: str | None = None


class AsistproSendMessageResponse(BaseModel):
    success: bool = True
    message_id: str
    type: Literal["text", "image"]
    phone_number_id: str
    to: str


async def require_asistpro_api_key(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> None:
    if not settings.ASISTPRO_SEND_API_KEY or credentials.credentials != settings.ASISTPRO_SEND_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Asistpro API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _get_connected_account(phone_number_id: str | None = None) -> dict:
    resolved_phone_number_id = phone_number_id
    if not resolved_phone_number_id and settings.ASISTPRO_PHONE_NUMBER_IDS:
        resolved_phone_number_id = settings.ASISTPRO_PHONE_NUMBER_IDS[0]

    query = (
        get_supabase()
        .table("whatsapp_accounts")
        .select("phone_number_id, display_phone, access_token_encrypted")
        .eq("status", "connected")
    )
    if resolved_phone_number_id:
        query = query.eq("phone_number_id", resolved_phone_number_id)
    result = query.limit(1).execute()
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No connected WhatsApp account found for Asistpro.",
        )
    return result.data[0]


def _normalize_recipient(raw_to: str, account: dict) -> str:
    recipient = normalize_phone(raw_to)
    if not recipient:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Recipient phone number is invalid.",
        )

    display_phone = normalize_phone(account.get("display_phone") or "")
    if display_phone and recipient == display_phone:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot send a WhatsApp message from a business phone number to itself.",
        )
    return recipient


def _decrypt_account_token(account: dict) -> str:
    try:
        return decrypt_token(account["access_token_encrypted"], settings.ENCRYPTION_KEY)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not decrypt WhatsApp access token.",
        )


@router.post(
    "/whatsapp/messages/text",
    response_model=AsistproSendMessageResponse,
    dependencies=[Depends(require_asistpro_api_key)],
)
async def send_text_message(request: Request, data: AsistproTextMessageRequest):
    account = _get_connected_account(data.phone_number_id)
    recipient = _normalize_recipient(data.to, account)
    message_id = await meta_api.send_whatsapp_message(
        request.app.state.http_client,
        account["phone_number_id"],
        recipient,
        data.text,
        _decrypt_account_token(account),
        settings.META_API_VERSION,
    )
    logger.info(
        "Asistpro text accepted phone_id=%s to=%s message_id=%s",
        account["phone_number_id"],
        recipient,
        message_id,
    )
    return AsistproSendMessageResponse(
        message_id=message_id,
        type="text",
        phone_number_id=account["phone_number_id"],
        to=recipient,
    )


@router.post(
    "/whatsapp/messages/image",
    response_model=AsistproSendMessageResponse,
    dependencies=[Depends(require_asistpro_api_key)],
)
async def send_image_message(request: Request, data: AsistproImageMessageRequest):
    account = _get_connected_account(data.phone_number_id)
    recipient = _normalize_recipient(data.to, account)
    message_id = await meta_api.send_whatsapp_image_message(
        request.app.state.http_client,
        account["phone_number_id"],
        recipient,
        str(data.image_url),
        data.caption,
        _decrypt_account_token(account),
        settings.META_API_VERSION,
    )
    logger.info(
        "Asistpro image accepted phone_id=%s to=%s message_id=%s",
        account["phone_number_id"],
        recipient,
        message_id,
    )
    return AsistproSendMessageResponse(
        message_id=message_id,
        type="image",
        phone_number_id=account["phone_number_id"],
        to=recipient,
    )
