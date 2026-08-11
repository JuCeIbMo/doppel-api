"""Text rendering grammar for admin tool outputs.

Pure, no I/O. `app/services/admin_view.py` fetches and trims lean dicts; this
module turns them into the compact text the model actually returns to the
owner over WhatsApp. Kept separate on purpose: `admin_view` is tested with
fakes, this is tested with plain dicts, and swapping the output format back to
JSON later only touches this one layer.

Every list a tool can return is already capped by `admin_view`; the primitives
here only render what they're given plus the "+N más" tail when there's more.
"""

from __future__ import annotations

LABELS = {
    "sale": "venta",
    "adjustment_in": "ajuste +",
    "adjustment_out": "ajuste -",
    "purchase": "compra",
    "income": "ingreso",
    "expense": "gasto",
    "completed": "completada",
    "cancelled": "cancelada",
}


def label(value: str | None) -> str:
    return LABELS.get(value, value or "")


def row(*parts: object) -> str:
    """Join parts with ` · `, dropping empty ones so nulls disappear without an
    `if` per field."""
    return " · ".join(str(p) for p in parts if p not in (None, ""))


def section(title: str, rows: list[str], *, empty: str = "sin datos", extra: int = 0) -> str:
    """Header with a count; an empty section says so explicitly instead of
    vanishing, because silence is what makes the model invent data."""
    if not rows:
        return f"{title}: {empty}"
    lines = [f"{title} ({len(rows)})"] + [f"- {r}" for r in rows]
    if extra > 0:
        lines.append(f"… +{extra} más (acotá el rango o la búsqueda)")
    return "\n".join(lines)


def doc(*sections: str) -> str:
    return "\n\n".join(s for s in sections if s)


def money(x: float | int | None) -> str:
    if x is None:
        return "0 Bs"
    x = float(x)
    n = int(x) if x == int(x) else round(x, 2)
    return f"{n} Bs"


def qty(x: float | int | None) -> str:
    if x is None:
        return "0"
    x = float(x)
    return str(int(x)) if x == int(x) else str(round(x, 3))


def when(iso: str | None) -> str:
    if not iso:
        return ""
    d, t = iso[:10], iso[11:16]
    return f"{d[8:10]}/{d[5:7]} {t}"


def day(iso: str | None) -> str:
    if not iso:
        return ""
    d = iso[:10]
    return f"{d[8:10]}/{d[5:7]}"


def period(date_from: str, date_to: str) -> str:
    return f"{day(date_from)} → {day(date_to)}"


def ref(uuid: str | None) -> str:
    return f"id {uuid}" if uuid else ""


# --------------------------------------------------------------------------
# render_* por tool
# --------------------------------------------------------------------------


def business_overview(data: dict) -> str:
    p = data["period"]
    top = data.get("top_product")
    lines = [
        f"NEGOCIO ({period(p['from'], p['to'])})",
        row(f"Ventas: {money(data['sales_total'])} ({data['sales_count']})",
            f"Margen: {money(data['gross_margin'])} ({data['gross_margin_pct']}%)"),
        row(f"Clientes nuevos: {data['new_clients']}", f"Bajo mínimo: {data['low_stock_count']}"),
    ]
    if top:
        lines.append(f"Top: {top['name']} · {qty(top['units_sold'])} u")
    balances = row(*[f"{a['name']} {money(a['balance'])}" for a in data.get("cash_balances", [])])
    if balances:
        lines.append(f"Caja: {balances}")
    return "\n".join(lines)


def sales_analysis(data: dict) -> str:
    p = data["period"]
    margin = data["margin"]
    top_rows = [row(t["product_name"], f"{qty(t['units'])} u", money(t["revenue"]))
                for t in data["top_products"]]
    trend_rows = [row(day(t["period"]), money(t["total"]), f"{t['count']} ventas")
                  for t in data["trend"]]
    margin_rows = [row(m["product_name"], money(m["revenue"]),
                        f"margen {money(m['margin'])} ({m['margin_pct']}%)")
                   for m in margin["by_product"]]
    header = f"ANÁLISIS ({period(p['from'], p['to'])})"
    return "\n\n".join([header, doc(
        section("TOP PRODUCTOS", top_rows),
        section("TENDENCIA", trend_rows),
        section(f"MARGEN {money(margin['gross_margin'])} ({margin['gross_margin_pct']}%)", margin_rows),
    )])


