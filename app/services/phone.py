"""Normalización de números de teléfono (extraído de manager_tools)."""

from __future__ import annotations

import re

_NON_DIGITS = re.compile(r"\D+")


def normalize_phone(raw: str | None) -> str:
    """Strip everything that isn't a digit. Matches the format Meta sends in webhooks
    (`from` field is digits only, no leading '+'). Empty result means invalid input.
    """
    return _NON_DIGITS.sub("", raw or "")
