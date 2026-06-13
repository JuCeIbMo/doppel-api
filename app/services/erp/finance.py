"""Finance service: transactions and cash accounts.

Balances are never written here — inserting a transaction fires a DB trigger that
updates `cash_accounts.balance`. Sales generate their income transaction inside the
`create_sale` RPC; this module covers manual income/expense and account management.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from app.services.erp.context import ERPContext, log_activity
from app.services.erp.exceptions import NotFound
from app.services.supabase_client import get_supabase

EXPENSE_CATEGORIES = [
    "Compras de mercadería", "Sueldos", "Alquiler", "Servicios",
    "Transporte", "Marketing", "Otros",
]


class FinanceService:
    # --- transactions ---
    async def list_transactions(self, ctx: ERPContext, *, type: str | None = None,
                                category: str | None = None, account_id: str | None = None,
                                date_from: str | None = None, date_to: str | None = None,
                                limit: int = 50, offset: int = 0) -> list[dict]:
        q = (
            get_supabase().table("transactions").select("*")
            .eq("tenant_id", ctx.tenant_id).order("date", desc=True)
        )
        if type:
            q = q.eq("type", type)
        if category:
            q = q.eq("category", category)
        if account_id:
            q = q.eq("cash_account_id", account_id)
        if date_from:
            q = q.gte("date", date_from)
        if date_to:
            q = q.lte("date", date_to)
        return (q.range(offset, offset + limit - 1).execute()).data or []

    async def create_transaction(self, ctx: ERPContext, data: dict[str, Any]) -> dict:
        payload = {
            "tenant_id": ctx.tenant_id,
            "type": data["type"],
            "amount": data["amount"],
            "category": data["category"],
            "description": data.get("description"),
            "cash_account_id": data.get("cash_account_id") or self._default_account_id(ctx),
            "actor": ctx.actor,
        }
        if data.get("date"):
            payload["date"] = data["date"].isoformat() if isinstance(data["date"], date) else data["date"]
        row = (get_supabase().table("transactions").insert(payload).execute()).data[0]
        log_activity(ctx, action=f"transaction.{data['type']}", module="finance",
                     detail={"amount": data["amount"], "category": data["category"]})
        return row

    async def categories(self, ctx: ERPContext) -> list[str]:
        rows = (
            get_supabase().table("transactions").select("category")
            .eq("tenant_id", ctx.tenant_id).execute()
        ).data or []
        used = {r["category"] for r in rows if r.get("category")}
        return sorted(used | set(EXPENSE_CATEGORIES))

    # --- accounts ---
    def _default_account_id(self, ctx: ERPContext) -> str | None:
        rows = (
            get_supabase().table("cash_accounts").select("id")
            .eq("tenant_id", ctx.tenant_id).eq("is_active", True)
            .order("is_default", desc=True).limit(1).execute()
        ).data
        return rows[0]["id"] if rows else None

    async def list_accounts(self, ctx: ERPContext) -> list[dict]:
        return (
            get_supabase().table("cash_accounts")
            .select("id, name, type, balance, is_default, is_active")
            .eq("tenant_id", ctx.tenant_id).order("created_at").execute()
        ).data or []

    async def create_account(self, ctx: ERPContext, data: dict[str, Any]) -> dict:
        if data.get("is_default"):
            self._clear_default(ctx)
        payload = {**data, "tenant_id": ctx.tenant_id}
        row = (get_supabase().table("cash_accounts").insert(payload).execute()).data[0]
        log_activity(ctx, action="account.created", module="finance",
                     detail={"account_id": row["id"], "name": row["name"]})
        return row

    async def update_account(self, ctx: ERPContext, account_id: str, data: dict[str, Any]) -> dict:
        clean = {k: v for k, v in data.items() if v is not None}
        if clean.get("is_default"):
            self._clear_default(ctx)
        rows = (
            get_supabase().table("cash_accounts").update(clean)
            .eq("tenant_id", ctx.tenant_id).eq("id", account_id).execute()
        ).data
        if not rows:
            raise NotFound("Caja no encontrada", account_id=account_id)
        return rows[0]

    def _clear_default(self, ctx: ERPContext) -> None:
        # Only one default per tenant (enforced by a partial unique index); unset the old one first.
        (
            get_supabase().table("cash_accounts").update({"is_default": False})
            .eq("tenant_id", ctx.tenant_id).eq("is_default", True).execute()
        )

    # --- cashflow ---
    async def cashflow(self, ctx: ERPContext, *, date_from: str, date_to: str,
                       group_by: str = "day") -> dict:
        rows = (
            get_supabase().table("transactions").select("type, amount, date")
            .eq("tenant_id", ctx.tenant_id).gte("date", date_from).lte("date", date_to)
            .execute()
        ).data or []

        def bucket(d: str) -> str:
            if group_by == "month":
                return d[:7]
            if group_by == "week":
                iso = date.fromisoformat(d).isocalendar()
                return f"{iso.year}-W{iso.week:02d}"
            return d  # day

        series: dict[str, dict[str, float]] = defaultdict(lambda: {"income": 0.0, "expense": 0.0})
        income = expense = 0.0
        for r in rows:
            amt = float(r["amount"])
            series[bucket(r["date"])][r["type"]] += amt
            if r["type"] == "income":
                income += amt
            else:
                expense += amt
        return {
            "from": date_from, "to": date_to, "group_by": group_by,
            "income": round(income, 2), "expense": round(expense, 2),
            "net": round(income - expense, 2),
            "series": [{"period": k, **{kk: round(vv, 2) for kk, vv in v.items()}}
                       for k, v in sorted(series.items())],
        }
