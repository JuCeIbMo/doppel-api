---
name: catalogo-productos
description: Presenta el catálogo de productos al cliente de forma clara. Usa list_available_products y count_available_products para responder consultas sobre precios, disponibilidad y opciones.
metadata:
  version: "1.0.0"
  tags: ["catalogo", "productos", "precios", "cliente"]
---

# Catálogo de Productos Skill

Usa esta skill cuando el cliente pregunte por productos, precios o disponibilidad.

## Cuándo usar

- "¿Qué tienen?", "¿Cuál es su menú/catálogo?"
- "¿Cuánto cuesta X?"
- "¿Tienen Y disponible?"
- "¿Cuántos productos tienen?"

## Tools disponibles

| Tool | Cuándo llamarla |
|---|---|
| `list_available_products` | Para mostrar el catálogo completo o buscar un producto |
| `count_available_products` | Solo cuando el cliente pregunta cuántos productos hay |
| `lookup_business_info` | Para obtener info del negocio si el cliente pregunta horarios, dirección, pagos |

## Cómo presentar el catálogo

**No** listes todos los productos en un bloque de texto plano — es difícil de leer en WhatsApp.

**Sí** usa este formato por producto:
```
🔸 *Nombre* — $precio
   Descripción breve
```

Si hay más de 5 productos, agrúpalos por categoría si existe. Si hay más de 10, sugiere al cliente que te diga qué busca para filtrar.

## Consultas de precio

Si el cliente pregunta por un producto específico:
1. Llama `list_available_products`
2. Filtra mentalmente por nombre
3. Responde con nombre, precio y descripción breve

Si no está disponible, dilo claramente:
> "En este momento ese producto no está disponible. ¿Te puedo ayudar con algo más del catálogo?"

## Reglas

- Solo muestra productos con `available: true` (la tool ya los filtra)
- Nunca inventes precios — usa siempre el valor de la tool
- Si el catálogo está vacío, informa que no hay productos disponibles en este momento
