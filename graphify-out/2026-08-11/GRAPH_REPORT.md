# Graph Report - .  (2026-08-11)

## Corpus Check
- 166 files · ~77,259 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1440 nodes · 3415 edges · 87 communities (78 shown, 9 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 177 edges (avg confidence: 0.67)
- Token cost: 233,025 input · 0 output

## Community Hubs (Navigation)
- Dashboard Auth & Schemas
- Agent Middleware Stack
- Meta OAuth & Media API
- WhatsApp Outbound Sender
- Inbound Interactive Parsing
- AI Core Tool Tests
- App Lifespan & DB Pool
- Admin Tool Registry
- Settings Validation
- Public Router Graph
- Bridge Agent Cache
- Tenant Config Loading
- Turn Outbox & Runtime
- Supabase Test Fakes
- Admin Agent Build
- OAuth Signup Flow
- Catalog ERP Tools
- Graphify Skill Docs
- ERP Export Service
- ERP API Schemas
- ERP Reports Endpoints
- Product Router Endpoints
- Finance & Barcode Endpoints
- Prompt Loading & Tool Gating
- Product Service & Audit Log
- Product Creation Pipeline
- Storefront Sale Registration
- Channel List Actions
- Turn Result Delivery
- Admin Confirmation Consume
- Public Agent Models
- AI Core Pending Work Notes
- Vision Service Tests
- Channel WhatsApp Tools
- ERP Typed Exceptions
- Redis Message Debounce
- Product Image Optimization
- Tenant Auth Dependencies
- Client Router & Endpoints
- Sales Service RPCs
- Storage Test Fakes
- Choice Option Validators
- Langfuse Tracing Wiring
- Public Specialist Prompts
- Webhook Ingest Endpoint
- Business Info Query
- Webhook Delivery Tests
- Activity Feed Service
- Export Endpoints
- Finance Endpoints
- Clients Service
- Product Image Storage
- Prompt-Tool Sync Guard
- Inbound Courtesy Reactions
- LangGraph Checkpointer Pool
- Gemini Product Vision
- Agno-Era Storefront Archive
- Intent Classification Router
- Agno Integration Plan Archive
- Dashboard API Tests
- Async I/O Discipline Guard
- Stock Check Tool
- Inventory Endpoints
- Health & Token Security
- Admin Write Confirmation Gate
- Admin Action Approvals
- Phone Normalization
- Fake Chat Model Harness
- Typing Pause Simulation
- Channel Action Buffer
- search_catalog Tool Variants
- Webhook Signature Verification
- Channel Package Init
- Common Agent Building Blocks
- ERP Routers Init
- ERP Services Init
- WhatsApp Package Init
- Test Config Fixture

## God Nodes (most connected - your core abstractions)
1. `ERPContext` - 121 edges
2. `get_supabase()` - 96 edges
3. `ToolContext` - 61 edges
4. `TenantConfig` - 58 edges
5. `contextual_tool()` - 36 edges
6. `NotFound` - 34 edges
7. `ProductsService` - 29 edges
8. `FakeSupabase` - 28 edges
9. `bot_context()` - 24 edges
10. `log_activity()` - 24 edges

## Surprising Connections (you probably didn't know these)
- `storefront.register_sale (Agno era)` --semantically_similar_to--> `create_order tool`  [INFERRED] [semantically similar]
  docs/archive/superpowers/plans/2026-06-20-storefront-vendedor.md → app/ai_core/public/prompts/closer.md
- `storefront.search_catalog (Agno era)` --semantically_similar_to--> `search_catalog tool (public catalog)`  [INFERRED] [semantically similar]
  docs/archive/superpowers/plans/2026-06-20-storefront-vendedor.md → app/ai_core/public/prompts/catalog.md
- `test_button_title_is_truncated()` --calls--> `ReplyButton`  [EXTRACTED]
  tests/test_channel_actions.py → app/ai_core/channel/actions.py
- `WebhookApiTests` --uses--> `SendImageAction`  [INFERRED]
  tests/test_webhook.py → app/ai_core/channel/actions.py
- `test_zero_buttons_is_rejected()` --calls--> `SendButtonsAction`  [EXTRACTED]
  tests/test_channel_actions.py → app/ai_core/channel/actions.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **graphify skill documentation set (SKILL.md + reference docs)** — _claude_skills_graphify_skill_pipeline, _claude_skills_graphify_references_add_watch_doc, _claude_skills_graphify_references_exports_doc, _claude_skills_graphify_references_extraction_spec_doc, _claude_skills_graphify_references_github_and_merge_doc, _claude_skills_graphify_references_hooks_doc, _claude_skills_graphify_references_query_doc, _claude_skills_graphify_references_transcribe_doc, _claude_skills_graphify_references_update_doc [EXTRACTED 1.00]
- **doppel-api repo agent contract (AGENTS.md/CLAUDE.md/README.md/.claude/CLAUDE.md)** — agents_doc, claude_doc, readme_doc, _claude_claude_pointer [EXTRACTED 1.00]
- **Catalog -> stock -> order closing sequence** — app_ai_core_public_prompts_catalog_search_catalog, app_ai_core_public_prompts_catalog_check_stock, app_ai_core_public_prompts_closer_create_order [EXTRACTED 1.00]
- **Propose-then-confirm admin write pattern** — app_ai_core_admin_readme_confirmation_gate, app_ai_core_admin_prompt_execute_confirmed_action, app_ai_core_admin_prompt_propose_stock_adjustment [EXTRACTED 0.90]
- **Agno to LangChain/LangGraph migration lifecycle** — docs_archive_superpowers_plans_2026_06_16_agno_integration_doc, docs_archive_ai_core_revision_2026_07_doc, docs_archive_readme_doc [INFERRED 0.85]

## Communities (87 total, 9 thin omitted)

### Community 0 - "Dashboard Auth & Schemas"
Cohesion: 0.05
Nodes (75): get_current_user(), Verify Bearer JWT token from Supabase Auth and return the user., AdminPhonesResponse, AdminPhonesUpdateRequest, AiCoreTurnResponse, BotConfigResponse, BotConfigUpdateRequest, BusinessInfoResponse (+67 more)

### Community 1 - "Agent Middleware Stack"
Cohesion: 0.07
Nodes (30): AgentMiddleware, build_message_window(), build_tool_context(), build_tool_error_boundary(), build_tool_guardrail(), MessageWindowMiddleware, Exception, Return True if the tool's argument schema exposes a ``ctx`` field. (+22 more)

### Community 2 - "Meta OAuth & Media API"
Cohesion: 0.10
Nodes (42): download_media_to_path(), _error_payload(), exchange_code_for_token(), get_media_url(), get_waba_details(), get_waba_phone_numbers(), is_already_registered(), is_already_subscribed() (+34 more)

### Community 3 - "WhatsApp Outbound Sender"
Cohesion: 0.08
Nodes (27): AsyncClient, Salida hacia WhatsApp: todo lo que el número del tenant puede *hacer*. Frontera…, Espera lo que tardaría una persona en escribir `text`., Acciones de canal apuntando a un cliente concreto. `inbound_message_id` es el…, Tildes azules y "escribiendo…" sobre el mensaje entrante. Se llama ANTES de…, Reacciona al mensaje entrante. `emoji` vacío quita la reacción., WhatsAppSender, FakeClient (+19 more)

### Community 4 - "Inbound Interactive Parsing"
Cohesion: 0.08
Nodes (32): InteractiveReply, Lo que llega desde el canal y el agente tiene que poder entender. Hoy es sólo…, Un botón o una fila de lista que el cliente tocó., El id sin nuestro namespace. Un id sin el prefijo `choice:` no lo generamos…, Cómo percibe el agente el tap, en el mismo formato que las otras notas., get, HTTP boundary for the WhatsApp Cloud API webhook., verify_webhook() (+24 more)

### Community 5 - "AI Core Tool Tests"
Cohesion: 0.07
Nodes (41): _capture_register_sale(), _channel_ctx(), _ctx(), _order_ctx(), parametrize, Regression tests for the LangChain tool wiring in app/ai_core. Covers the two…, `ctx` is injected by middleware, so it must not be in the LLM's schema., Sync-only middleware makes `ainvoke` raise NotImplementedError. (+33 more)

### Community 6 - "App Lifespan & DB Pool"
Cohesion: 0.07
Nodes (32): close_pool(), Release the shared pool. Called from the app lifespan on shutdown., erp_error_handler(), lifespan(), Exception, FastAPI, Request, Catch-all: log with request context, return a safe JSON 500 (no leak). (+24 more)

### Community 7 - "Admin Tool Registry"
Cohesion: 0.13
Nodes (35): The explicit capability registry for the admin agent. Add future admin…, SendButtonsAction, _ctx(), execute_confirmed_action(), find_customers(), get_business_overview(), get_cash_summary(), get_customer_details() (+27 more)

### Community 8 - "Settings Validation"
Cohesion: 0.07
Nodes (28): field_validator, Settings, Raise ValueError if key is not a valid Fernet key. Call at startup., validate_fernet_key(), BaseSettings, model_validator, _ctx(), Invariants of the agent core that nothing else enforces. Each of these was a… (+20 more)

### Community 9 - "Public Router Graph"
Cohesion: 0.12
Nodes (27): build_public_agent(), Build the public turn graph: the router dispatches fresh on every turn. ``START…, _FakeClassifier, _offline(), _patch_specialists(), fixture, El router corre en cada turno, con sesgo de continuidad y sin handoffs. Esto…, Sacar el routing pegajoso no puede costar la persistencia del historial. (+19 more)

### Community 10 - "Bridge Agent Cache"
Cohesion: 0.09
Nodes (29): _config_fingerprint(), _document_note(), _evict_agent(), _get_or_build_agent(), _image_fallback_note(), Puente entre el webhook y el agente LangGraph. Entrada única por mensaje.…, Serialize turns on one conversation. A customer sending two messages in a row…, Drop a cached agent so the next message rebuilds it from scratch. Without this,… (+21 more)

### Community 11 - "Tenant Config Loading"
Cohesion: 0.09
Nodes (25): load_tenant_config(), Builds a TenantConfig by reading business_info + bot_configs from Supabase.…, AdminAgentConfig, PublicAgentConfig, BaseModel, Tenant config for the LangChain agent core, backed by Supabase (not YAML).…, Regression tests for the checkpointer pool and the agent-cache eviction. Both…, `.setup()` is idempotent but costs a round trip on every agent build. (+17 more)

### Community 12 - "Turn Outbox & Runtime"
Cohesion: 0.11
Nodes (24): SendTextAction, Buffer de acciones de canal de UN turno. Las tools no mandan nada por su…, Acciones encoladas por las tools durante un turno, en orden de encolado., Lo que se pasa como `context=` al invocar el grafo. Uno nuevo por turno. ⚠️ NO…, TurnOutbox, TurnRuntime, _build_graph(), BaseChatModel (+16 more)

### Community 13 - "Supabase Test Fakes"
Cohesion: 0.08
Nodes (7): Dobles reutilizables para pruebas sin servicios externos., FakeResult, FakeTableQuery, Implementación mínima en memoria del query builder asíncrono de Supabase., Builder filtrado realista: permite ``eq``/``execute``, no ``select``., StrictFilteredMutation, StrictMutationQuery

### Community 14 - "Admin Agent Build"
Cohesion: 0.11
Nodes (24): build_admin_agent(), Any, Run one admin turn with input guardrails and per-turn tracing. Mirrors the…, run_admin_agent_turn(), Owner-facing administrative agent., build_chat_model(), Centralized DeepSeek chat-model factory. Every agent in the core builds its…, Return the configured model name for a role (env override or default). (+16 more)

### Community 15 - "OAuth Signup Flow"
Cohesion: 0.15
Nodes (26): oauth_exchange(), BackgroundTasks, post, Request, HTTP boundary for WhatsApp Embedded Signup., meta_error_detail(), Return a short, log-friendly description of a Meta error response., _encrypt_access_token() (+18 more)

### Community 16 - "Catalog ERP Tools"
Cohesion: 0.12
Nodes (22): Actor, add_product(), _erp_ctx(), Field, gt, min_length, Catalog tools. Body reads/writes doppel-api's real ERP, not SQLite.…, Search available products by name, description and tags. Omit `query` to list… (+14 more)

### Community 17 - "Graphify Skill Docs"
Cohesion: 0.10
Nodes (25): .claude/CLAUDE.md — graphify trigger pointer, graphify reference: add-watch, graphify reference: exports and benchmark, graphify reference: extraction subagent prompt spec, graphify reference: GitHub clone and cross-repo merge, graphify reference: commit hook and CLAUDE.md integration, graphify reference: query, path, explain, graphify reference: transcribe video and audio (+17 more)

### Community 18 - "ERP Export Service"
Cohesion: 0.17
Nodes (14): _csv(), ExportService, Export service: Excel (openpyxl), PDF reports (reportlab), barcode labels…, Serialize a (title, headers, rows) table to the requested format., serialize(), _xlsx(), FinanceService, Finance service: transactions and cash accounts. Balances are never written… (+6 more)

### Community 19 - "ERP API Schemas"
Cohesion: 0.15
Nodes (23): AdjustmentRequest, CashAccountCreate, CashAccountResponse, CashAccountUpdate, ClientDetailResponse, ClientRecentSale, ClientResponse, ClientUpdate (+15 more)

### Community 20 - "ERP Reports Endpoints"
Cohesion: 0.15
Nodes (17): clients_report(), dashboard(), margin(), get, Reports endpoints. All accept ?date_from=&date_to= (default = current month)., sales_by_period(), top_products(), cancel_sale() (+9 more)

### Community 21 - "Product Router Endpoints"
Cohesion: 0.12
Nodes (22): ProductCreate, VariantCreate, add_variant(), create_product(), delete_product(), get_by_barcode(), get_product(), list_products() (+14 more)

### Community 22 - "Finance & Barcode Endpoints"
Cohesion: 0.11
Nodes (8): Generate a printable barcode label (Code128) for a product without its own code., Any, get_product_image(), URL pública de la foto de un producto, o None si no tiene. Aparte de…, get_supabase(), AsyncClient, Return the service-role database client. Keep this client away from Supabase…, test_get_product_image_is_tenant_scoped_and_requires_available()

### Community 23 - "Prompt Loading & Tool Gating"
Cohesion: 0.23
Nodes (17): allowed_tools_for(), load_prompt(), Load a static prompt owned by the corresponding agent role., Intersect an agent's tools with its tenant-level allow-list., TenantConfig, _enabled_specialists(), _extract_usage(), PublicAgentState (+9 more)

### Community 24 - "Product Service & Audit Log"
Cohesion: 0.18
Nodes (10): log_activity(), Append to the audit log. Best-effort: it never raises — a failed log must not…, _image_presence_map(), ProductsService, Any, Products + variants service. All logic + Supabase access for the catalog.…, Sum inventory quantity per product (across variants) for the given products., Resolve image presence without leaking image URLs into catalog results. (+2 more)

### Community 25 - "Product Creation Pipeline"
Cohesion: 0.16
Nodes (11): ProductCreationService, Orchestrate image processing, Storage and the existing product insert. Storage…, client(), _patch_pipeline(), _Products, Exception, fixture, Product creation is one multipart operation with compensating rollback. (+3 more)

### Community 26 - "Storefront Sale Registration"
Cohesion: 0.14
Nodes (19): Página lean de productos disponibles. Incluye `id` como ancla para la venta y…, Registra una venta del vendedor público. `items` = [{product_id, quantity}]…, register_sale(), search_catalog(), Unit tests for storefront lean reads. Shared test environment is loaded before…, Un ERPError genérico en get_by_phone no debe abortar la venta; client_id=None., La clave tiene que llegar al RPC: es lo único que lo hace idempotente., El RPC devuelve la venta ya registrada; el shape lean tiene que decirlo. (+11 more)

### Community 27 - "Channel List Actions"
Cohesion: 0.19
Nodes (15): ListRow, ListSection, BaseModel, Acciones de canal: lo que el agente decide mandar, antes de mandarlo. Pydantic…, Shape exacto que espera Meta para una sección de lista., SendListAction, SendReactionAction, Tests de la capa de canal pura: cortesías por reglas y modelos de acción. Todo… (+7 more)

### Community 28 - "Turn Result Delivery"
Cohesion: 0.18
Nodes (18): Lo que un turno produce: el texto del agente más lo que encoló el canal.…, SendImageAction, TurnResult, _chunk(), plan_delivery(), ChannelAction, Del resultado de un turno al orden exacto de mensajes que sale por WhatsApp.…, Orden final de entrega para un turno. (+10 more)

### Community 29 - "Admin Confirmation Consume"
Cohesion: 0.25
Nodes (14): _consume_admin_confirmation(), Validate our confirmation buttons before the LLM sees their identifier., AdminActionService, Any, FakeSupabase, _ctx(), test_admin_action_requires_matching_tenant_and_thread(), test_claim_recovers_stuck_executing_action() (+6 more)

### Community 30 - "Public Agent Models"
Cohesion: 0.22
Nodes (16): CatalogPage, ChoiceOption, HandoffResult, ListRowInput, OrderItemInput, OrderItemResult, OrderResult, ProductResult (+8 more)

### Community 31 - "AI Core Pending Work Notes"
Cohesion: 0.12
Nodes (18): ai_core pendientes vigentes, Image vision support resolved, Agent cache invalidation by config fingerprint, BOT_ENABLED switch rename, check_stock found-vs-zero-stock distinction, classify_intent -> route_dispatch fixed-depth graph, create_order idempotency fix, ai_core revision 2026-07 findings (+10 more)

### Community 32 - "Vision Service Tests"
Cohesion: 0.21
Nodes (12): _analyze(), _FakeAio, _FakeClient, _FakeModels, _FakeResponse, Tests del análisis de imágenes con Gemini (autodescripción/etiquetado). Sin…, El código llama `client.aio.models.generate_content`, la variante async del…, test_analyze_handles_gemini_failure() (+4 more)

### Community 33 - "Channel WhatsApp Tools"
Cohesion: 0.18
Nodes (16): ReplyButton, _erp_ctx(), Field, min_length, Tools que usan las capacidades de WhatsApp: foto, botones y listas. Estas tools…, Show a scrollable menu of options grouped in sections: the catalog, categories,…, Show the customer the photo of a product. Use `product_id` exactly as returned…, Offer the customer up to 3 tappable buttons: a payment method, confirm/cancel,… (+8 more)

### Community 34 - "ERP Typed Exceptions"
Cohesion: 0.15
Nodes (12): ERPError, Forbidden, Any, Exception, Typed business errors for the ERP. Services raise these — never…, Base business error. `status_code` and `code` are overridden by subclasses., ValidationError, _current_stock() (+4 more)

### Community 35 - "Redis Message Debounce"
Cohesion: 0.15
Nodes (12): debounce_message(), _get_client(), _keys(), Any, Redis-backed debounce for bursts of inbound WhatsApp messages. Each webhook…, Return the complete batch to one waiter; return ``[]`` to the others. Redis is…, Redis, FakeRedis (+4 more)

### Community 36 - "Product Image Optimization"
Cohesion: 0.21
Nodes (14): _flatten_to_rgb(), optimize_image(), Tratamiento de imágenes de productos (Pillow). Herramienta del front, aislada…, Normaliza `raw` a un cuadrado WebP de CANVAS×CANVAS con fondo blanco. Lanza…, Aplana transparencia sobre fondo blanco y devuelve una imagen RGB., Image, _png_bytes(), Tests del tratamiento de imágenes de productos (Pillow). El entorno compartido… (+6 more)

### Community 37 - "Tenant Auth Dependencies"
Cohesion: 0.22
Nodes (6): get_current_tenant(), Resolve the tenant for the authenticated user. Raises 404 if not onboarded., ApiTestCase, Base común para probar los routers FastAPI con dependencias aisladas., StrictSupabase, AuthApiTests

### Community 38 - "Client Router & Endpoints"
Cohesion: 0.19
Nodes (13): flush(), Send buffered events before a short-lived CLI process exits., ClientCreate, create_client(), get_by_phone(), get_by_whatsapp(), get_client(), list_clients() (+5 more)

### Community 39 - "Sales Service RPCs"
Cohesion: 0.24
Nodes (9): Conflict, InsufficientStock, Any, Exception, Sales service. The create/cancel paths delegate to atomic Postgres RPCs so the…, Postgres RAISE ... USING DETAIL=<json> surfaces through postgrest as a…, _rpc_error_detail(), _rpc_message() (+1 more)

### Community 40 - "Storage Test Fakes"
Cohesion: 0.24
Nodes (7): _FakeBucket, _FakeStorage, _FakeSupabase, Tests de subida de imágenes a Supabase Storage., test_delete_uses_storage_path(), test_upload_returns_public_url(), test_upload_uses_configured_bucket()

### Community 42 - "Langfuse Tracing Wiring"
Cohesion: 0.22
Nodes (12): _contact_from_thread_id(), get_handler(), invocation_config(), _opaque_id(), Any, Minimal Langfuse wiring for top-level LangGraph invocations., Return whether both Langfuse project credentials are configured., Return one process-wide LangChain callback handler, or ``None``. (+4 more)

### Community 43 - "Public Specialist Prompts"
Cohesion: 0.21
Nodes (13): check_stock tool, Public catalog specialist prompt, send_image channel tool, send_list_message channel tool, send_reply_buttons channel tool, create_order tool, Public closer specialist prompt, human_handoff escalation tool (+5 more)

### Community 44 - "Webhook Ingest Endpoint"
Cohesion: 0.17
Nodes (13): BackgroundTasks, post, Request, Verify and delegate the payload. Always return 200 so Meta does not retry., receive_webhook(), ingest_webhook(), log_whatsapp_statuses(), AsyncClient (+5 more)

### Community 45 - "Business Info Query"
Cohesion: 0.17
Nodes (6): business_info(), Perfil del negocio para inyectar al prompt (no es una tool)., _BizQuery, _BizSupabase, test_business_info_empty_returns_blanks(), test_business_info_returns_profile()

### Community 46 - "Webhook Delivery Tests"
Cohesion: 0.24
Nodes (4): Lo que devuelve `bridge.respond`: texto más acciones de canal., Un tap que se descarta es peor que no tener botones: el cliente toca y no pasa…, _turn(), WebhookApiTests

### Community 47 - "Activity Feed Service"
Cohesion: 0.23
Nodes (8): activity_feed(), ai_activity_feed(), get, Activity endpoints. Thin: delegate to ActivityService., ActivityService, _enrich(), Activity service: read-only feed over the append-only `activity_log` table., Add deep-link fields the frontend needs. `action` is always `<entity>.<verb>`…

### Community 48 - "Export Endpoints"
Cohesion: 0.33
Nodes (11): _download(), export_barcode(), export_inventory(), export_report_pdf(), export_sales(), export_transactions(), get, Export endpoints. Return file downloads (Excel / PDF / PNG barcode). (+3 more)

### Community 49 - "Finance Endpoints"
Cohesion: 0.23
Nodes (11): cashflow(), categories(), create_account(), create_transaction(), list_accounts(), list_transactions(), get, post (+3 more)

### Community 50 - "Clients Service"
Cohesion: 0.29
Nodes (5): ClientsService, Any, Clients service. Quick creation during a sale (name + phone is enough). The bot…, NotFound, Capa de lectura/venta del agente vendedor de cara al público (WhatsApp). Recibe…

### Community 51 - "Product Image Storage"
Cohesion: 0.21
Nodes (10): _merge_tags(), Any, delete_product_image(), Subida de imágenes de productos a Supabase Storage. Reusa el cliente…, Sube `data` (WebP) al bucket de productos y devuelve su URL pública. El path se…, Upload a WebP and retain its path so callers can compensate on failure., Delete one product image by Storage path., upload_product_image() (+2 more)

### Community 52 - "Prompt-Tool Sync Guard"
Cohesion: 0.20
Nodes (9): _available_to(), parametrize, Every tool a prompt names must actually be bound to that agent. The port from…, Backticked snake_case identifiers — how every prompt writes a tool name., A prompt promising a tool the agent lacks makes the model improvise., A tool in the allow-list but bound to no agent is a dead code path., test_every_public_tool_is_bound_somewhere(), test_prompt_only_names_tools_the_agent_has() (+1 more)

### Community 53 - "Inbound Courtesy Reactions"
Cohesion: 0.20
Nodes (10): choose_reaction(), _normalize(), Cortesías del canal por reglas: reacción con emoji y pausa de "escribiendo…".…, Minúsculas y sin acentos, para que el match no dependa de cómo escriban., Emoji para reaccionar al mensaje entrante, o None si no aplica ninguno.…, Gana sobre el texto: el saludo inicial merece el mismo gesto siempre., test_first_contact_always_waves(), test_no_reaction_when_nothing_applies() (+2 more)

### Community 54 - "LangGraph Checkpointer Pool"
Cohesion: 0.22
Nodes (10): get_chat_db_url(), get_pool(), open_checkpointer(), LangGraph checkpointer: one shared Postgres pool for every tenant. Unlike the…, Return the process-wide pool, opening it on first use. Opened lazily rather…, Return a checkpointer over the shared pool, running `.setup()` once. Async on…, AsyncConnectionPool, AsyncPostgresSaver (+2 more)

### Community 55 - "Gemini Product Vision"
Cohesion: 0.25
Nodes (9): Single-operation product creation with one required primary image., analyze_product_image(), _clean_str(), _get_client(), _normalize_tags(), Análisis de imágenes de productos con Gemini (autodescripción/etiquetado).…, Cliente genai perezoso (singleton). La API key sale del entorno/config., Devuelve {ai_ok, name, description, tags} sugeridos por Gemini para la imagen. (+1 more)

### Community 56 - "Agno-Era Storefront Archive"
Cohesion: 0.20
Nodes (11): app/ai/bridge.py respond() (Agno era), Plan: Storefront Vendedor implementation, storefront.register_sale (Agno era), app/services/storefront.py module, business_info injected via Agno dependencies, Design spec: Storefront vendedor, Product id as stable cross-turn anchor, bridge.respond returns None on crash vs empty string (+3 more)

### Community 57 - "Intent Classification Router"
Cohesion: 0.22
Nodes (9): _classifier_prompt(), classify_intent(), _continuity_prompt(), IntentClassification, BaseModel, Bias the classifier towards the specialist already handling the thread. The…, Build the router node: classifies the next specialist for the current turn.…, History the classifier can see, without orphan ``tool_calls``. El router no… (+1 more)

### Community 58 - "Agno Integration Plan Archive"
Cohesion: 0.20
Nodes (10): Shared AsyncConnectionPool for checkpointer, Tools registered with func= instead of coroutine=, app/ai/ Agno-based package (superseded), get_client_agent factory (Agno era), Plan: Agno integration into doppel-api, get_manager_agent factory (Agno era), count_available_products tool, Plan: client tool count_available_products (+2 more)

### Community 59 - "Dashboard API Tests"
Cohesion: 0.31
Nodes (3): patch, DashboardApiTests, OAuthApiTests

### Community 60 - "Async I/O Discipline Guard"
Cohesion: 0.31
Nodes (9): parametrize, _python_files(), Architectural guard: no blocking I/O inside `async def`. This is the rule the…, Yield (node, parents, enclosing_func, source) for each Supabase I/O call., A guard that matches nothing would pass forever; make sure it has teeth., _supabase_calls(), test_guard_actually_sees_the_calls(), test_supabase_calls_are_awaited() (+1 more)

### Community 61 - "Stock Check Tool"
Cohesion: 0.33
Nodes (8): StockResult, check_stock(), _erp_ctx(), Field, ge, Check available stock for a product by its id (as returned by search_catalog).…, Set the stock quantity for a product to a specific count. Admin-only., update_stock()

### Community 62 - "Inventory Endpoints"
Cohesion: 0.31
Nodes (8): adjust_stock(), list_stock(), low_stock(), movements(), movements_for_product(), get, post, Inventory endpoints. Thin: validate, delegate to InventoryService.

### Community 63 - "Health & Token Security"
Cohesion: 0.42
Nodes (7): health(), preflight(), get, Onboarding preflight: verifies everything needed by /oauth/exchange is healthy., decrypt_token(), encrypt_token(), _fernet()

### Community 64 - "Admin Write Confirmation Gate"
Cohesion: 0.29
Nodes (8): Admin agent prompt contract, execute_confirmed_action tool, propose_product_change tool, propose_sale_cancellation tool, propose_stock_adjustment tool, propose_transaction tool, Admin write confirmation gate, Admin agent package README

### Community 65 - "Admin Action Approvals"
Cohesion: 0.29
Nodes (5): _parse_timestamp(), Durable, tenant-scoped approvals for admin-agent mutations., Parsea un timestamp ISO de Postgres, asumiendo UTC si viene naive., Accept a raw interactive reply. Returns an executable id only on confirm., datetime

### Community 66 - "Phone Normalization"
Cohesion: 0.39
Nodes (6): normalize_phone(), Normalización de números de teléfono (extraído de manager_tools)., Strip everything that isn't a digit. Matches the format Meta sends in webhooks…, test_normalize_empty(), test_normalize_non_numeric(), test_normalize_strips_symbols()

### Community 67 - "Fake Chat Model Harness"
Cohesion: 0.29
Nodes (3): BaseChatModel, Contesta con su propia etiqueta, así el test sabe quién atendió el turno., _ResponderModel

### Community 68 - "Typing Pause Simulation"
Cohesion: 0.33
Nodes (6): Segundos a esperar antes de mandar `text`, descontando `elapsed`. `elapsed` es…, typing_pause(), El LLM ya tardó más que la pausa objetivo: no hay nada que simular., test_typing_pause_grows_with_length_and_is_capped(), test_typing_pause_handles_empty_text(), test_typing_pause_is_zero_once_the_turn_already_took_longer()

### Community 70 - "search_catalog Tool Variants"
Cohesion: 0.67
Nodes (3): search_catalog tool (admin view), search_catalog tool (public catalog), storefront.search_catalog (Agno era)

## Knowledge Gaps
- **19 isolated node(s):** `.claude/CLAUDE.md — graphify trigger pointer`, `graphify reference: add-watch`, `graphify reference: exports and benchmark`, `graphify reference: extraction subagent prompt spec`, `graphify reference: GitHub clone and cross-repo merge` (+14 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **9 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get_supabase()` connect `Finance & Barcode Endpoints` to `Dashboard Auth & Schemas`, `Inbound Interactive Parsing`, `Tenant Config Loading`, `OAuth Signup Flow`, `Catalog ERP Tools`, `ERP Export Service`, `ERP Reports Endpoints`, `Product Service & Audit Log`, `Admin Confirmation Consume`, `ERP Typed Exceptions`, `Tenant Auth Dependencies`, `Sales Service RPCs`, `Webhook Ingest Endpoint`, `Business Info Query`, `Activity Feed Service`, `Clients Service`, `Product Image Storage`, `Health & Token Security`, `Admin Action Approvals`?**
  _High betweenness centrality (0.180) - this node is a cross-community bridge._
- **Why does `TenantConfig` connect `Prompt Loading & Tool Gating` to `Agent Middleware Stack`, `Fake Chat Model Harness`, `AI Core Tool Tests`, `Admin Tool Registry`, `Settings Validation`, `Public Router Graph`, `Bridge Agent Cache`, `Tenant Config Loading`, `Turn Outbox & Runtime`, `Admin Agent Build`, `Catalog ERP Tools`, `Intent Classification Router`, `Admin Confirmation Consume`?**
  _High betweenness centrality (0.075) - this node is a cross-community bridge._
- **Why does `ERPContext` connect `ERP Reports Endpoints` to `Catalog ERP Tools`, `ERP Export Service`, `Product Router Endpoints`, `Finance & Barcode Endpoints`, `Product Service & Audit Log`, `Product Creation Pipeline`, `Storefront Sale Registration`, `Admin Confirmation Consume`, `ERP Typed Exceptions`, `Client Router & Endpoints`, `Sales Service RPCs`, `Business Info Query`, `Activity Feed Service`, `Export Endpoints`, `Finance Endpoints`, `Clients Service`, `Product Image Storage`, `Gemini Product Vision`, `Inventory Endpoints`, `Admin Action Approvals`?**
  _High betweenness centrality (0.075) - this node is a cross-community bridge._
- **Are the 8 inferred relationships involving `ToolContext` (e.g. with `InputTooLongError` and `MessageWindowMiddleware`) actually correct?**
  _`ToolContext` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Are the 13 inferred relationships involving `TenantConfig` (e.g. with `InputTooLongError` and `MessageWindowMiddleware`) actually correct?**
  _`TenantConfig` has 13 INFERRED edges - model-reasoned connections that need verification._
- **What connects `.claude/CLAUDE.md — graphify trigger pointer`, `graphify reference: add-watch`, `graphify reference: exports and benchmark` to the rest of the system?**
  _19 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Dashboard Auth & Schemas` be split into smaller, more focused modules?**
  _Cohesion score 0.05443037974683544 - nodes in this community are weakly interconnected._