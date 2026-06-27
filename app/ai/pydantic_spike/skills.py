"""Carga de skills como texto plano para inyectar en las instructions.

Agno tiene un loader nativo (`LocalSkills`); Pydantic AI no. Acá lo resolvemos
de la forma más simple: leemos el cuerpo de cada `SKILL.md` (sin frontmatter) y
lo concatenamos al system prompt.

NOTA spike: esto carga todas las skills en cada turno, igual que hace hoy Agno.
El upgrade natural sería carga on-demand (capabilities con defer_loading), pero
para comparar 1:1 mantenemos el mismo comportamiento eager.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_SKILLS_DIR = Path(__file__).parent.parent.parent.parent / "skills"


def _strip_frontmatter(text: str) -> str:
    """Quita el bloque YAML `--- ... ---` del inicio si existe."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4 :].lstrip("\n")
    return text


@lru_cache(maxsize=None)
def _load_skill_body(name: str) -> str:
    path = _SKILLS_DIR / name / "SKILL.md"
    if not path.exists():
        return ""
    return _strip_frontmatter(path.read_text(encoding="utf-8")).strip()


def load_skills_text(*names: str) -> str:
    """Concatena los cuerpos de las skills pedidas, separados por encabezados."""
    blocks: list[str] = []
    for name in names:
        body = _load_skill_body(name)
        if body:
            blocks.append(f"# Skill: {name}\n\n{body}")
    return "\n\n---\n\n".join(blocks)
