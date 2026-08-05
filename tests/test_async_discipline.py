"""Architectural guard: no blocking I/O inside `async def`.

This is the rule the LangChain migration was built on, enforced instead of
documented. It exists because the failure mode is invisible: a synchronous
Supabase call inside an `async def` works perfectly in tests and in manual
QA — it only shows up in production as the whole event loop (FastAPI, the
WhatsApp webhook, every concurrent conversation) stalling for the duration of
each round-trip, while the type signature claims otherwise.

Two invariants, checked over the real AST of `app/`:

1. Every Supabase call is awaited. Forgetting `await` yields a coroutine, and
   the `.data` access after it raises AttributeError — loud, but only on the
   code path that runs. This catches it everywhere at once.
2. No Supabase call sits in a plain `def`. A sync helper doing network I/O is
   exactly how the blocking crept in before: it looks harmless at the call site.
"""

import ast
import pathlib

import pytest

APP = pathlib.Path(__file__).resolve().parent.parent / "app"

# Terminal calls that hit the network on the Supabase async client.
DB_CALLS = {"execute"}
AUTH_STORAGE_CALLS = {
    "upload", "get_public_url", "get_user", "sign_in_with_otp",
    "verify_otp", "refresh_session", "sign_out",
}

def _python_files():
    return sorted(APP.rglob("*.py"))

def _supabase_calls(path):
    """Yield (node, parents, enclosing_func, source) for each Supabase I/O call."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        attr = node.func.attr
        if attr in DB_CALLS:
            pass
        elif attr in AUTH_STORAGE_CALLS:
            # These names are generic; only count them on a Supabase chain.
            segment = ast.get_source_segment(src, node) or ""
            if "supabase" not in segment.lower():
                continue
        else:
            continue

        enclosing = None
        cur = node
        while cur in parents:
            cur = parents[cur]
            if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                enclosing = cur
                break
        yield node, parents, enclosing, src

@pytest.mark.parametrize("path", _python_files(), ids=lambda p: str(p.name))
def test_supabase_calls_are_awaited(path):
    offenders = [
        f"{path.name}:{node.lineno}  {(ast.get_source_segment(src, node) or '')[:70]}"
        for node, parents, _enclosing, src in _supabase_calls(path)
        if not isinstance(parents.get(node), ast.Await)
    ]
    assert not offenders, "Supabase I/O without `await`:\n" + "\n".join(offenders)

@pytest.mark.parametrize("path", _python_files(), ids=lambda p: str(p.name))
def test_supabase_calls_are_not_in_sync_functions(path):
    offenders = [
        f"{path.name}:{node.lineno}  inside `def {enclosing.name}(...)`"
        for node, _parents, enclosing, _src in _supabase_calls(path)
        if isinstance(enclosing, ast.FunctionDef)
    ]
    assert not offenders, "Supabase I/O in a sync function:\n" + "\n".join(offenders)

def test_guard_actually_sees_the_calls():
    """A guard that matches nothing would pass forever; make sure it has teeth."""
    total = sum(len(list(_supabase_calls(p))) for p in _python_files())
    assert total > 80, f"expected the full Supabase surface, only found {total}"
