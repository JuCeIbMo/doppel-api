# doppel-api

API multi-tenant para el ERP de Doppel y sus agentes de WhatsApp. La estructura está
ordenada por responsabilidad: los routers sólo traducen HTTP, los módulos de dominio
ejecutan el caso de uso y `ai_core` contiene exclusivamente la lógica de agentes.

## Por dónde empezar

Para seguir un mensaje entrante, este es el hilo principal:

```text
POST /webhook/whatsapp
  app/routers/webhook.py          verifica firma y delega
  app/whatsapp/webhook.py         identifica tenant, deduplica y agenda el turno
  app/whatsapp/turn.py            descarga adjuntos y coordina la respuesta
  app/ai_core/bridge.py           elige agente público o admin
  app/ai_core/public/agent.py     router + especialista público
  app/ai_core/admin/agent.py      agente administrativo
  app/whatsapp/delivery.py        prepara las acciones de salida
  app/whatsapp/sender.py          envía a Meta Cloud API
```

Para seguir una operación del dashboard:

```text
app/routers/erp/<dominio>.py
  app/services/erp/<dominio>.py
  Supabase
```

## Mapa del código

```text
app/
├── routers/              fronteras HTTP; validan y delegan
│   └── erp/              endpoints por dominio del ERP
├── services/
│   ├── erp/              reglas y persistencia del ERP
│   ├── storefront.py     fachada reducida del ERP para el agente público
│   └── images/storage/vision.py
├── whatsapp/             integración completa con Meta y ciclo de cada mensaje
│   ├── onboarding.py     Embedded Signup/OAuth y sincronización inicial
│   ├── webhook.py        ingestión, tenant, deduplicación y scheduling
│   ├── inbound.py        normalización y descarga de adjuntos
│   ├── turn.py           coordinación WhatsApp ↔ agentes
│   ├── delivery.py       plan de entrega de texto/acciones
│   ├── sender.py         transporte de salida
│   └── meta.py           llamadas a Meta Cloud API
└── ai_core/
    ├── bridge.py         única entrada al subsistema de agentes
    ├── public/           router y cuatro especialistas de ventas
    ├── admin/            agente administrativo y registro de capacidades
    ├── common/           LLM, prompts y middleware compartido
    ├── tools/            implementaciones de tools (se conserva su runtime actual)
    ├── channel/          acciones puras y outbox por turno
    ├── config/           contrato y carga de configuración por tenant
    ├── persistence/      checkpointer de LangGraph
    └── observability/    tracing y Langfuse
```

`app/ai_core/public` no es un swarm. Es un router que clasifica cada turno y ejecuta
uno de cuatro especialistas: `greeter`, `catalog`, `objection` o `closer`. No hay
handoffs ni conversaciones autónomas entre especialistas.

## Dónde agregar una función

| Necesidad | Lugar principal |
|---|---|
| Endpoint o contrato HTTP | `app/routers/` |
| Regla del ERP | `app/services/erp/` |
| Lectura/acción comercial para el bot público | `app/services/storefront.py` y `app/ai_core/tools/` |
| Capacidad del agente admin | `app/ai_core/admin/tools.py` |
| Prompt público | `app/ai_core/public/prompts/` |
| Prompt admin | `app/ai_core/admin/prompt.md` |
| Parseo o entrega de WhatsApp | `app/whatsapp/` |
| Acción de canal nueva | modelo en `app/ai_core/channel/`, ejecución en `app/whatsapp/` |

### Agente admin

El espacio del admin ya es explícito y no depende del agente público. Para agregar una
capacidad:

1. Implementar la operación de negocio en ERP y su tool en `app/ai_core/tools/`.
2. Registrar la tool en `ADMIN_TOOLS`, en `app/ai_core/admin/tools.py`.
3. Documentar su uso en `app/ai_core/admin/prompt.md`.
4. Agregar la prueba de contrato prompt/tool en `tests/test_prompt_tool_sync.py` y una
   prueba funcional de la operación.

La lista `ADMIN_TOOLS` es el inventario real del admin; revisar ese archivo responde qué
puede hacer hoy sin rastrear imports por todo el repositorio.

## Desarrollo

```bash
python3 -m pytest tests/ -q
uvicorn app.main:app --reload
```

`tests/conftest.py` carga las variables seguras comunes. Las pruebas HTTP están separadas
por dominio (`test_auth_api.py`, `test_oauth.py`, `test_dashboard.py`, `test_webhook.py`) y
los dobles reutilizables viven en `tests/fakes/`.

Los documentos que describen implementaciones antiguas están en `docs/archive/`; sirven
como historial y no como guía del código actual. Las decisiones vigentes del agente están
en `docs/ai-core-pendientes.md`.
