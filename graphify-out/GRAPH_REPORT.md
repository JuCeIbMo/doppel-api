# Graph Report - doppel-api  (2026-08-11)

## Corpus Check
- 166 files · ~81,318 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1544 nodes · 3687 edges · 88 communities (79 shown, 9 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 191 edges (avg confidence: 0.68)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `69aadedc`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- dashboard.py
- ToolContextMiddleware
- meta.py
- test_whatsapp_sender.py
- turn.py
- test_ai_core_tools.py
- main.py
- admin.py
- test_ai_core_invariants.py
- test_public_routing.py
- bridge.py
- test_checkpointer_pool.py
- test_turn_outbox.py
- FakeTableQuery
- render.py
- test_admin_tool_payloads.py
- whatsapp/webhook.py
- /graphify SKILL.md pipeline
- admin_view.py
- erp_schemas.py
- routers/erp/sales.py
- routers/erp/products.py
- InventoryService
- TenantConfig
- get_supabase
- test_product_creation.py
- erp/context.py
- actions.py
- test_channel_actions.py
- FakeSupabase
- models.py
- ai_core revision 2026-07 findings
- test_vision.py
- ToolContext
- app/config.py
- test_message_debounce.py
- optimize_image
- dependencies.py
- routers/erp/clients.py
- SalesService
- test_storage.py
- test_middleware.py
- public/agent.py
- Public catalog specialist prompt
- ingest_webhook
- _BizQuery
- WebhookApiTests
- ERPContext
- routers/erp/export.py
- routers/erp/finance.py
- StrictFilteredMutation
- transcription.py
- test_prompt_tool_sync.py
- erp_error_handler
- checkpointer.py
- product_creation.py
- Plan: Storefront Vendedor implementation
- router.py
- Plan: Agno integration into doppel-api
- patch
- test_async_discipline.py
- stock.py
- RequestContextMiddleware
- security.py
- execute_confirmed_action tool
- admin_actions.py
- normalize_phone
- test_auth_dependencies.py
- RequestIdLogFilter
- get_product_image
- search_catalog tool (public catalog)
- routers/webhook.py
- channel/__init__.py
- common/__init__.py
- routers/erp/__init__.py
- services/erp/__init__.py
- whatsapp/__init__.py
- conftest.py
- _offline

## God Nodes (most connected - your core abstractions)
1. `ERPContext` - 132 edges
2. `get_supabase()` - 96 edges
3. `TenantConfig` - 59 edges
4. `ToolContext` - 37 edges
5. `contextual_tool()` - 34 edges
6. `NotFound` - 34 edges
7. `ProductsService` - 30 edges
8. `FakeSupabase` - 28 edges
9. `log_activity()` - 24 edges
10. `FinanceService` - 23 edges

## Surprising Connections (you probably didn't know these)
- `storefront.register_sale (Agno era)` --semantically_similar_to--> `create_order tool`  [INFERRED] [semantically similar]
  docs/archive/superpowers/plans/2026-06-20-storefront-vendedor.md → app/ai_core/public/prompts/closer.md
- `storefront.search_catalog (Agno era)` --semantically_similar_to--> `search_catalog tool (public catalog)`  [INFERRED] [semantically similar]
  docs/archive/superpowers/plans/2026-06-20-storefront-vendedor.md → app/ai_core/public/prompts/catalog.md
- `test_agent_entrypoints_are_async()` --indirect_call--> `build_admin_agent()`  [INFERRED]
  tests/test_ai_core_tools.py → app/ai_core/admin/agent.py
- `ToolThenAnswerModel` --uses--> `SendTextAction`  [INFERRED]
  tests/test_turn_outbox.py → app/ai_core/channel/actions.py
- `WebhookApiTests` --uses--> `SendImageAction`  [INFERRED]
  tests/test_webhook.py → app/ai_core/channel/actions.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **graphify skill documentation set (SKILL.md + reference docs)** — _claude_skills_graphify_skill_pipeline, _claude_skills_graphify_references_add_watch_doc, _claude_skills_graphify_references_exports_doc, _claude_skills_graphify_references_extraction_spec_doc, _claude_skills_graphify_references_github_and_merge_doc, _claude_skills_graphify_references_hooks_doc, _claude_skills_graphify_references_query_doc, _claude_skills_graphify_references_transcribe_doc, _claude_skills_graphify_references_update_doc [EXTRACTED 1.00]
- **doppel-api repo agent contract (AGENTS.md/CLAUDE.md/README.md/.claude/CLAUDE.md)** — agents_doc, claude_doc, readme_doc, _claude_claude_pointer [EXTRACTED 1.00]
- **Catalog -> stock -> order closing sequence** — app_ai_core_public_prompts_catalog_search_catalog, app_ai_core_public_prompts_catalog_check_stock, app_ai_core_public_prompts_closer_create_order [EXTRACTED 1.00]
- **Propose-then-confirm admin write pattern** — app_ai_core_admin_readme_confirmation_gate, app_ai_core_admin_prompt_execute_confirmed_action, app_ai_core_admin_prompt_propose_stock_adjustment [EXTRACTED 0.90]
- **Agno to LangChain/LangGraph migration lifecycle** — docs_archive_superpowers_plans_2026_06_16_agno_integration_doc, docs_archive_ai_core_revision_2026_07_doc, docs_archive_readme_doc [INFERRED 0.85]

## Communities (88 total, 9 thin omitted)

### Community 0 - "dashboard.py"
Cohesion: 0.06
Nodes (71): get_current_user(), Verify Bearer JWT token from Supabase Auth and return the user., AdminPhonesResponse, AdminPhonesUpdateRequest, AiCoreTurnResponse, BotConfigResponse, BotConfigUpdateRequest, BusinessInfoResponse (+63 more)

### Community 1 - "ToolContextMiddleware"
Cohesion: 0.10
Nodes (15): AgentMiddleware, MessageWindowMiddleware, Exception, Return True if the tool's argument schema exposes a ``ctx`` field., Reject tool calls outside the allow-list for the active role., Bound model context while the parent graph keeps full durable history. This…, Convert tool exceptions into structured error messages for the model., Inject the run-scoped ToolContext into tools that accept a ``ctx`` arg.… (+7 more)

### Community 2 - "meta.py"
Cohesion: 0.06
Nodes (68): oauth_exchange(), BackgroundTasks, post, Request, HTTP boundary for WhatsApp Embedded Signup., download_media_to_path(), _error_payload(), exchange_code_for_token() (+60 more)

### Community 3 - "test_whatsapp_sender.py"
Cohesion: 0.08
Nodes (27): AsyncClient, Salida hacia WhatsApp: todo lo que el número del tenant puede *hacer*. Frontera…, Espera lo que tardaría una persona en escribir `text`., Acciones de canal apuntando a un cliente concreto. `inbound_message_id` es el…, Tildes azules y "escribiendo…" sobre el mensaje entrante. Se llama ANTES de…, Reacciona al mensaje entrante. `emoji` vacío quita la reacción., WhatsAppSender, FakeClient (+19 more)

### Community 4 - "turn.py"
Cohesion: 0.19
Nodes (15): cleanup_media_files(), download_media_files(), inbound_message_type(), _media_download_path(), AsyncClient, Path, Best-effort removal of every attachment downloaded for one turn., action_preview() (+7 more)

### Community 5 - "test_ai_core_tools.py"
Cohesion: 0.06
Nodes (53): build_message_window(), _capture_register_sale(), _channel_ctx(), _ctx(), _order_ctx(), parametrize, Regression tests for the LangChain tool wiring in app/ai_core. Covers the two…, `ctx` is injected by middleware, so it must not be in the LLM's schema. (+45 more)

### Community 6 - "main.py"
Cohesion: 0.24
Nodes (10): close_pool(), Release the shared pool. Called from the app lifespan on shutdown., lifespan(), FastAPI, Delete leftover attachments older than `max_age_seconds`. Returns how many.…, Background loop that sweeps orphaned WhatsApp media until cancelled., run_media_reaper(), _sweep_stale_media() (+2 more)

### Community 7 - "admin.py"
Cohesion: 0.11
Nodes (43): The explicit capability registry for the admin agent. Add future admin…, _ctx(), execute_confirmed_action(), find_customers(), get_business_overview(), get_cash_summary(), get_customer_details(), get_inventory_alerts() (+35 more)

### Community 8 - "test_ai_core_invariants.py"
Cohesion: 0.10
Nodes (22): Per-turn operational trace, persisted in doppel-api's existing `activity_log`…, trace_turn(), _truncate(), _ctx(), Invariants of the agent core that nothing else enforces. Each of these was a…, search_catalog + check_stock + create_order., Concurrent turns on one checkpoint mean one message silently vanishes., The lock must be per conversation, not a global bottleneck. (+14 more)

### Community 9 - "test_public_routing.py"
Cohesion: 0.08
Nodes (34): load_tenant_config(), Builds a TenantConfig by reading business_info + bot_configs from Supabase.…, AdminAgentConfig, PublicAgentConfig, BaseModel, Tenant config for the LangChain agent core, backed by Supabase (not YAML).…, build_public_agent(), Build the public turn graph: the router dispatches fresh on every turn. ``START… (+26 more)

### Community 10 - "bridge.py"
Cohesion: 0.12
Nodes (22): _config_fingerprint(), _document_note(), _evict_agent(), _get_or_build_agent(), _image_fallback_note(), Puente entre el webhook y el agente LangGraph. Entrada única por mensaje.…, Serialize turns on one conversation. A customer sending two messages in a row…, Drop a cached agent so the next message rebuilds it from scratch. Without this,… (+14 more)

### Community 11 - "test_checkpointer_pool.py"
Cohesion: 0.13
Nodes (18): Regression tests for the checkpointer pool and the agent-cache eviction. Both…, `.setup()` is idempotent but costs a round trip on every agent build., A pool left open on shutdown leaks server-side Postgres connections., The whole point: a broken agent must not survive into the next message., Eviction must not turn the cache into a per-message rebuild., Otherwise a bot_configs edit never reaches a running process., The fingerprint must cover what is bound, not just the display name., An unbounded cache grows one agent per tenant for the life of the process. (+10 more)

### Community 12 - "test_turn_outbox.py"
Cohesion: 0.10
Nodes (25): ChannelAction, Buffer de acciones de canal de UN turno. Las tools no mandan nada por su…, Acciones encoladas por las tools durante un turno, en orden de encolado., Devuelve lo encolado y vacía el buffer., Lo que se pasa como `context=` al invocar el grafo. Uno nuevo por turno. ⚠️ NO…, TurnOutbox, TurnRuntime, _build_graph() (+17 more)

### Community 13 - "FakeTableQuery"
Cohesion: 0.10
Nodes (4): Dobles reutilizables para pruebas sin servicios externos., FakeResult, FakeTableQuery, Implementación mínima en memoria del query builder asíncrono de Supabase.

### Community 14 - "render.py"
Cohesion: 0.10
Nodes (46): business_overview(), cash_summary(), customer_details(), day(), doc(), execute_confirmed_action(), find_customers(), inventory_alerts() (+38 more)

### Community 15 - "test_admin_tool_payloads.py"
Cohesion: 0.11
Nodes (23): get_sale(), list_sales(), get, Any, _assert_within_budget(), _ctx(), parametrize, Enforcement suite: admin tools must return compact text within a declared… (+15 more)

### Community 16 - "whatsapp/webhook.py"
Cohesion: 0.20
Nodes (10): InteractiveReply, Lo que llega desde el canal y el agente tiene que poder entender. Hoy es sólo…, Un botón o una fila de lista que el cliente tocó., El id sin nuestro namespace. Un id sin el prefijo `choice:` no lo generamos…, Cómo percibe el agente el tap, en el mismo formato que las otras notas., InboundMessage, parse_inbound(), Normalize inbound Meta messages and manage their temporary media files. (+2 more)

### Community 17 - "/graphify SKILL.md pipeline"
Cohesion: 0.10
Nodes (25): .claude/CLAUDE.md — graphify trigger pointer, graphify reference: add-watch, graphify reference: exports and benchmark, graphify reference: extraction subagent prompt spec, graphify reference: GitHub clone and cross-repo merge, graphify reference: commit hook and CLAUDE.md integration, graphify reference: query, path, explain, graphify reference: transcribe video and audio (+17 more)

### Community 18 - "admin_view.py"
Cohesion: 0.13
Nodes (23): clients_report(), dashboard(), margin(), get, Reports endpoints. All accept ?date_from=&date_to= (default = current month)., sales_by_period(), top_products(), business_overview() (+15 more)

### Community 19 - "erp_schemas.py"
Cohesion: 0.24
Nodes (14): AdjustmentRequest, CashAccountResponse, ClientRecentSale, DashboardResponse, InventoryRow, MovementResponse, ProductResponse, BaseModel (+6 more)

### Community 20 - "routers/erp/sales.py"
Cohesion: 0.47
Nodes (5): CreateSaleRequest, cancel_sale(), create_sale(), post, Sales endpoints. Thin: validate, delegate to SalesService (atomic RPCs).

### Community 21 - "routers/erp/products.py"
Cohesion: 0.12
Nodes (23): ProductCreate, ProductUpdate, VariantCreate, add_variant(), create_product(), delete_product(), get_by_barcode(), get_product() (+15 more)

### Community 22 - "InventoryService"
Cohesion: 0.20
Nodes (3): ExportService, Generate a printable barcode label (Code128) for a product without its own code., InventoryService

### Community 23 - "TenantConfig"
Cohesion: 0.16
Nodes (25): build_admin_agent(), Owner-facing administrative agent., build_chat_model(), Centralized DeepSeek chat-model factory. Every agent in the core builds its…, Return the configured model name for a role (env override or default)., Build the chat model for an agent role with sane production defaults. Fails…, resolve_model_name(), build_tool_context() (+17 more)

### Community 24 - "get_supabase"
Cohesion: 0.12
Nodes (16): log_activity(), Append to the audit log. Best-effort: it never raises — a failed log must not…, FinanceService, Any, _current_stock(), Apply a manual stock correction by inserting one adjustment movement. Accepts…, _image_presence_map(), ProductsService (+8 more)

### Community 25 - "test_product_creation.py"
Cohesion: 0.18
Nodes (12): ProductCreationService, Orchestrate image processing, Storage and the existing product insert. Storage…, UploadedProductImage, client(), _patch_pipeline(), _Products, Exception, fixture (+4 more)

### Community 26 - "erp/context.py"
Cohesion: 0.07
Nodes (43): Clients service. Quick creation during a sale (name + phone is enough). The bot…, The shared spine of the ERP: request context, activity logging, RPC helpers.…, ERPError, Forbidden, InsufficientStock, NotFound, Any, Exception (+35 more)

### Community 27 - "actions.py"
Cohesion: 0.12
Nodes (18): ListRow, ListSection, BaseModel, field_validator, Acciones de canal: lo que el agente decide mandar, antes de mandarlo. Pydantic…, Shape exacto que espera Meta para una sección de lista., ReplyButton, SendButtonsAction (+10 more)

### Community 28 - "test_channel_actions.py"
Cohesion: 0.08
Nodes (37): Lo que un turno produce: el texto del agente más lo que encoló el canal.…, SendImageAction, TurnResult, choose_reaction(), _normalize(), Cortesías del canal por reglas: reacción con emoji y pausa de "escribiendo…".…, Minúsculas y sin acentos, para que el match no dependa de cómo escriban., Emoji para reaccionar al mensaje entrante, o None si no aplica ninguno.… (+29 more)

### Community 29 - "FakeSupabase"
Cohesion: 0.32
Nodes (13): _consume_admin_confirmation(), Validate our confirmation buttons before the LLM sees their identifier., AdminActionService, FakeSupabase, _ctx(), test_admin_action_requires_matching_tenant_and_thread(), test_claim_recovers_stuck_executing_action(), test_claim_rejects_recently_stuck_executing_action() (+5 more)

### Community 30 - "models.py"
Cohesion: 0.09
Nodes (33): add_product(), _erp_ctx(), Field, gt, InjectedCtx, min_length, Catalog tools. Body reads/writes doppel-api's real ERP, not SQLite.…, Search available products by name, description and tags. Omit `query` to list… (+25 more)

### Community 31 - "ai_core revision 2026-07 findings"
Cohesion: 0.12
Nodes (18): ai_core pendientes vigentes, Image vision support resolved, Agent cache invalidation by config fingerprint, BOT_ENABLED switch rename, check_stock found-vs-zero-stock distinction, classify_intent -> route_dispatch fixed-depth graph, create_order idempotency fix, ai_core revision 2026-07 findings (+10 more)

### Community 32 - "test_vision.py"
Cohesion: 0.21
Nodes (12): _analyze(), _FakeAio, _FakeClient, _FakeModels, _FakeResponse, Tests del análisis de imágenes con Gemini (autodescripción/etiquetado). Sin…, El código llama `client.aio.models.generate_content`, la variante async del…, test_analyze_handles_gemini_failure() (+4 more)

### Community 33 - "ToolContext"
Cohesion: 0.15
Nodes (20): Actor, _erp_ctx(), Field, InjectedCtx, min_length, Tools que usan las capacidades de WhatsApp: foto, botones y listas. Estas tools…, Show a scrollable menu of options grouped in sections: the catalog, categories,…, Show the customer the photo of a product. Use `product_id` exactly as returned… (+12 more)

### Community 34 - "app/config.py"
Cohesion: 0.24
Nodes (7): field_validator, Settings, Raise ValueError if key is not a valid Fernet key. Call at startup., validate_fernet_key(), BaseSettings, Renaming the switch must not silently disable the bot on live deploys.…, test_bot_switch_still_accepts_the_historical_env_names()

### Community 35 - "test_message_debounce.py"
Cohesion: 0.14
Nodes (14): close_debounce(), debounce_message(), _get_client(), _keys(), Any, Redis-backed debounce for bursts of inbound WhatsApp messages. Each webhook…, Release the process-wide Redis connection pool at shutdown., Return the complete batch to one waiter; return ``[]`` to the others. Redis is… (+6 more)

### Community 36 - "optimize_image"
Cohesion: 0.21
Nodes (14): _flatten_to_rgb(), optimize_image(), Tratamiento de imágenes de productos (Pillow). Herramienta del front, aislada…, Normaliza `raw` a un cuadrado WebP de CANVAS×CANVAS con fondo blanco. Lanza…, Aplana transparencia sobre fondo blanco y devuelve una imagen RGB., Image, _png_bytes(), Tests del tratamiento de imágenes de productos (Pillow). El entorno compartido… (+6 more)

### Community 37 - "dependencies.py"
Cohesion: 0.24
Nodes (6): get_current_tenant(), Resolve the tenant for the authenticated user. Raises 404 if not onboarded., ApiTestCase, Base común para probar los routers FastAPI con dependencias aisladas., StrictSupabase, AuthApiTests

### Community 38 - "routers/erp/clients.py"
Cohesion: 0.17
Nodes (15): ClientCreate, ClientDetailResponse, ClientResponse, ClientUpdate, GET /erp/clients/{id}: the client plus their last sales (ClientsService.get)., create_client(), get_by_phone(), get_by_whatsapp() (+7 more)

### Community 39 - "SalesService"
Cohesion: 0.18
Nodes (10): _execute(), Estado y total de una venta, para validar y describir una cancelación., sale_brief(), sale_details(), Any, Exception, Postgres RAISE ... USING DETAIL=<json> surfaces through postgrest as a…, _rpc_error_detail() (+2 more)

### Community 40 - "test_storage.py"
Cohesion: 0.19
Nodes (9): Sube `data` (WebP) al bucket de productos y devuelve su URL pública. El path se…, upload_product_image(), _FakeBucket, _FakeStorage, _FakeSupabase, Tests de subida de imágenes a Supabase Storage., test_delete_uses_storage_path(), test_upload_returns_public_url() (+1 more)

### Community 41 - "test_middleware.py"
Cohesion: 0.39
Nodes (6): install_observability(), FastAPI, _app(), test_echoes_inbound_request_id(), test_generates_request_id_header(), test_security_headers_present()

### Community 42 - "public/agent.py"
Cohesion: 0.08
Nodes (35): Any, Run one admin turn with input guardrails and per-turn tracing. Mirrors the…, run_admin_agent_turn(), InputTooLongError, Raised when a user message exceeds the accepted length., sanitize_user_input(), _contact_from_thread_id(), flush() (+27 more)

### Community 43 - "Public catalog specialist prompt"
Cohesion: 0.21
Nodes (13): check_stock tool, Public catalog specialist prompt, send_image channel tool, send_list_message channel tool, send_reply_buttons channel tool, create_order tool, Public closer specialist prompt, human_handoff escalation tool (+5 more)

### Community 44 - "ingest_webhook"
Cohesion: 0.22
Nodes (11): debounce_bot_response(), ingest_webhook(), log_whatsapp_statuses(), AsyncClient, Start every debounce waiter from one Meta payload concurrently., Coalesce one conversation's message burst before invoking the agent., Ingest all message/status changes contained in one verified Meta payload., run_scheduled_responses() (+3 more)

### Community 46 - "WebhookApiTests"
Cohesion: 0.22
Nodes (4): Lo que devuelve `bridge.respond`: texto más acciones de canal., Un tap que se descarta es peor que no tener botones: el cliente toca y no pasa…, _turn(), WebhookApiTests

### Community 47 - "ERPContext"
Cohesion: 0.10
Nodes (22): activity_feed(), ai_activity_feed(), get, Activity endpoints. Thin: delegate to ActivityService., adjust_stock(), list_stock(), low_stock(), movements() (+14 more)

### Community 48 - "routers/erp/export.py"
Cohesion: 0.23
Nodes (15): _download(), export_barcode(), export_inventory(), export_report_pdf(), export_sales(), export_transactions(), get, Export endpoints. Return file downloads (Excel / PDF / PNG barcode). (+7 more)

### Community 49 - "routers/erp/finance.py"
Cohesion: 0.20
Nodes (14): CashAccountCreate, CashAccountUpdate, TransactionCreate, cashflow(), categories(), create_account(), create_transaction(), list_accounts() (+6 more)

### Community 50 - "StrictFilteredMutation"
Cohesion: 0.22
Nodes (3): Builder filtrado realista: permite ``eq``/``execute``, no ``select``., StrictFilteredMutation, StrictMutationQuery

### Community 51 - "transcription.py"
Cohesion: 0.32
Nodes (7): _get_client(), Whisper audio transcription for voice notes. Framework-agnostic (plain OpenAI…, Transcribe un archivo de audio a texto con Whisper. Devuelve '' si falla., Concatena las transcripciones de todas las notas de voz del mensaje., transcribe_audio(), transcribe_audio_media(), AsyncOpenAI

### Community 52 - "test_prompt_tool_sync.py"
Cohesion: 0.20
Nodes (9): _available_to(), parametrize, Every tool a prompt names must actually be bound to that agent. The port from…, Backticked snake_case identifiers — how every prompt writes a tool name., A prompt promising a tool the agent lacks makes the model improvise., A tool in the allow-list but bound to no agent is a dead code path., test_every_public_tool_is_bound_somewhere(), test_prompt_only_names_tools_the_agent_has() (+1 more)

### Community 53 - "erp_error_handler"
Cohesion: 0.32
Nodes (8): erp_error_handler(), Exception, Request, Catch-all: log with request context, return a safe JSON 500 (no leak)., Translate typed ERP business errors into a consistent JSON shape., unhandled_exception_handler(), exception_handler, JSONResponse

### Community 54 - "checkpointer.py"
Cohesion: 0.29
Nodes (7): get_chat_db_url(), get_pool(), LangGraph checkpointer: one shared Postgres pool for every tenant. Unlike the…, Return the process-wide pool, opening it on first use. Opened lazily rather…, AsyncConnectionPool, Without `check`, a stale connection is still served once and that turn dies., test_pool_validates_connections_before_handing_them_out()

### Community 55 - "product_creation.py"
Cohesion: 0.15
Nodes (16): _merge_tags(), Any, Single-operation product creation with one required primary image., delete_product_image(), Subida de imágenes de productos a Supabase Storage. Reusa el cliente…, Upload a WebP and retain its path so callers can compensate on failure., Delete one product image by Storage path., upload_product_image_asset() (+8 more)

### Community 56 - "Plan: Storefront Vendedor implementation"
Cohesion: 0.20
Nodes (11): app/ai/bridge.py respond() (Agno era), Plan: Storefront Vendedor implementation, storefront.register_sale (Agno era), app/services/storefront.py module, business_info injected via Agno dependencies, Design spec: Storefront vendedor, Product id as stable cross-turn anchor, bridge.respond returns None on crash vs empty string (+3 more)

### Community 57 - "router.py"
Cohesion: 0.22
Nodes (9): _classifier_prompt(), classify_intent(), _continuity_prompt(), IntentClassification, BaseModel, Bias the classifier towards the specialist already handling the thread. The…, Build the router node: classifies the next specialist for the current turn.…, History the classifier can see, without orphan ``tool_calls``. El router no… (+1 more)

### Community 58 - "Plan: Agno integration into doppel-api"
Cohesion: 0.20
Nodes (10): Shared AsyncConnectionPool for checkpointer, Tools registered with func= instead of coroutine=, app/ai/ Agno-based package (superseded), get_client_agent factory (Agno era), Plan: Agno integration into doppel-api, get_manager_agent factory (Agno era), count_available_products tool, Plan: client tool count_available_products (+2 more)

### Community 59 - "patch"
Cohesion: 0.27
Nodes (3): patch, DashboardApiTests, OAuthApiTests

### Community 60 - "test_async_discipline.py"
Cohesion: 0.31
Nodes (9): parametrize, _python_files(), Architectural guard: no blocking I/O inside `async def`. This is the rule the…, Yield (node, parents, enclosing_func, source) for each Supabase I/O call., A guard that matches nothing would pass forever; make sure it has teeth., _supabase_calls(), test_guard_actually_sees_the_calls(), test_supabase_calls_are_awaited() (+1 more)

### Community 61 - "stock.py"
Cohesion: 0.31
Nodes (9): StockResult, check_stock(), _erp_ctx(), Field, ge, InjectedCtx, Check available stock for a product by its id (as returned by search_catalog).…, Set the stock quantity for a product to a specific count. Admin-only. (+1 more)

### Community 62 - "RequestContextMiddleware"
Cohesion: 0.50
Nodes (3): Request, RequestContextMiddleware, BaseHTTPMiddleware

### Community 63 - "security.py"
Cohesion: 0.23
Nodes (12): health(), preflight(), get, Onboarding preflight: verifies everything needed by /oauth/exchange is healthy., client_ip(), decrypt_token(), encrypt_token(), _fernet() (+4 more)

### Community 64 - "execute_confirmed_action tool"
Cohesion: 0.29
Nodes (8): Admin agent prompt contract, execute_confirmed_action tool, propose_product_change tool, propose_sale_cancellation tool, propose_stock_adjustment tool, propose_transaction tool, Admin write confirmation gate, Admin agent package README

### Community 65 - "admin_actions.py"
Cohesion: 0.28
Nodes (6): _parse_timestamp(), Durable, tenant-scoped approvals for admin-agent mutations., Parsea un timestamp ISO de Postgres, asumiendo UTC si viene naive., Accept a raw interactive reply. Returns an executable id only on confirm., Conflict, datetime

### Community 66 - "normalize_phone"
Cohesion: 0.39
Nodes (6): normalize_phone(), Normalización de números de teléfono (extraído de manager_tools)., Strip everything that isn't a digit. Matches the format Meta sends in webhooks…, test_normalize_empty(), test_normalize_non_numeric(), test_normalize_strips_symbols()

### Community 69 - "get_product_image"
Cohesion: 0.67
Nodes (3): get_product_image(), URL pública de la foto de un producto, o None si no tiene. Aparte de…, test_get_product_image_is_tenant_scoped_and_requires_available()

### Community 70 - "search_catalog tool (public catalog)"
Cohesion: 0.67
Nodes (3): search_catalog tool (admin view), search_catalog tool (public catalog), storefront.search_catalog (Agno era)

### Community 71 - "routers/webhook.py"
Cohesion: 0.20
Nodes (10): BackgroundTasks, get, post, Request, HTTP boundary for the WhatsApp Cloud API webhook., Verify and delegate the payload. Always return 200 so Meta does not retry., receive_webhook(), verify_webhook() (+2 more)

### Community 87 - "_offline"
Cohesion: 0.67
Nodes (3): _offline(), fixture, Sin Postgres y sin Supabase: checkpoint en memoria y tracing mudo.

## Knowledge Gaps
- **19 isolated node(s):** `.claude/CLAUDE.md — graphify trigger pointer`, `graphify reference: add-watch`, `graphify reference: exports and benchmark`, `graphify reference: extraction subagent prompt spec`, `graphify reference: GitHub clone and cross-repo merge` (+14 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **9 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get_supabase()` connect `get_supabase` to `dashboard.py`, `admin_actions.py`, `meta.py`, `turn.py`, `dependencies.py`, `get_product_image`, `SalesService`, `test_public_routing.py`, `ingest_webhook`, `ERPContext`, `test_admin_tool_payloads.py`, `whatsapp/webhook.py`, `admin_view.py`, `InventoryService`, `product_creation.py`, `erp/context.py`, `security.py`?**
  _High betweenness centrality (0.133) - this node is a cross-community bridge._
- **Why does `ERPContext` connect `ERPContext` to `admin_actions.py`, `ToolContext`, `get_product_image`, `routers/erp/clients.py`, `admin.py`, `SalesService`, `test_admin_tool_payloads.py`, `routers/erp/export.py`, `routers/erp/finance.py`, `admin_view.py`, `routers/erp/sales.py`, `routers/erp/products.py`, `InventoryService`, `product_creation.py`, `get_supabase`, `test_product_creation.py`, `erp/context.py`?**
  _High betweenness centrality (0.083) - this node is a cross-community bridge._
- **Why does `TenantConfig` connect `TenantConfig` to `ToolContextMiddleware`, `ToolContext`, `test_ai_core_tools.py`, `test_ai_core_invariants.py`, `test_public_routing.py`, `public/agent.py`, `bridge.py`, `test_checkpointer_pool.py`, `test_turn_outbox.py`, `test_admin_tool_payloads.py`, `router.py`, `FakeSupabase`?**
  _High betweenness centrality (0.078) - this node is a cross-community bridge._
- **Are the 13 inferred relationships involving `TenantConfig` (e.g. with `InputTooLongError` and `MessageWindowMiddleware`) actually correct?**
  _`TenantConfig` has 13 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `ToolContext` (e.g. with `InputTooLongError` and `MessageWindowMiddleware`) actually correct?**
  _`ToolContext` has 8 INFERRED edges - model-reasoned connections that need verification._
- **What connects `.claude/CLAUDE.md — graphify trigger pointer`, `graphify reference: add-watch`, `graphify reference: exports and benchmark` to the rest of the system?**
  _19 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `dashboard.py` be split into smaller, more focused modules?**
  _Cohesion score 0.05960755275823769 - nodes in this community are weakly interconnected._