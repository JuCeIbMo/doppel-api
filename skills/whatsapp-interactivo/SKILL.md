---
name: whatsapp-interactivo
description: Usa mensajes interactivos de WhatsApp (botones, listas, imágenes, ubicación) para mejorar la experiencia. Cuándo usar cada formato y cómo estructurarlos.
metadata:
  version: "1.0.0"
  tags: ["whatsapp", "interactivo", "botones", "listas", "imagen"]
---

# WhatsApp Interactivo Skill

Usa esta skill cuando puedas mejorar la respuesta con un formato interactivo de WhatsApp en lugar de solo texto plano.

## Tools disponibles

| Tool | Límites | Cuándo usarla |
|---|---|---|
| `send_reply_buttons` | Máx 3 botones, título ≤ 20 chars | Confirmar una acción, elegir entre pocas opciones |
| `send_list_message` | Máx 10 secciones, 10 filas total | Mostrar catálogo, menú, lista de opciones largas |
| `send_image` | URL pública o media_id | Mostrar foto de un producto |
| `send_location` | lat, lng, nombre, dirección | Dar la ubicación del negocio |
| `send_document` | URL pública o media_id | Enviar PDF, factura, menú en archivo |
| `send_reaction` | emoji + message_id | Confirmar recibo de un mensaje del cliente |

## Cuándo usar cada formato

### Botones de respuesta (`send_reply_buttons`)
Úsalos cuando el cliente tiene entre 2 y 3 opciones claras:
- "¿Cómo quieres pagar?" → [Efectivo] [Tarjeta] [Transferencia]
- "¿Confirmamos la venta?" → [Sí, confirmar] [No, cancelar]

### Lista interactiva (`send_list_message`)
Úsala para catálogos, menús o cuando hay más de 3 opciones:
- Mostrar categorías de productos
- Opciones de horario para una reserva

### Imagen (`send_image`)
Envíala cuando el cliente pregunta cómo es un producto y tienes `image_url` en el catálogo.

### Ubicación (`send_location`)
Envíala cuando el cliente pregunta dónde están o cómo llegar.
Obtén lat/lng de `lookup_business_info` → campo `address` si tiene coordenadas, o pide las coordenadas al sistema.

## Reglas importantes

- Después de enviar un mensaje interactivo con una tool, tu respuesta de texto debe ser breve o vacía — el mensaje interactivo ya comunica lo necesario
- `send_text_message` está deshabilitada — el texto de tu respuesta final lo envía el sistema automáticamente
- Los botones e IDs deben ser únicos en el mensaje
- Títulos de botones: máximo 20 caracteres

## Ejemplo: mostrar catálogo como lista

```python
send_list_message(
    body_text="Aquí tienes nuestro catálogo:",
    button_text="Ver opciones",
    sections=[
        {
            "title": "Bebidas",
            "rows": [
                {"id": "prod-1", "title": "Café americano", "description": "$3.50"},
                {"id": "prod-2", "title": "Jugo de naranja", "description": "$4.00"},
            ]
        }
    ]
)
```
