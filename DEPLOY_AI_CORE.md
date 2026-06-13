# Deploy `doppel-api` + `ai-core`

## Objetivo

Dejar `doppel-api` como borde del producto y `ai-core` como servicio interno separado,
con Postgres propio, sin que `ai-core` toque Supabase ni Meta directamente.

## Servicios

- `doppel-api`
  - Dockerfile: `Dockerfile`
  - Puerto interno: `8000`
- `ai-core`
  - Dockerfile: `Dockerfile.ai-core`
  - Puerto interno: `8000`
- `ai-core-postgres`
  - Imagen: `pgvector/pgvector:pg17`

## Variables mínimas

### `doppel-api`

- `META_APP_ID`
- `META_APP_SECRET`
- `META_VERIFY_TOKEN`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`
- `ENCRYPTION_KEY`
- `AI_CORE_URL=http://ai-core:8000`
- `AI_CORE_TOKEN=<secreto-compartido-con-ai-core>`
- `DOPPEL_INTERNAL_API_TOKEN=<secreto-para-tools-internas>`

### `ai-core`

- `AI_CORE_API_TOKEN=<mismo-valor-de-AI_CORE_TOKEN>`
- `DOPPEL_API_URL=http://doppel-api:8000`
- `DOPPEL_INTERNAL_API_TOKEN=<mismo-valor-de-DOPPEL_INTERNAL_API_TOKEN>`
- `AI_CORE_DB_URL=postgresql://ai:ai@ai-core-postgres:5432/ai_core`
- `ANTHROPIC_API_KEY=<opcional-por-ahora>`

## Dokploy

### Opción 1: Compose

- Usar `compose.ai-core.yaml`
- Cargar las variables del `.env`

### Opción 2: Servicios separados

Crear 3 servicios:

1. `doppel-api`
   - build context: repo actual
   - dockerfile: `Dockerfile`
2. `ai-core`
   - build context: repo actual
   - dockerfile: `Dockerfile.ai-core`
3. `ai-core-postgres`
   - imagen: `pgvector/pgvector:pg17`

Poner a `doppel-api` y `ai-core` en la misma red privada.

## Estado actual del `ai-core`

- Ya recibe turnos desde Doppel por `POST /internal/doppel/turn`
- Ya puede pedir tools internas a Doppel:
  - `GET /internal/ai/tools`
  - `POST /internal/ai/tools/execute`
- Ya tiene su token interno separado
- Ya tiene su Postgres propio previsto por env y compose

Lo que falta a propósito:

- montar la implementación real de Agno/AgentOS
- persistir sesiones/memoria en `AI_CORE_DB_URL`
- definir knowledge/memory específicos
