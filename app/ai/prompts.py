"""Selección del prompt según el modo (client vs manager)."""

from __future__ import annotations


def select_prompt(config: dict, mode: str) -> str:
    if mode == "manager" and config.get("manager_prompt"):
        return str(config["manager_prompt"])
    return str(config.get("system_prompt") or "")
