"""Reports service. Aggregations are scoped by date so the working set stays small
(a shop's month is hundreds of rows, not millions). Queries filter on the joined
`sales` row so only completed, in-period sales count.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from app.services.erp.context import ERPContext
from app.services.erp.finance import FinanceService
from app.services.erp.inventory import InventoryService
from app.services.supabase_client import get_supabase


def default_period(date_from: str | None, date_to: str | None) -> tuple[str, str]:
    today = date.today()
    return (date_from or today.replace(day=1).isoformat(), date_to or today.isoformat())


def _sale_items_in_period(tenant_id: str, date_from: str, date_to: str) -> list[dict]:
    return (
        get_supabase().table("sale_items")
        .select("product_id, product_name, quantity, unit_price, unit_cost, total, "
                "products(category), sales!inner(status, created_at, client_id)")
        .eq("tenant_id", tenant_id)
        .eq("sales.status", "completed")
        .gte("sales.created_at", date_from)
        .lte("sales.created_at", f"{date_to}T23:59:59")
        .execute()
    ).data or []


def _margin_of(item: dict) -> float:
    return (float(item["unit_price"]) - float(item["unit_cost"])) * float(item["quantity"])


class ReportsService:
    def __init__(self) -> None:
        self.inventory = InventoryService()
        self.finance = FinanceService()

    async def dashboard(self, ctx: ERPContext, *, date_from: str, date_to: str) -> dict:
        items = _sale_items_in_period(ctx.tenant_id, date_from, date_to)

        sales = (
            get_supabase().table("sales").select("id, total")
            .eq("tenant_id", ctx.tenant_id).eq("status", "completed")
            .gte("created_at", date_from).lte("created_at", f"{date_to}T23:59:59").execute()
        ).data or []
        sales_total = round(sum(float(s["total"]) for s in sales), 2)
        sales_count = len(sales)

        gross_margin = round(sum(_margin_of(i) for i in items), 2)
        revenue = round(sum(float(i["total"]) for i in items), 2)
        margin_pct = round((gross_margin / revenue * 100) if revenue else 0, 1)

        new_clients = (
            get_supabase().table("clients").select("id", count="exact")
            .eq("tenant_id", ctx.tenant_id)
            .gte("created_at", date_from).lte("created_at", f"{date_to}T23:59:59").execute()
        ).count or 0

        units: dict[str, float] = defaultdict(float)
        for i in items:
            units[i["product_name"]] += float(i["quantity"])
        top_product = None
        if units:
            name, qty = max(units.items(), key=lambda kv: kv[1])
            top_product = {"name": name, "units_sold": qty}

        accounts = await self.finance.list_accounts(ctx)
        low_stock = await self.inventory.low_stock(ctx)

        return {
            "period": {"from": date_from, "to": date_to},
            "sales_total": sales_total,
            "sales_count": sales_count,
            "gross_margin": gross_margin,
            "gross_margin_pct": margin_pct,
            "new_clients": new_clients,
            "low_stock_count": len(low_stock),
            "top_product": top_product,
            "cash_balances": [{"name": a["name"], "balance": float(a["balance"])} for a in accounts],
        }

    async def top_products(self, ctx: ERPContext, *, date_from: str, date_to: str,
                           limit: int = 5) -> list[dict]:
        items = _sale_items_in_period(ctx.tenant_id, date_from, date_to)
        agg: dict[str, dict] = {}
        for i in items:
            a = agg.setdefault(i["product_name"], {"product_name": i["product_name"], "units": 0.0, "revenue": 0.0})
            a["units"] += float(i["quantity"])
            a["revenue"] += float(i["total"])
        ranked = sorted(agg.values(), key=lambda x: x["revenue"], reverse=True)
        for r in ranked:
            r["units"] = round(r["units"], 3)
            r["revenue"] = round(r["revenue"], 2)
        return ranked[:limit]

    async def sales_by_period(self, ctx: ERPContext, *, date_from: str, date_to: str,
                              group_by: str = "day") -> list[dict]:
        sales = (
            get_supabase().table("sales").select("total, created_at")
            .eq("tenant_id", ctx.tenant_id).eq("status", "completed")
            .gte("created_at", date_from).lte("created_at", f"{date_to}T23:59:59").execute()
        ).data or []

        def bucket(ts: str) -> str:
            d = ts[:10]
            if group_by == "month":
                return d[:7]
            if group_by == "week":
                iso = date.fromisoformat(d).isocalendar()
                return f"{iso.year}-W{iso.week:02d}"
            return d

        agg: dict[str, dict] = defaultdict(lambda: {"total": 0.0, "count": 0})
        for s in sales:
            b = agg[bucket(s["created_at"])]
            b["total"] += float(s["total"])
            b["count"] += 1
        return [{"period": k, "total": round(v["total"], 2), "count": v["count"]}
                for k, v in sorted(agg.items())]

    async def margin(self, ctx: ERPContext, *, date_from: str, date_to: str) -> dict:
        items = _sale_items_in_period(ctx.tenant_id, date_from, date_to)
        by_product: dict[str, dict] = {}
        by_category: dict[str, dict] = defaultdict(lambda: {"revenue": 0.0, "margin": 0.0})
        for i in items:
            m = _margin_of(i)
            rev = float(i["total"])
            p = by_product.setdefault(i["product_name"], {"product_name": i["product_name"], "revenue": 0.0, "margin": 0.0})
            p["revenue"] += rev
            p["margin"] += m
            cat = (i.get("products") or {}).get("category") or "Sin categoría"
            by_category[cat]["revenue"] += rev
            by_category[cat]["margin"] += m

        def finalize(d: dict) -> dict:
            d["revenue"] = round(d["revenue"], 2)
            d["margin"] = round(d["margin"], 2)
            d["margin_pct"] = round((d["margin"] / d["revenue"] * 100) if d["revenue"] else 0, 1)
            return d

        gross_margin = round(sum(_margin_of(i) for i in items), 2)
        revenue = sum(float(i["total"]) for i in items)
        gross_margin_pct = round((gross_margin / revenue * 100) if revenue else 0, 1)

        return {
            "gross_margin": gross_margin,
            "gross_margin_pct": gross_margin_pct,
            "by_product": [finalize(p) for p in sorted(by_product.values(), key=lambda x: x["margin"], reverse=True)],
            "by_category": [finalize({"category": k, **v}) for k, v in by_category.items()],
        }

    async def clients(self, ctx: ERPContext, *, date_from: str, date_to: str) -> dict:
        sales = (
            get_supabase().table("sales").select("client_id, total")
            .eq("tenant_id", ctx.tenant_id).eq("status", "completed")
            .gte("created_at", date_from).lte("created_at", f"{date_to}T23:59:59").execute()
        ).data or []
        new_clients = (
            get_supabase().table("clients").select("id", count="exact")
            .eq("tenant_id", ctx.tenant_id)
            .gte("created_at", date_from).lte("created_at", f"{date_to}T23:59:59").execute()
        ).count or 0

        spend: dict[str, float] = defaultdict(float)
        for s in sales:
            if s.get("client_id"):
                spend[s["client_id"]] += float(s["total"])

        # Returning = bought in-period AND has at least one completed sale before the period.
        returning_clients = 0
        if spend:
            prior = (
                get_supabase().table("sales").select("client_id")
                .eq("tenant_id", ctx.tenant_id).eq("status", "completed")
                .in_("client_id", list(spend.keys()))
                .lt("created_at", date_from).execute()
            ).data or []
            returning_clients = len({r["client_id"] for r in prior if r.get("client_id")})

        top_ids = sorted(spend.items(), key=lambda kv: kv[1], reverse=True)[:5]
        top = []
        if top_ids:
            rows = (
                get_supabase().table("clients").select("id, name")
                .eq("tenant_id", ctx.tenant_id).in_("id", [cid for cid, _ in top_ids]).execute()
            ).data or []
            names = {r["id"]: r["name"] for r in rows}
            top = [{"client_id": cid, "name": names.get(cid, "—"), "spent": round(total, 2)}
                   for cid, total in top_ids]
        return {
            "period": {"from": date_from, "to": date_to},
            "new_clients": new_clients,
            "returning_clients": returning_clients,
            "buyers": len(spend),
            "top_clients": top,
        }
