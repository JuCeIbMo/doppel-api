# Pendientes vigentes de `app/ai_core`

Este archivo contiene únicamente trabajo todavía abierto. El diagnóstico y las
correcciones de la migración Agno → LangChain/LangGraph están archivados en
`docs/archive/ai-core-revision-2026-07.md`.

## Soporte de imágenes entrantes

El bot todavía no interpreta imágenes recibidas por WhatsApp. El bridge detecta
el adjunto y pide al cliente que describa lo que busca. El audio sí se transcribe.

Antes de implementarlo hay que definir qué proveedor de visión usará el bot y
qué límites de tamaño, privacidad y retención se aplicarán a esos adjuntos.
