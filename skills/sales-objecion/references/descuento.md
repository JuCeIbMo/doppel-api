# Objeción / Pedido: "¿Me podés hacer un descuento?"

Es objeción y pedido a la vez. El cliente está interesado (no pediría descuento
si no le interesara) pero el precio le pesa. Tu respuesta depende del config.

## Si `descuento_maximo > 0`

**Primero escuchá el número del cliente**, no ofrezcas el descuento de entrada.

> "Veo qué puedo hacer — ¿qué precio tenías en mente?"

Posibles respuestas:

### Dentro del margen (descuento ≤ descuento_maximo)

Aceptá directo:
> "Dale, podemos hacer [precio que pidió]. ¿Lo coordinamos?"

Pasás a cierre inmediatamente.

### Fuera del margen (el cliente pide más descuento del permitido)

Ofrecé el máximo una sola vez, marcando que es el tope:
> "Hasta [precio con descuento máximo] te puedo hacer. Es lo máximo que
> manejo. ¿Con eso estamos?"

Si insiste: mantenete. Negociar más allá del máximo destruye margen y
acostumbra al cliente a regatear más en futuras compras.

> "Es el tope que tengo. Si te suma, lo coordinamos; si no, lo entiendo."

### El cliente no da un número específico

> "Decime qué tenés en mente y veo qué puedo hacer."

No ofrezcas descuento sin que dé un anchor — perdés margen innecesario.

## Si `descuento_maximo: 0`

Precio fijo. Decilo con convicción, sin disculparte:

> "Los precios acá son fijos — lo que sí te puedo decir es qué incluye ese
> precio y por qué vale lo que vale."

Si insiste:
> "Entiendo, pero no manejo descuentos. Lo que sí te puedo ofrecer es
> [valor agregado real del config si existe: cuotas, envío, garantía].
> Si el precio es lo definitivo, te entiendo perfecto también."

## Anti-patrones críticos

- **Nunca prometas un descuento "preguntando al jefe"** si no existe esa
  posibilidad real. Es excusa típica que destruye credibilidad.
- **Nunca ofrezcas descuento que no esté en el config** aunque suene razonable.
  El sistema anti-alucinación cubre también descuentos inventados.
- **Nunca ofrezcas un descuento la primera vez que mencionan precio.** Esperar
  a que pidan descuento explícito.

## Una vez que el descuento se cierra

Pasá a cierre inmediatamente. No sigas negociando. No agregués extras. El
precio final acordado es el precio final.
