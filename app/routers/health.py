from fastapi import APIRouter

from app.models.schemas import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def health():
    return {"status": "ok", "service": "doppel-api"}
