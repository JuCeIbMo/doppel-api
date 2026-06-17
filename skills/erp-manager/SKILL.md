---
name: erp-manager
description: Gestión del negocio vía WhatsApp para el administrador. Cubre ventas, stock, reportes y clientes usando las tools ERP disponibles.
metadata:
  version: "1.0.0"
  tags: ["erp", "ventas", "inventario", "reportes"]
---

# ERP Manager Skill

Usa esta skill cuando el administrador pregunte por ventas, stock, reportes, clientes o quiera registrar una venta.

## Cuándo usar

- Preguntas sobre ventas del día/semana/mes
- Consultas de stock o productos con bajo inventario
- Registrar una venta por WhatsApp
- Ver productos más vendidos
- Ajustar stock tras un conteo físico

## Tools disponibles

| Tool | Cuándo llamarla |
|---|---|
| `get_dashboard_summary` | Resumen general del negocio (ventas, margen, caja) |
| `get_stock` | Ver stock actual, filtrar por producto o stock bajo |
| `get_top_products` | Ranking de productos más vendidos |
| `create_sale` | Registrar una venta (baja stock de forma atómica) |
| `adjust_stock` | Corregir el stock tras un conteo físico |

## Flujo para registrar una venta

1. Pide los productos y cantidades si el admin no los especificó
2. Confirma el total antes de registrar (calcula precio × cantidad)
3. Llama `create_sale` con los ítems y método de pago
4. Si falla por `insufficient_stock`, informa exactamente cuál producto no tiene stock
5. Confirma el registro con el total y el ID de la venta

## Flujo para consultar reportes

- Si el admin dice "hoy", usa `period="today"`
- Si dice "esta semana", usa `period="week"`
- Si dice "este mes" o no especifica, usa `period="month"`
- Para rangos específicos usa `period="custom"` con `date_from` y `date_to` en `YYYY-MM-DD`

## Reglas de negocio importantes

- `create_sale` es atómica: si falla, NADA se guarda — no hay ventas parciales
- `adjust_stock` recibe la cantidad REAL contada, no el delta
- El `payment_method` por defecto es `cash` si el admin no especifica
- Si el cliente paga por WhatsApp, usa `payment_method="whatsapp"`
