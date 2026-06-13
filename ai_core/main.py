import json
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile, status

from ai_core.config import settings
from ai_core.contracts import TurnResponse
from ai_core.runtime import respond

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("ai-core")


def _require_internal_token(authorization: str | None) -> None:
    if not settings.AI_CORE_API_TOKEN:
        return
    expected = f"Bearer {settings.AI_CORE_API_TOKEN}"
    if authorization != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid AI core token",
            headers={"WWW-Authenticate": "Bearer"},
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient(timeout=30.0)
    logger.info("ai-core started")
    yield
    await app.state.http_client.aclose()
    logger.info("ai-core stopped")


app = FastAPI(
    title="Doppel AI Core",
    version="1.0.0",
    description="Internal runtime service for Doppel agent execution.",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ai-core"}


@app.post("/internal/doppel/turn", response_model=TurnResponse)
async def handle_turn(
    tenant_id: str = Form(...),
    mode: str = Form(...),
    sender_id: str = Form(...),
    chat_id: str = Form(...),
    message_id: str = Form(""),
    content: str = Form(""),
    system_prompt: str = Form(...),
    model: str = Form(...),
    conversation: str = Form("[]"),
    files: list[UploadFile] | None = File(default=None),
    authorization: str | None = Header(default=None),
):
    _require_internal_token(authorization)
    try:
        parsed_conversation = json.loads(conversation)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid conversation payload",
        ) from exc

    if files:
        logger.info(
            "Received media files tenant=%s mode=%s count=%s",
            tenant_id,
            mode,
            len(files),
        )

    return await respond(
        app.state.http_client,
        tenant_id=tenant_id,
        mode=mode,
        sender_id=sender_id,
        content=content,
        conversation=parsed_conversation,
        system_prompt=system_prompt,
        model=model,
    )
