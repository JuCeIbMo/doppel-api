"""Subida de imágenes de productos a Supabase Storage.

Reusa el cliente service_role (`get_supabase`), que escribe ignorando RLS. El bucket
es público de lectura, así que la URL devuelta puede ir directa al front y al catálogo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import uuid4

from app.config import settings
from app.services.supabase_client import get_supabase

logger = logging.getLogger("doppel.storage")


@dataclass(frozen=True, slots=True)
class UploadedProductImage:
    path: str
    url: str


async def upload_product_image(tenant_id: str, data: bytes) -> str:
    """Sube `data` (WebP) al bucket de productos y devuelve su URL pública.

    El path se scopea por tenant: `{tenant_id}/{uuid}.webp`.
    """
    return (await upload_product_image_asset(tenant_id, data)).url


async def upload_product_image_asset(tenant_id: str, data: bytes) -> UploadedProductImage:
    """Upload a WebP and retain its path so callers can compensate on failure."""
    path = f"{tenant_id}/{uuid4().hex}.webp"
    bucket = get_supabase().storage.from_(settings.PRODUCT_IMAGES_BUCKET)
    await bucket.upload(path, data, {"content-type": "image/webp", "upsert": "false"})
    try:
        url = await bucket.get_public_url(path)
    except Exception:
        # The object already exists at this point. Do not leak it if resolving
        # its URL fails before the caller receives the path.
        try:
            await bucket.remove([path])
        except Exception:
            logger.exception("failed to remove orphan product image path=%s", path)
        raise
    return UploadedProductImage(path=path, url=url)


async def delete_product_image(path: str) -> None:
    """Delete one product image by Storage path."""
    bucket = get_supabase().storage.from_(settings.PRODUCT_IMAGES_BUCKET)
    await bucket.remove([path])
