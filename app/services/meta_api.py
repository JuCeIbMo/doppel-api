import asyncio
from pathlib import Path

import httpx

from app.config import settings


# Meta error codes we want to treat as idempotent success on retries.
# Docs: https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes
_ALREADY_REGISTERED_CODES = {133005, 133006}  # phone already registered / pin reset in progress
_ALREADY_REGISTERED_HINTS = ("already registered", "already been registered")
_ALREADY_SUBSCRIBED_HINTS = ("already subscribed",)


def _error_payload(response: httpx.Response) -> dict:
    try:
        return response.json().get("error", {}) or {}
    except Exception:
        return {}


def is_already_registered(response: httpx.Response) -> bool:
    err = _error_payload(response)
    if err.get("code") in _ALREADY_REGISTERED_CODES:
        return True
    msg = (err.get("message") or "").lower()
    return any(hint in msg for hint in _ALREADY_REGISTERED_HINTS)


def is_already_subscribed(response: httpx.Response) -> bool:
    err = _error_payload(response)
    msg = (err.get("message") or "").lower()
    return any(hint in msg for hint in _ALREADY_SUBSCRIBED_HINTS)


def meta_error_detail(response: httpx.Response) -> str:
    """Return a short, log-friendly description of a Meta error response."""
    err = _error_payload(response)
    if err:
        code = err.get("code")
        subcode = err.get("error_subcode")
        message = err.get("message") or response.text[:300]
        tag = f"[{code}/{subcode}]" if subcode is not None else f"[{code}]"
        return f"{tag} {message}"
    return response.text[:300]


def _should_retry(exc: httpx.HTTPError | None = None, response: httpx.Response | None = None) -> bool:
    if exc is not None:
        return isinstance(exc, (httpx.TimeoutException, httpx.NetworkError))
    if response is not None:
        return response.status_code >= 500 or response.status_code == 429
    return False


async def _request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    retryable: bool = True,
    **kwargs,
) -> httpx.Response:
    last_exc: httpx.HTTPError | None = None

    for attempt in range(settings.META_API_RETRIES):
        try:
            response = await client.request(method, url, **kwargs)
            if retryable and _should_retry(response=response) and attempt < settings.META_API_RETRIES - 1:
                await asyncio.sleep(settings.META_API_RETRY_DELAY_MS / 1000)
                continue
            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            last_exc = exc
            if not retryable or not _should_retry(exc=exc) or attempt == settings.META_API_RETRIES - 1:
                raise
            await asyncio.sleep(settings.META_API_RETRY_DELAY_MS / 1000)

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Meta API request failed without a response")


async def exchange_code_for_token(
    client: httpx.AsyncClient,
    code: str,
    app_id: str,
    app_secret: str,
    api_version: str,
) -> str:
    """Exchange OAuth authorization code for an access token."""
    response = await _request_with_retry(
        client,
        "GET",
        f"https://graph.facebook.com/{api_version}/oauth/access_token",
        retryable=False,
        params={"client_id": app_id, "client_secret": app_secret, "code": code},
    )
    return response.json()["access_token"]


async def get_waba_details(
    client: httpx.AsyncClient,
    waba_id: str,
    token: str,
    api_version: str,
) -> dict:
    """Fetch WABA details (business name, etc.)."""
    response = await _request_with_retry(
        client,
        "GET",
        f"https://graph.facebook.com/{api_version}/{waba_id}",
        params={"fields": "name,currency,timezone_id", "access_token": token},
    )
    return response.json()


async def register_phone_number(
    client: httpx.AsyncClient,
    phone_number_id: str,
    token: str,
    pin: str,
    api_version: str,
) -> None:
    """Register a phone number for WhatsApp Cloud API."""
    await _request_with_retry(
        client,
        "POST",
        f"https://graph.facebook.com/{api_version}/{phone_number_id}/register",
        headers={"Authorization": f"Bearer {token}"},
        json={"messaging_product": "whatsapp", "pin": pin},
    )


async def subscribe_app_to_waba(
    client: httpx.AsyncClient,
    waba_id: str,
    token: str,
    api_version: str,
) -> None:
    """Subscribe the app to a WABA to receive webhook events."""
    await _request_with_retry(
        client,
        "POST",
        f"https://graph.facebook.com/{api_version}/{waba_id}/subscribed_apps",
        headers={"Authorization": f"Bearer {token}"},
    )


async def get_waba_phone_numbers(
    client: httpx.AsyncClient,
    waba_id: str,
    token: str,
    api_version: str,
) -> list[dict]:
    """Return phone number objects associated with a WABA (for coexistence onboarding)."""
    response = await _request_with_retry(
        client,
        "GET",
        f"https://graph.facebook.com/{api_version}/{waba_id}/phone_numbers",
        params={"access_token": token},
    )
    return response.json().get("data", [])


async def subscribe_coexistence_fields(
    client: httpx.AsyncClient,
    waba_id: str,
    token: str,
    api_version: str,
) -> None:
    """Subscribe extra webhook fields required for coexistence mode."""
    for field in ("history", "smb_app_state_sync", "smb_message_echoes"):
        await _request_with_retry(
            client,
            "POST",
            f"https://graph.facebook.com/{api_version}/{waba_id}/subscribed_apps",
            headers={"Authorization": f"Bearer {token}"},
            params={"subscribed_fields": field},
        )


async def trigger_smb_sync(
    client: httpx.AsyncClient,
    phone_number_id: str,
    token: str,
    sync_type: str,
    api_version: str,
) -> None:
    """Trigger contact or history sync for a coexistence number. Must run within 24hs of onboarding."""
    await _request_with_retry(
        client,
        "POST",
        f"https://graph.facebook.com/{api_version}/{phone_number_id}/smb_app_data",
        headers={"Authorization": f"Bearer {token}"},
        json={"messaging_product": "whatsapp", "sync_type": sync_type},
    )


async def send_whatsapp_message(
    client: httpx.AsyncClient,
    phone_number_id: str,
    to: str,
    text: str,
    token: str,
    api_version: str,
) -> str:
    """Send a text message via WhatsApp Cloud API. Returns Meta's message ID."""
    response = await _request_with_retry(
        client,
        "POST",
        f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text},
        },
    )
    return response.json()["messages"][0]["id"]


async def get_media_url(
    client: httpx.AsyncClient,
    media_id: str,
    token: str,
    api_version: str,
) -> dict:
    """Return Meta media metadata, including the temporary download URL."""
    response = await _request_with_retry(
        client,
        "GET",
        f"https://graph.facebook.com/{api_version}/{media_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    return response.json()


async def download_media_to_path(
    client: httpx.AsyncClient,
    media_id: str,
    token: str,
    api_version: str,
    destination: Path,
) -> dict:
    """Download one WhatsApp media object to destination and return metadata."""
    media = await get_media_url(client, media_id, token, api_version)
    url = media.get("url")
    if not url:
        raise RuntimeError(f"Meta media {media_id} did not include a download URL")

    response = await _request_with_retry(
        client,
        "GET",
        url,
        headers={"Authorization": f"Bearer {token}"},
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(response.content)
    return {
        "media_id": media_id,
        "path": str(destination),
        "mime_type": media.get("mime_type") or response.headers.get("content-type"),
        "size": len(response.content),
    }
