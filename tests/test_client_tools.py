import asyncio

from app.ai.tools.client_tools import build_client_tools


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows
    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def execute(self):
        rows = self._rows
        class R:
            data = rows
            count = len(rows)
        return R()


class _FakeSupabase:
    def __init__(self, rows):
        self._rows = rows
    def table(self, _name):
        return _FakeQuery(self._rows)


def test_build_client_tools_returns_callables():
    tools = build_client_tools(_FakeSupabase([]), "t1")
    assert all(callable(t) for t in tools)
    assert {t.__name__ for t in tools} == {
        "lookup_business_info",
        "list_available_products",
        "count_available_products",
    }


def test_list_available_products_returns_rows():
    rows = [{"name": "Pizza", "price": 10, "available": True}]
    tools = build_client_tools(_FakeSupabase(rows), "t1")
    list_products = next(t for t in tools if t.__name__ == "list_available_products")
    assert asyncio.run(list_products()) == rows


def test_count_available_products_returns_total():
    rows = [
        {"name": "Pizza", "price": 10, "available": True},
        {"name": "Pasta", "price": 8, "available": True},
    ]
    tools = build_client_tools(_FakeSupabase(rows), "t1")
    count_tool = next(t for t in tools if t.__name__ == "count_available_products")
    assert asyncio.run(count_tool()) == {"total": 2}


def test_count_available_products_empty():
    tools = build_client_tools(_FakeSupabase([]), "t1")
    count_tool = next(t for t in tools if t.__name__ == "count_available_products")
    assert asyncio.run(count_tool()) == {"total": 0}
