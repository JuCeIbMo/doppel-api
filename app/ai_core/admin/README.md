# Agente administrativo

Este paquete es el punto reservado para desarrollar el agente admin sin mezclarlo con el
router ni con los especialistas públicos.

- `agent.py`: construcción y ejecución de un turno admin.
- `tools.py`: inventario explícito de capacidades habilitadas.
- `prompt.md`: contrato de comportamiento y herramientas visibles para el modelo.

Las consultas de negocio reutilizan los services ERP existentes. Las escrituras no se
exponen directamente: se proponen como una acción persistente y el dueño debe tocar
Confirmar en WhatsApp. El bridge valida ese tap y sólo ese turno puede ejecutar la
acción; así texto libre, reintentos y conversaciones ajenas no modifican el ERP.

Una capacidad nueva debe implementar primero su regla en la capa ERP, exponer una tool,
sumarla a `ADMIN_TOOLS` y actualizar el prompt y sus pruebas. No se registra desde
`bridge.py`: el bridge sólo resuelve el rol, valida confirmaciones y llama a este paquete.