def inventory_alerts(data: dict) -> str:
    low_rows = [
        row(r["product_name"], f"{qty(r['quantity'])} de {qty(r['threshold'])} {r['unit']}", ref(r["product_id"]))
        for r in data["low_stock"]
    ]
    move_rows = [
        row(when(m["when"]), label(m["type"]), f"{m['product_name']} ×{qty(m['quantity'])}")
        for m in data["movements"]
    ]
    return doc(
        section("FALTANTES", low_rows, empty="sin faltantes", extra=data.get("low_stock_extra", 0)),
        section("MOVIMIENTOS RECIENTES", move_rows, extra=data.get("movements_extra", 0)),
    )


def find_customers(data: dict) -> str:
    rows = [
        row(c["name"], c["phone"], f"{c['purchase_count']} compras", money(c["total_purchases"]),
            f"última {day(c['last_purchase_at'])}" if c.get("last_purchase_at") else "",
            ref(c["id"]))
        for c in data["items"]
    ]
    return section("CLIENTES", rows, empty="sin resultados", extra=data.get("extra", 0))


def customer_details(data: dict) -> str:
    c = data["customer"]
    header = row(c["name"], c["phone"], f"{c['purchase_count']} compras", money(c["total_purchases"]))
    sale_rows = [row(when(s["created_at"]), money(s["total"]), label(s["status"])) for s in data["recent_sales"]]
    return doc(header, section("ÚLTIMAS VENTAS", sale_rows))


def recent_sales(data: dict) -> str:
    rows = [
        row(when(s["created_at"]), money(s["total"]), label(s["status"]), s.get("payment_method"), ref(s["id"]))
        for s in data["items"]
    ]
    return section("VENTAS", rows, empty="sin ventas", extra=data.get("extra", 0))


def sale_details(data: dict) -> str:
    s = data["sale"]
    header = row(when(s["created_at"]), label(s["status"]), s.get("payment_method"), money(s["total"]))
    item_rows = [row(f"{i['product_name']} ×{qty(i['quantity'])}", money(i["total"])) for i in data["items"]]
    return doc(header, section("ÍTEMS", item_rows))


def cash_summary(data: dict) -> str:
    p = data["period"]
    account_rows = [row(a["name"], money(a["balance"])) for a in data["accounts"]]
    flow = data["cashflow"]
    flow_line = row(f"Ingresos: {money(flow['income'])}", f"Egresos: {money(flow['expense'])}",
                     f"Neto: {money(flow['net'])}")
    tx_rows = [
        row(day(t["date"]), label(t["type"]), t.get("category"), money(t["amount"]))
        for t in data["transactions"]
    ]
    return doc(
        f"CAJA ({period(p['from'], p['to'])})",
        section("CUENTAS", account_rows),
        flow_line,
        section("MOVIMIENTOS", tx_rows, extra=data.get("transactions_extra", 0)),
    )


def propose(description: str) -> str:
    return f"Propuesta pendiente: {description}. Botones enviados; esperá que el dueño toque Confirmar."


_EXECUTED_MESSAGES = {
    "stock_adjustment": lambda payload: f"stock de {payload['product_name']} quedó en {qty(payload['quantity'])}",
    "product_create": lambda payload: f"se creó el producto {payload['label']}",
    "product_update": lambda payload: f"se actualizó {payload['label']}",
    "product_deactivate": lambda payload: f"se desactivó {payload['label']}",
    "transaction": lambda payload: f"se registró {label(payload['type'])} de {money(payload['amount'])} en {payload['category']}",
    "sale_cancellation": lambda payload: f"la venta por {money(payload['total'])} quedó cancelada",
}


def execute_confirmed_action(kind: str, payload: dict, *, duplicate: bool) -> str:
    describe = _EXECUTED_MESSAGES.get(kind)
    detail = describe(payload) if describe else f"se ejecutó {kind}"
    prefix = "Ya estaba ejecutada" if duplicate else "Hecho"
    return f"{prefix}: {detail}."
