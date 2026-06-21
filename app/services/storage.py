"""Subida de imágenes de productos a Supabase Storage.

Reusa el cliente service_role (`get_supabase`), que escribe ignorando RLS. El bucket
es público de lectura, así que la URL devuelta puede ir directa al front y al catálogo.
"""

from __future__ import annotations

from uuid import uuid4

from app.config import settings
from app.services.supabase_client import get_supabase


def upload_product_image(tenant_id: str, data: bytes) -> str:
    """Sube `data` (WebP) al bucket de productos y devuelve su URL pública.

    El path se scopea por tenant: `{tenant_id}/{uuid}.webp`.
    """
    path = f"{tenant_id}/{uuid4().hex}.webp"
    bucket = get_supabase().storage.from_(settings.PRODUCT_IMAGES_BUCKET)
    bucket.upload(path, data, {"content-type": "image/webp", "upsert": "true"})
    return bucket.get_public_url(path)
