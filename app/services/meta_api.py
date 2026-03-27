import httpx


async def exchange_code_for_token(
    client: httpx.AsyncClient,
    code: str,
    app_id: str,
    app_secret: str,
    api_version: str,
) -> str:
    """Exchange OAuth authorization code for an access token."""
    response = await client.get(
        f"https://graph.facebook.com/{api_version}/oauth/access_token",
        params={"client_id": app_id, "client_secret": app_secret, "code": code},
    )
    response.raise_for_status()
    return response.json()["access_token"]


async def get_waba_details(
    client: httpx.AsyncClient,
    waba_id: str,
    token: str,
    api_version: str,
) -> dict:
    """Fetch WABA details (business name, etc.)."""
    response = await client.get(
        f"https://graph.facebook.com/{api_version}/{waba_id}",
        params={"fields": "name,currency,timezone_id", "access_token": token},
    )
    response.raise_for_status()
    return response.json()


async def register_phone_number(
    client: httpx.AsyncClient,
    phone_number_id: str,
    token: str,
    pin: str,
    api_version: str,
) -> None:
    """Register a phone number for WhatsApp Cloud API."""
    response = await client.post(
        f"https://graph.facebook.com/{api_version}/{phone_number_id}/register",
        headers={"Authorization": f"Bearer {token}"},
        json={"messaging_product": "whatsapp", "pin": pin},
    )
    response.raise_for_status()


async def subscribe_app_to_waba(
    client: httpx.AsyncClient,
    waba_id: str,
    token: str,
    api_version: str,
) -> None:
    """Subscribe the app to a WABA to receive webhook events."""
    response = await client.post(
        f"https://graph.facebook.com/{api_version}/{waba_id}/subscribed_apps",
        headers={"Authorization": f"Bearer {token}"},
    )
    response.raise_for_status()


async def send_whatsapp_message(
    client: httpx.AsyncClient,
    phone_number_id: str,
    to: str,
    text: str,
    token: str,
    api_version: str,
) -> str:
    """Send a text message via WhatsApp Cloud API. Returns Meta's message ID."""
    response = await client.post(
        f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text},
        },
    )
    response.raise_for_status()
    return response.json()["messages"][0]["id"]
