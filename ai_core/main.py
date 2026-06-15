import logging
from contextlib import asynccontextmanager

import httpx
from agno.media import Image
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
    # `runtime` + `echo` + `model` let you confirm WHICH image is live: if this
    # endpoint lacks these fields, the container is running a stale build.
    return {
        "status": "ok",
        "service": "ai-core",
        "runtime": "agno-gemini",
        "echo": settings.AI_CORE_ECHO,
        "model": settings.AI_CORE_GEMINI_MODEL,
    }


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
    files: list[UploadFile] | None = File(default=None),
    authorization: str | None = Header(default=None),
):
    _require_internal_token(authorization)

    # The conversation history is no longer sent by the API: Agno owns it via
    # the per-user session (session_id) persisted in Postgres.
    images: list[Image] = []
    for upload in files or []:
        if (upload.content_type or "").startswith("image/"):
            images.append(Image(content=await upload.read()))

    if files:
        logger.info(
            "Received media files tenant=%s mode=%s count=%s images=%s",
            tenant_id,
            mode,
            len(files),
            len(images),
        )

    return await respond(
        app.state.http_client,
        tenant_id=tenant_id,
        mode=mode,
        sender_id=sender_id,
        content=content,
        system_prompt=system_prompt,
        model=model,
        images=images or None,
    )
