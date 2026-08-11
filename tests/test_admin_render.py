"""Unit tests for the admin text-rendering grammar (app/ai_core/tools/render.py).

Pure, no I/O: these only exercise the primitives against plain dicts, not the
ERP-backed `admin_view` layer (covered separately by test_admin_tool_payloads.py).
"""

from app.ai_core.tools import render


def test_row_drops_empty_parts():
    """Nulls disappear without an `if` per field."""
    assert render.row("Cerveza", None, "", "22 u", 0) == "Cerveza · 22 u · 0"


def test_row_all_empty_is_empty_string():
    assert render.row(None, "", None) == ""


def test_section_renders_empty_explicitly():
    """A silent empty section is what makes the model invent data."""
    assert render.section("FALTANTES", []) == "FALTANTES: sin datos"
    assert render.section("FALTANTES", [], empty="sin faltantes") == "FALTANTES: sin faltantes"


def test_section_counts_and_lists_rows():
    text = render.section("VENTAS", ["a", "b"])
    assert text == "VENTAS (2)\n- a\n- b"


def test_section_adds_cut_tail_when_extra():
    text = render.section("VENTAS", ["a"], extra=5)
    assert text.endswith("… +5 más (acotá el rango o la búsqueda)")


def test_section_no_tail_without_extra():
    text = render.section("VENTAS", ["a"], extra=0)
    assert "más" not in text


def test_money_drops_trailing_zero():
    assert render.money(2.0) == "2 Bs"
    assert render.money(2.5) == "2.5 Bs"
    assert render.money(None) == "0 Bs"


def test_qty_drops_trailing_zero():
    assert render.qty(22.0) == "22"
    assert render.qty(1.5) == "1.5"
    assert render.qty(None) == "0"


def test_when_formats_microseconds_and_offset():
    """Real inventory_movements timestamps look like this."""
    assert render.when("2026-06-17T09:38:53.471743+00:00") == "17/06 09:38"


def test_day_formats_a_bare_date():
    assert render.day("2026-06-17") == "17/06"


def test_period_formats_a_range():
    assert render.period("2026-06-01", "2026-06-17") == "01/06 → 17/06"


def test_ref_prefixes_the_id():
    assert render.ref("a1000001-0000-0000-0000-000000000001") == "id a1000001-0000-0000-0000-000000000001"
    assert render.ref(None) == ""


def test_label_translates_known_enums():
    assert render.label("adjustment_in") == "ajuste +"
    assert render.label("completed") == "completada"


def test_label_passes_through_unknown_values():
    assert render.label("weird_enum") == "weird_enum"


def test_doc_joins_sections_with_blank_line():
    assert render.doc("a", "b") == "a\n\nb"


def test_doc_skips_empty_sections():
    assert render.doc("a", "", "b") == "a\n\nb"


def test_propose_message():
    assert render.propose("Ajustar stock de Cerveza Paceña a 22") == (
        "Propuesta pendiente: Ajustar stock de Cerveza Paceña a 22. "
        "Botones enviados; esperá que el dueño toque Confirmar."
    )


def test_execute_confirmed_action_stock_adjustment():
    text = render.execute_confirmed_action(
        "stock_adjustment", {"product_name": "Cerveza Paceña", "quantity": 22}, duplicate=False)
    assert text == "Hecho: stock de Cerveza Paceña quedó en 22."


def test_execute_confirmed_action_duplicate():
    text = render.execute_confirmed_action(
        "stock_adjustment", {"product_name": "Cerveza Paceña", "quantity": 22}, duplicate=True)
    assert text.startswith("Ya estaba ejecutada:")
