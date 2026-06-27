"""Subsistema de IA. Única puerta de entrada para el resto del backend.

`respond` enruta entre el bridge productivo (Agno) y el spike (Pydantic AI) según
el flag AI_PYDANTIC_SPIKE. El spike solo cubre el modo `client`; el `manager`
siempre cae en Agno (el propio spike lo delega).
"""

from app.ai.bridge import respond as _agno_respond
from app.ai.config import PYDANTIC_SPIKE


async def respond(**kwargs):
    if PYDANTIC_SPIKE:
        from app.ai.pydantic_spike import respond as _spike_respond

        return await _spike_respond(**kwargs)
    return await _agno_respond(**kwargs)


__all__ = ["respond"]
