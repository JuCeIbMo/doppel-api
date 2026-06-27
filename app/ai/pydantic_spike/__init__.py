"""Spike: client agent reimplementado con Pydantic AI, en paralelo a Agno.

Aislado en su propio paquete para poder compararlo contra `app/ai/` sin tocar el
camino productivo. El `bridge` real enruta acá solo cuando AI_PYDANTIC_SPIKE=true.
Expone la misma interfaz pública que `app.ai`: `respond`.
"""

from __future__ import annotations

from app.ai.pydantic_spike.bridge import respond

__all__ = ["respond"]
