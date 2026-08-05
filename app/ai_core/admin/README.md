# Agente administrativo

Este paquete es el punto reservado para desarrollar el agente admin sin mezclarlo con el
router ni con los especialistas públicos.

- `agent.py`: construcción y ejecución de un turno admin.
- `tools.py`: inventario explícito de capacidades habilitadas.
- `prompt.md`: contrato de comportamiento y herramientas visibles para el modelo.

Una capacidad nueva debe implementar primero su regla en la capa ERP, exponer una tool,
sumarla a `ADMIN_TOOLS` y actualizar el prompt y sus pruebas. No se registra desde
`bridge.py`: el bridge sólo resuelve el rol y llama a este paquete.
