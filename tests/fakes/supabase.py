"""Implementación mínima en memoria del query builder asíncrono de Supabase."""

class FakeResult:
    def __init__(self, data=None, count=None):
        self.data = data
        self.count = count

class FakeTableQuery:
    def __init__(self, table_name, store):
        self.table_name = table_name
        self.store = store
        self.filters = []
        self._insert_payload = None
        self._update_payload = None
        self._delete_mode = False
        self._single = False
        self._count = None
        self._range = None
        self._limit = None

    def select(self, _fields, count=None):
        self._count = count
        return self

    def eq(self, key, value):
        self.filters.append(lambda row, key=key, value=value: row.get(key) == value)
        return self

    def gte(self, key, value):
        self.filters.append(lambda row, key=key, value=value: row.get(key) >= value)
        return self

    def order(self, key, desc=False):
        self._order_key = key
        self._order_desc = desc
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def limit(self, limit):
        self._limit = limit
        return self

    def single(self):
        self._single = True
        return self

    def maybe_single(self):
        self._single = True
        return self

    def insert(self, payload):
        self._insert_payload = payload
        return self

    def upsert(self, payload, on_conflict=None):
        self._insert_payload = payload
        self._upsert = on_conflict
        return self

    def update(self, payload):
        self._update_payload = payload
        return self

    def delete(self):
        self._delete_mode = True
        return self

    async def execute(self):
        table = self.store.setdefault(self.table_name, [])

        if self._insert_payload is not None:
            payload = dict(self._insert_payload)
            payload.setdefault("id", f"{self.table_name}-{len(table) + 1}")
            payload.setdefault("created_at", f"9999-12-31T23:59:{len(table) + 1:02d}Z")
            table.append(payload)
            return FakeResult([payload])

        rows = [row for row in table if all(check(row) for check in self.filters)]

        if self._update_payload is not None:
            updated = []
            for row in rows:
                row.update(self._update_payload)
                updated.append(dict(row))
            return FakeResult(updated)

        if self._delete_mode:
            self.store[self.table_name] = [row for row in table if row not in rows]
            return FakeResult(rows)

        if hasattr(self, "_order_key"):
            rows = sorted(rows, key=lambda item: item.get(self._order_key, ""), reverse=self._order_desc)

        if self._range is not None:
            start, end = self._range
            rows = rows[start : end + 1]

        if self._limit is not None:
            rows = rows[: self._limit]

        count = len(rows) if self._count == "exact" else None
        if self._single:
            return FakeResult(rows[0] if rows else None, count=count)
        return FakeResult(rows, count=count)

class FakeSupabase:
    def __init__(self, store=None):
        self.store = store or {}

    def table(self, name):
        return FakeTableQuery(name, self.store)

class StrictFilteredMutation:
    """Builder filtrado realista: permite ``eq``/``execute``, no ``select``."""

    def __init__(self, query):
        self.query = query

    def eq(self, key, value):
        self.query.eq(key, value)
        return self

    async def execute(self):
        return await self.query.execute()

class StrictMutationQuery(FakeTableQuery):
    def update(self, payload):
        super().update(payload)
        return self

    def eq(self, key, value):
        super().eq(key, value)
        if self._update_payload is not None:
            return StrictFilteredMutation(self)
        return self

class StrictSupabase(FakeSupabase):
    def table(self, name):
        return StrictMutationQuery(name, self.store)
