---
name: whatsapp-interactivo
description: Usa mensajes interactivos de WhatsApp (botones, listas, imágenes) para mejorar la experiencia. Cuándo usar cada formato y cómo estructurarlos.
metadata:
  version: "2.0.0"
  tags: ["whatsapp", "interactivo", "botones", "listas", "imagen"]
---

# WhatsApp Interactivo Skill

Usa esta skill cuando puedas mejorar la respuesta con un formato interactivo de WhatsApp en lugar de solo texto plano.

Estas tools **no consultan ni escriben nada**: le piden a WhatsApp que mande un mensaje
aparte. El texto de tu respuesta final lo envía el sistema por su cuenta.

## Tools disponibles

| Tool | Límites | Cuándo usarla |
|---|---|---|
| `send_reply_buttons` | Máx 3 opciones, `label` ≤ 20 chars | Confirmar una acción, elegir entre pocas opciones |
| `send_list_message` | Máx 10 secciones y 10 filas en total | Mostrar catálogo, menú, lista de opciones largas |
| `send_image` | Recibe `product_id`, no una URL | Mostrar la foto de un producto |

Las reacciones con emoji, las tildes azules y el "escribiendo…" **no son tools**: el canal
los maneja solo, por reglas (`app/ai_core/channel/courtesy.py`). No los pidas.

## Cuándo usar cada formato

### Botones de respuesta (`send_reply_buttons`)
Cuando el cliente tiene entre 2 y 3 opciones claras:
- "¿Cómo querés pagar?" → [Efectivo] [Tarjeta] [Transferencia]
- "¿Confirmamos la venta?" → [Sí, confirmar] [No, cancelar]

Cada opción lleva un `label` (lo que el cliente lee) y un `value` (un id corto que vas a
reconocer cuando lo toque). Cuando el cliente toca un botón, te llega como su próximo
mensaje.

### Lista interactiva (`send_list_message`)
Para catálogos, menús o cuando hay más de 3 opciones. El nombre va en `title` (≤24 chars) y
el precio en `description` (≤72).

### Imagen (`send_image`)
Cuando el cliente pregunta cómo es un producto. Le pasás el `product_id` que te devolvió
`search_catalog`; **el canal resuelve la foto**. Si el producto no tiene, la tool devuelve
`ok: false` con `reason: "no_image"`: describilo en palabras y no menciones que falló nada.

## Reglas importantes

- **Nunca escribas una URL, un link ni un `product_id` en tu texto.** La foto la manda el
  canal como mensaje aparte.
- Después de mandar un mensaje interactivo, tu texto tiene que ser breve: **no repitas las
  opciones en palabras**, el cliente ya las ve.
- Como máximo **un** mensaje interactivo por turno. Nunca `send_reply_buttons` y
  `send_list_message` en el mismo turno.
- Los ids de botones y filas deben ser únicos dentro del mensaje.
- Si mandás más opciones de las que permite WhatsApp, la tool devuelve `ok: false` con el
  motivo en vez de recortar en silencio: mandá menos opciones y volvé a intentar.

## Ejemplo: mostrar catálogo como lista

```python
send_list_message(
    body="Aquí tienes nuestro catálogo:",
    button_label="Ver opciones",
    sections=[
        {
            "title": "Bebidas",
            "rows": [
                {"title": "Café americano", "value": "prod-1", "description": "$3.50"},
                {"title": "Jugo de naranja", "value": "prod-2", "description": "$4.00"},
            ],
        }
    ],
)
```

## Ejemplo: ofrecer opciones

```python
send_reply_buttons(
    body="¿Cómo preferís pagar?",
    options=[
        {"label": "Efectivo", "value": "cash"},
        {"label": "Transferencia", "value": "transfer"},
    ],
)
```
