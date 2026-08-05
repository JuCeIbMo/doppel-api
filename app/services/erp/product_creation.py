"""Single-operation product creation with one required primary image."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.services.erp.context import ERPContext
from app.services.erp.products import ProductsService
from app.services.images import optimize_image
from app.services.storage import delete_product_image, upload_product_image_asset
from app.services.vision import analyze_product_image

logger = logging.getLogger("doppel.erp.product_creation")


def _merge_tags(manual: list[str] | None, generated: list[str] | None) -> list[str]:
    merged: list[str] = []
    for value in [*(manual or []), *(generated or [])]:
        tag = value.strip().lower()
        if tag and tag not in merged:
            merged.append(tag)
        if len(merged) == 20:
            break
    return merged


class ProductCreationService:
    """Orchestrate image processing, Storage and the existing product insert.

    Storage and Postgres cannot share a transaction. The image is therefore
    uploaded first and deleted if the database insert fails.
    """

    def __init__(self, products: ProductsService | None = None) -> None:
        self.products = products or ProductsService()

    async def create(
        self,
        ctx: ERPContext,
        product_data: dict[str, Any],
        raw_image: bytes,
    ) -> dict:
        optimized = await asyncio.to_thread(optimize_image, raw_image)

        upload_task = upload_product_image_asset(ctx.tenant_id, optimized)
        analysis_task = analyze_product_image(
            optimized,
            "image/webp",
            hint=product_data.get("name"),
        )
        upload_result, analysis_result = await asyncio.gather(
            upload_task,
            analysis_task,
            return_exceptions=True,
        )

        if isinstance(upload_result, BaseException):
            raise upload_result

        if isinstance(analysis_result, BaseException):
            logger.error(
                "unexpected image analysis failure tenant=%s",
                ctx.tenant_id,
                exc_info=(
                    type(analysis_result),
                    analysis_result,
                    analysis_result.__traceback__,
                ),
            )
            analysis: dict[str, Any] = {
                "ai_ok": False,
                "name": None,
                "description": None,
                "tags": [],
            }
        else:
            analysis = analysis_result

        payload = dict(product_data)
        payload["image_url"] = upload_result.url
        if not (payload.get("description") or "").strip() and analysis.get("description"):
            payload["description"] = analysis["description"]
        payload["tags"] = _merge_tags(payload.get("tags"), analysis.get("tags"))

        try:
            product = await self.products.create(ctx, payload)
        except Exception:
            try:
                await delete_product_image(upload_result.path)
            except Exception:
                logger.exception(
                    "failed to rollback product image path=%s tenant=%s",
                    upload_result.path,
                    ctx.tenant_id,
                )
            raise

        # Useful to clients without exposing Gemini internals as a second flow.
        product["has_image"] = True
        product["image_analysis_ok"] = bool(analysis.get("ai_ok"))
        return product
