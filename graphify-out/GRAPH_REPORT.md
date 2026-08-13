# Graph Report - doppel-api  (2026-08-12)

## Corpus Check
- 219 files · ~140,896 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 2104 nodes · 4426 edges · 137 communities (114 shown, 23 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 229 edges (avg confidence: 0.68)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `63d04e43`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- dashboard.py
- ToolContextMiddleware
- meta.py
- test_whatsapp_sender.py
- turn.py
- test_ai_core_tools.py
- build_chat_model
- admin.py
- test_ai_core_invariants.py
- test_public_routing.py
- bridge.py
- tenant.py
- test_turn_outbox.py
- FakeTableQuery
- render.py
- test_admin_tool_payloads.py
- whatsapp/webhook.py
- /graphify SKILL.md pipeline
- test_channel_actions.py
- TenantConfig
- erp_schemas.py
- routers/erp/products.py
- admin_view.py
- MultiTurnHarborAgent
- get_supabase
- test_product_creation.py
- NotFound
- index.ts
- main.py
- FakeSupabase
- SalesService
- ai_core revision 2026-07 findings
- test_vision.py
- channel.py
- test_admin_deep_agent.py
- Guide the user through their first agent
- optimize_image
- routers/erp/inventory.py
- What You Must Do When Invoked
- routers/erp/finance.py
- test_storage.py
- test_middleware.py
- langfuse.py
- Public catalog specialist prompt
- test_message_debounce.py
- langgraph-cli/SKILL.md
- Swarm
- supabase_client.py
- services/erp/export.py
- ToolContext
- Core Packages
- ERPContext
- test_prompt_tool_sync.py
- ecosystem-primer/SKILL.md
- admin/agent.py
- test_admin_product_photo.py
- Plan: Storefront Vendedor implementation
- WebhookApiTests
- Plan: Agno integration into doppel-api
- dependencies.py
- test_async_discipline.py
- stock.py
- Environment Building
- app/config.py
- execute_confirmed_action tool
- Eval Engineering
- langgraph-fundamentals/SKILL.md
- langgraph-human-in-the-loop/SKILL.md
- LangSmith Online Evaluator API Reference
- services/vision.py
- search_catalog tool (public catalog)
- product_creation.py
- channel/__init__.py
- common/__init__.py
- routers/erp/__init__.py
- services/erp/__init__.py
- whatsapp/__init__.py
- conftest.py
- langgraph-persistence/SKILL.md
- patch
- _ResponderModel
- eval-engineering/SKILL.md
- Evaluator Design
- Trace Inspection
- graphify reference: extra exports and benchmark
- supabase.py
- langchain-rag/SKILL.md
- receive_webhook
- routers/erp/clients.py
- ScriptedModel
- Task Design
- Trace Sourcing
- Verifier Design
- langchain-fundamentals/SKILL.md
- Online Eval Engineering
- client_ip
- SKILL.md Format
- deep-agents-orchestration/SKILL.md
- Harness
- LLM-as-judge best practices
- graphify reference: query, path, explain
- Harbor Task and Run Contract
- langchain-middleware/SKILL.md
- Common field name patterns
- Create a code evaluator
- List, update, and delete evaluators
- graphify reference: add a URL and watch a folder
- graphify reference: commit hook and native CLAUDE.md integration
- graphify reference: incremental update and cluster-only
- deep-agents-memory/SKILL.md
- Deep Agents Python quickstart
- Deep Agents TypeScript quickstart
- LangChain Python quickstart
- LangChain TypeScript quickstart
- LangGraph Python quickstart
- LangGraph TypeScript quickstart
- graphify reference: GitHub clone and cross-repo merge
- graphify reference: transcribe video and audio
- extraction-spec.md
- ingest_webhook
- routers/erp/sales.py
- ChannelAction
- BaseModel
- FastAPI
- Request
- BaseChatModel
- fixture

## God Nodes (most connected - your core abstractions)
1. `ERPContext` - 128 edges
2. `get_supabase()` - 94 edges
3. `TenantConfig` - 64 edges
4. `contextual_tool()` - 34 edges
5. `ToolContext` - 33 edges
6. `NotFound` - 33 edges
7. `FakeSupabase` - 28 edges
8. `ProductsService` - 26 edges
9. `Guide the user through their first agent` - 26 edges
10. `InventoryService` - 24 edges

## Surprising Connections (you probably didn't know these)
- `storefront.register_sale (Agno era)` --semantically_similar_to--> `create_order tool`  [INFERRED] [semantically similar]
  docs/archive/superpowers/plans/2026-06-20-storefront-vendedor.md → app/ai_core/public/prompts/closer.md
- `storefront.search_catalog (Agno era)` --semantically_similar_to--> `search_catalog tool (public catalog)`  [INFERRED] [semantically similar]
  docs/archive/superpowers/plans/2026-06-20-storefront-vendedor.md → app/ai_core/public/prompts/catalog.md
- `test_agent_entrypoints_are_async()` --indirect_call--> `build_admin_agent()`  [INFERRED]
  tests/test_ai_core_tools.py → app/ai_core/admin/agent.py
- `_FakeRuntime` --uses--> `TurnRuntime`  [INFERRED]
  tests/test_admin_deep_agent.py → app/ai_core/channel/outbox.py
- `ScriptedModel` --uses--> `TurnRuntime`  [INFERRED]
  tests/test_admin_deep_agent.py → app/ai_core/channel/outbox.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **graphify skill documentation set (SKILL.md + reference docs)** — _claude_skills_graphify_skill_pipeline, _claude_skills_graphify_references_add_watch_doc, _claude_skills_graphify_references_exports_doc, _claude_skills_graphify_references_extraction_spec_doc, _claude_skills_graphify_references_github_and_merge_doc, _claude_skills_graphify_references_hooks_doc, _claude_skills_graphify_references_query_doc, _claude_skills_graphify_references_transcribe_doc, _claude_skills_graphify_references_update_doc [EXTRACTED 1.00]
- **doppel-api repo agent contract (AGENTS.md/CLAUDE.md/README.md/.claude/CLAUDE.md)** — agents_doc, claude_doc, readme_doc, _claude_claude_pointer [EXTRACTED 1.00]
- **Catalog -> stock -> order closing sequence** — app_ai_core_public_prompts_catalog_search_catalog, app_ai_core_public_prompts_catalog_check_stock, app_ai_core_public_prompts_closer_create_order [EXTRACTED 1.00]
- **Propose-then-confirm admin write pattern** — app_ai_core_admin_readme_confirmation_gate, app_ai_core_admin_prompt_execute_confirmed_action, app_ai_core_admin_prompt_propose_stock_adjustment [EXTRACTED 0.90]
- **Agno to LangChain/LangGraph migration lifecycle** — docs_archive_superpowers_plans_2026_06_16_agno_integration_doc, docs_archive_ai_core_revision_2026_07_doc, docs_archive_readme_doc [INFERRED 0.85]

## Communities (137 total, 23 thin omitted)

### Community 0 - "dashboard.py"
Cohesion: 0.06
Nodes (74): AdminPhonesResponse, AdminPhonesUpdateRequest, AiCoreTurnResponse, BotConfigResponse, BotConfigUpdateRequest, BusinessInfoResponse, BusinessInfoUpdateRequest, ConversationMessage (+66 more)

### Community 1 - "ToolContextMiddleware"
Cohesion: 0.10
Nodes (15): AgentMiddleware, MessageWindowMiddleware, Exception, Return True if the tool's argument schema exposes a ``ctx`` field., Reject tool calls outside the allow-list for the active role. For tools passed…, Convert tool exceptions into structured error messages for the model., Bound model context while the parent graph keeps full durable history. This…, Inject the run-scoped ToolContext into tools that accept a ``ctx`` arg.… (+7 more)

### Community 2 - "meta.py"
Cohesion: 0.06
Nodes (69): oauth_exchange(), BackgroundTasks, post, Request, HTTP boundary for WhatsApp Embedded Signup., download_media_to_path(), _error_payload(), exchange_code_for_token() (+61 more)

### Community 3 - "test_whatsapp_sender.py"
Cohesion: 0.08
Nodes (27): AsyncClient, Salida hacia WhatsApp: todo lo que el número del tenant puede *hacer*. Frontera…, Espera lo que tardaría una persona en escribir `text`., Acciones de canal apuntando a un cliente concreto. `inbound_message_id` es el…, Tildes azules y "escribiendo…" sobre el mensaje entrante. Se llama ANTES de…, Reacciona al mensaje entrante. `emoji` vacío quita la reacción., WhatsAppSender, FakeClient (+19 more)

### Community 4 - "turn.py"
Cohesion: 0.19
Nodes (15): cleanup_media_files(), download_media_files(), inbound_message_type(), _media_download_path(), AsyncClient, Path, Best-effort removal of every attachment downloaded for one turn., action_preview() (+7 more)

### Community 5 - "test_ai_core_tools.py"
Cohesion: 0.06
Nodes (51): build_message_window(), _capture_register_sale(), _channel_ctx(), _ctx(), _order_ctx(), parametrize, Regression tests for the LangChain tool wiring in app/ai_core. Covers the two…, `ctx` is injected by middleware, so it must not be in the LLM's schema. (+43 more)

### Community 6 - "build_chat_model"
Cohesion: 0.32
Nodes (7): build_chat_model(), Centralized DeepSeek chat-model factory. Every agent in the core builds its…, Return the configured model name for a role (env override or default)., Build the chat model for an agent role with sane production defaults. Fails…, resolve_model_name(), ChatDeepSeek, ModelRole

### Community 7 - "admin.py"
Cohesion: 0.12
Nodes (41): The explicit capability registry for the admin agent. Add future admin…, _ctx(), execute_confirmed_action(), find_customers(), get_business_overview(), get_cash_summary(), get_customer_details(), get_inventory_alerts() (+33 more)

### Community 8 - "test_ai_core_invariants.py"
Cohesion: 0.09
Nodes (24): Per-turn operational trace, persisted in doppel-api's existing `activity_log`…, trace_turn(), _truncate(), _ctx(), Invariants of the agent core that nothing else enforces. Each of these was a…, search_catalog + check_stock + create_order., Concurrent turns on one checkpoint mean one message silently vanishes., A tool outside ALL_ADMIN_TOOLS is rejected by the guardrail at runtime,… (+16 more)

### Community 9 - "test_public_routing.py"
Cohesion: 0.09
Nodes (36): build_public_agent(), Build the public turn graph: the router dispatches fresh on every turn. ``START…, _classifier_prompt(), classify_intent(), _continuity_prompt(), IntentClassification, BaseModel, Bias the classifier towards the specialist already handling the thread. The… (+28 more)

### Community 10 - "bridge.py"
Cohesion: 0.10
Nodes (27): _consume_admin_confirmation(), _document_note(), _evict_agent(), _image_fallback_note(), Puente entre el webhook y el agente LangGraph. Entrada única por mensaje.…, Serialize turns on one conversation. A customer sending two messages in a row…, Drop a cached agent so the next message rebuilds it from scratch. Without this,…, Validate our confirmation buttons before the LLM sees their identifier. (+19 more)

### Community 11 - "tenant.py"
Cohesion: 0.10
Nodes (25): load_tenant_config(), Builds a TenantConfig by reading business_info + bot_configs from Supabase.…, AdminAgentConfig, PublicAgentConfig, Tenant config for the LangChain agent core, backed by Supabase (not YAML).…, BaseModel, Regression tests for the checkpointer pool and the agent-cache eviction. Both…, `.setup()` is idempotent but costs a round trip on every agent build. (+17 more)

### Community 12 - "test_turn_outbox.py"
Cohesion: 0.10
Nodes (26): SendTextAction, Buffer de acciones de canal de UN turno. Las tools no mandan nada por su…, Acciones encoladas por las tools durante un turno, en orden de encolado., Devuelve lo encolado y vacía el buffer., Lo que se pasa como `context=` al invocar el grafo. Uno nuevo por turno. ⚠️ NO…, TurnOutbox, TurnRuntime, ChannelAction (+18 more)

### Community 14 - "render.py"
Cohesion: 0.10
Nodes (47): business_overview(), cash_summary(), customer_details(), day(), doc(), execute_confirmed_action(), find_customers(), inventory_alerts() (+39 more)

### Community 15 - "test_admin_tool_payloads.py"
Cohesion: 0.12
Nodes (21): get_sale(), list_sales(), get, _assert_within_budget(), _ctx(), parametrize, Enforcement suite: admin tools must return compact text within a declared…, Adding a tool to ADMIN_TOOLS without a BUDGET entry must break the suite. (+13 more)

### Community 16 - "whatsapp/webhook.py"
Cohesion: 0.15
Nodes (14): InteractiveReply, Lo que llega desde el canal y el agente tiene que poder entender. Hoy es sólo…, Un botón o una fila de lista que el cliente tocó., El id sin nuestro namespace. Un id sin el prefijo `choice:` no lo generamos…, Cómo percibe el agente el tap, en el mismo formato que las otras notas., InboundMessage, parse_inbound(), Normalize inbound Meta messages and manage their temporary media files. (+6 more)

### Community 17 - "/graphify SKILL.md pipeline"
Cohesion: 0.10
Nodes (25): .claude/CLAUDE.md — graphify trigger pointer, graphify reference: add-watch, graphify reference: exports and benchmark, graphify reference: extraction subagent prompt spec, graphify reference: GitHub clone and cross-repo merge, graphify reference: commit hook and CLAUDE.md integration, graphify reference: query, path, explain, graphify reference: transcribe video and audio (+17 more)

### Community 18 - "test_channel_actions.py"
Cohesion: 0.06
Nodes (54): ListRow, ListSection, BaseModel, field_validator, Acciones de canal: lo que el agente decide mandar, antes de mandarlo. Pydantic…, Lo que un turno produce: el texto del agente más lo que encoló el canal.…, Shape exacto que espera Meta para una sección de lista., ReplyButton (+46 more)

### Community 19 - "TenantConfig"
Cohesion: 0.11
Nodes (36): build_admin_agent(), _config_fingerprint(), _get_or_build_agent(), Fingerprint the tenant config that gets baked into a built agent. Deliberately…, Cache the compiled agent per (tenant_id, role), keyed to its config. `respond`…, build_tool_context(), build_tool_error_boundary(), build_tool_guardrail() (+28 more)

### Community 20 - "erp_schemas.py"
Cohesion: 0.19
Nodes (18): CashAccountCreate, CashAccountResponse, CashAccountUpdate, ClientDetailResponse, ClientRecentSale, ClientResponse, DashboardResponse, InventoryRow (+10 more)

### Community 21 - "routers/erp/products.py"
Cohesion: 0.12
Nodes (19): ProductCreate, create_product(), delete_product(), get_by_barcode(), get_product(), list_products(), _product_create_form(), delete (+11 more)

### Community 22 - "admin_view.py"
Cohesion: 0.13
Nodes (18): cash_summary(), customer_details(), _cut(), find_customers(), inventory_alerts(), product_brief(), Capa de lectura/consulta del agente admin de cara al dueño (WhatsApp). Recibe…, Nombre de un producto, para el mensaje de una propuesta de stock/edición. (+10 more)

### Community 23 - "MultiTurnHarborAgent"
Cohesion: 0.06
Nodes (43): AgentContext, HarnessReply, HarnessSession, MultiTurnHarborAgent, Protocol, Reusable Harbor adapter for scripted or LLM-user conversations., One visible response and directly observed evidence for a Harness turn., Adapt a repository Harness session to the conversation runner. (+35 more)

### Community 24 - "get_supabase"
Cohesion: 0.11
Nodes (18): Any, log_activity(), Append to the audit log. Best-effort: it never raises — a failed log must not…, FinanceService, Any, _current_stock(), Apply a manual stock correction by inserting one adjustment movement. Accepts…, _image_presence_map() (+10 more)

### Community 25 - "test_product_creation.py"
Cohesion: 0.16
Nodes (11): ProductCreationService, Orchestrate image processing, Storage and the existing product insert. Storage…, client(), _patch_pipeline(), _Products, Exception, fixture, Product creation is one multipart operation with compensating rollback. (+3 more)

### Community 26 - "NotFound"
Cohesion: 0.07
Nodes (33): ClientsService, Any, Clients service. Quick creation during a sale (name + phone is enough). The bot…, NotFound, business_info(), get_product_image(), Capa de lectura/venta del agente vendedor de cara al público (WhatsApp). Recibe…, Perfil del negocio para inyectar al prompt (no es una tool). (+25 more)

### Community 27 - "index.ts"
Cohesion: 0.07
Nodes (60): buildBatchPrompt(), clampBatchSize(), createBatches(), formatValue(), MAX_BATCH_SIZE, renderItemsBlock(), renderTaskBlock(), resolveBatchGroups() (+52 more)

### Community 28 - "main.py"
Cohesion: 0.14
Nodes (14): close_store(), Release the store. Called from the app lifespan, BEFORE `close_pool()`. Order…, erp_error_handler(), lifespan(), Exception, Catch-all: log with request context, return a safe JSON 500 (no leak)., Translate typed ERP business errors into a consistent JSON shape., unhandled_exception_handler() (+6 more)

### Community 29 - "FakeSupabase"
Cohesion: 0.40
Nodes (11): AdminActionService, FakeSupabase, _ctx(), test_admin_action_requires_matching_tenant_and_thread(), test_claim_recovers_stuck_executing_action(), test_claim_rejects_recently_stuck_executing_action(), test_confirmation_can_only_be_claimed_once(), test_confirmation_id_chain_end_to_end() (+3 more)

### Community 30 - "SalesService"
Cohesion: 0.18
Nodes (10): _execute(), Estado y total de una venta, para validar y describir una cancelación., sale_brief(), sale_details(), Any, Exception, Postgres RAISE ... USING DETAIL=<json> surfaces through postgrest as a…, _rpc_error_detail() (+2 more)

### Community 31 - "ai_core revision 2026-07 findings"
Cohesion: 0.12
Nodes (18): ai_core pendientes vigentes, Image vision support resolved, Agent cache invalidation by config fingerprint, BOT_ENABLED switch rename, check_stock found-vs-zero-stock distinction, classify_intent -> route_dispatch fixed-depth graph, create_order idempotency fix, ai_core revision 2026-07 findings (+10 more)

### Community 32 - "test_vision.py"
Cohesion: 0.21
Nodes (12): _analyze(), _FakeAio, _FakeClient, _FakeModels, _FakeResponse, Tests del análisis de imágenes con Gemini (autodescripción/etiquetado). Sin…, El código llama `client.aio.models.generate_content`, la variante async del…, test_analyze_handles_gemini_failure() (+4 more)

### Community 33 - "channel.py"
Cohesion: 0.21
Nodes (14): _erp_ctx(), Field, InjectedCtx, min_length, Tools que usan las capacidades de WhatsApp: foto, botones y listas. Estas tools…, Show a scrollable menu of options grouped in sections: the catalog, categories,…, Show the customer the photo of a product. Use `product_id` exactly as returned…, Offer the customer up to 3 tappable buttons: a payment method, confirm/cancel,… (+6 more)

### Community 34 - "test_admin_deep_agent.py"
Cohesion: 0.09
Nodes (36): memory_namespace(), _namespace_factory(), Store namespace holding one tenant's admin memories., Build the `StoreBackend` namespace factory for one tenant. **This is the multi-…, fixture, build(), _FakeRuntime, parametrize (+28 more)

### Community 35 - "Guide the user through their first agent"
Cohesion: 0.07
Nodes (29): 1. Ask what they want to build, 2. Check the answer against the limits, 3. Map the answer onto capabilities, 4. Confirm the shape before writing files, 5. Scaffold and wire the smallest thing that runs, 6. Handle keys without touching their secrets, 7. Run it locally, then deploy, Channels (+21 more)

### Community 36 - "optimize_image"
Cohesion: 0.21
Nodes (15): ValidationError, _flatten_to_rgb(), optimize_image(), Tratamiento de imágenes de productos (Pillow). Herramienta del front, aislada…, Normaliza `raw` a un cuadrado WebP de CANVAS×CANVAS con fondo blanco. Lanza…, Aplana transparencia sobre fondo blanco y devuelve una imagen RGB., Image, _png_bytes() (+7 more)

### Community 37 - "routers/erp/inventory.py"
Cohesion: 0.29
Nodes (9): AdjustmentRequest, adjust_stock(), list_stock(), low_stock(), movements(), movements_for_product(), get, post (+1 more)

### Community 38 - "What You Must Do When Invoked"
Cohesion: 0.08
Nodes (24): For /graphify add and --watch, For /graphify query, For the commit hook and native CLAUDE.md integration, For --update and --cluster-only, /graphify, Honesty Rules, Interpreter guard for subcommands, Part A - Structural extraction for code files (+16 more)

### Community 39 - "routers/erp/finance.py"
Cohesion: 0.22
Nodes (12): TransactionCreate, cashflow(), categories(), create_account(), create_transaction(), list_accounts(), list_transactions(), get (+4 more)

### Community 40 - "test_storage.py"
Cohesion: 0.24
Nodes (7): _FakeBucket, _FakeStorage, _FakeSupabase, Tests de subida de imágenes a Supabase Storage., test_delete_uses_storage_path(), test_upload_returns_public_url(), test_upload_uses_configured_bucket()

### Community 41 - "test_middleware.py"
Cohesion: 0.17
Nodes (11): install_observability(), FastAPI, Request, RequestContextMiddleware, RequestIdLogFilter, BaseHTTPMiddleware, LogRecord, _app() (+3 more)

### Community 42 - "langfuse.py"
Cohesion: 0.17
Nodes (15): _contact_from_thread_id(), flush(), get_handler(), invocation_config(), _opaque_id(), Any, Minimal Langfuse wiring for top-level LangGraph invocations., Send buffered events before a short-lived CLI process exits. (+7 more)

### Community 43 - "Public catalog specialist prompt"
Cohesion: 0.21
Nodes (13): check_stock tool, Public catalog specialist prompt, send_image channel tool, send_list_message channel tool, send_reply_buttons channel tool, create_order tool, Public closer specialist prompt, human_handoff escalation tool (+5 more)

### Community 44 - "test_message_debounce.py"
Cohesion: 0.14
Nodes (14): close_debounce(), debounce_message(), _get_client(), _keys(), Any, Redis-backed debounce for bursts of inbound WhatsApp messages. Each webhook…, Release the process-wide Redis connection pool at shutdown., Return the complete batch to one waiter; return ``[]`` to the others. Redis is… (+6 more)

### Community 45 - "langgraph-cli/SKILL.md"
Cohesion: 0.10
Nodes (20): Commands, Full config with all keys, Gotchas, Installation, Key reference, `langgraph build`, `langgraph deploy`, `langgraph deploy delete` (+12 more)

### Community 46 - "Swarm"
Cohesion: 0.12
Nodes (16): Action-only tasks, Aggregation, API Reference, Batching, Chaining passes, Choosing a source, `create(source)`, Filtering (+8 more)

### Community 47 - "supabase_client.py"
Cohesion: 0.11
Nodes (19): _parse_timestamp(), Durable, tenant-scoped approvals for admin-agent mutations., Parsea un timestamp ISO de Postgres, asumiendo UTC si viene naive., Accept a raw interactive reply. Returns an executable id only on confirm., Conflict, ERPError, Forbidden, InsufficientStock (+11 more)

### Community 48 - "services/erp/export.py"
Cohesion: 0.21
Nodes (16): _download(), export_barcode(), export_inventory(), export_report_pdf(), export_sales(), export_transactions(), get, Export endpoints. Return file downloads (Excel / PDF / PNG barcode). (+8 more)

### Community 49 - "ToolContext"
Cohesion: 0.09
Nodes (38): Actor, create_product_from_photo(), _erp_ctx(), Field, ge, gt, InjectedCtx, min_length (+30 more)

### Community 50 - "Core Packages"
Cohesion: 0.12
Nodes (15): Common Mistakes, Core Packages, Environment Requirements, Environment Variables, Framework Choice, Minimal Project Templates, Python — always required, Python — common tool & retrieval packages (+7 more)

### Community 51 - "ERPContext"
Cohesion: 0.11
Nodes (21): activity_feed(), ai_activity_feed(), get, Activity endpoints. Thin: delegate to ActivityService., clients_report(), dashboard(), margin(), get (+13 more)

### Community 52 - "test_prompt_tool_sync.py"
Cohesion: 0.20
Nodes (9): _available_to(), parametrize, Every tool a prompt names must actually be bound to that agent. The port from…, Backticked snake_case identifiers — how every prompt writes a tool name., A prompt promising a tool the agent lacks makes the model improvise., A tool in the allow-list but bound to no agent is a dead code path., test_every_public_tool_is_bound_somewhere(), test_prompt_only_names_tools_the_agent_has() (+1 more)

### Community 53 - "ecosystem-primer/SKILL.md"
Cohesion: 0.13
Nodes (14): Accessing docs in an agent context, Canonical landing pages, Deep Agents, Deep Agents — agent harness, LangChain, LangChain — agent framework, LangGraph, LangGraph — agent runtime (+6 more)

### Community 54 - "admin/agent.py"
Cohesion: 0.09
Nodes (24): Any, Run one admin turn with input guardrails and per-turn tracing. Mirrors the…, run_admin_agent_turn(), Owner-facing administrative agent., close_pool(), get_chat_db_url(), get_pool(), open_checkpointer() (+16 more)

### Community 55 - "test_admin_product_photo.py"
Cohesion: 0.36
Nodes (7): _merge_tags(), Any, _ctx(), `create_product_from_photo`: the WhatsApp photo alta flow. Follows the style of…, test_with_photo_creates_the_product_once(), test_with_stock_adjusts_inventory_after_creating(), test_without_photo_asks_for_one_and_never_calls_the_service()

### Community 56 - "Plan: Storefront Vendedor implementation"
Cohesion: 0.20
Nodes (11): app/ai/bridge.py respond() (Agno era), Plan: Storefront Vendedor implementation, storefront.register_sale (Agno era), app/services/storefront.py module, business_info injected via Agno dependencies, Design spec: Storefront vendedor, Product id as stable cross-turn anchor, bridge.respond returns None on crash vs empty string (+3 more)

### Community 57 - "WebhookApiTests"
Cohesion: 0.24
Nodes (4): Lo que devuelve `bridge.respond`: texto más acciones de canal., Un tap que se descarta es peor que no tener botones: el cliente toca y no pasa…, _turn(), WebhookApiTests

### Community 58 - "Plan: Agno integration into doppel-api"
Cohesion: 0.20
Nodes (10): Shared AsyncConnectionPool for checkpointer, Tools registered with func= instead of coroutine=, app/ai/ Agno-based package (superseded), get_client_agent factory (Agno era), Plan: Agno integration into doppel-api, get_manager_agent factory (Agno era), count_available_products tool, Plan: client tool count_available_products (+2 more)

### Community 59 - "dependencies.py"
Cohesion: 0.21
Nodes (8): get_current_tenant(), get_current_user(), Verify Bearer JWT token from Supabase Auth and return the user., Resolve the tenant for the authenticated user. Raises 404 if not onboarded., HTTPAuthorizationCredentials, ApiTestCase, Base común para probar los routers FastAPI con dependencias aisladas., AuthApiTests

### Community 60 - "test_async_discipline.py"
Cohesion: 0.31
Nodes (9): parametrize, _python_files(), Architectural guard: no blocking I/O inside `async def`. This is the rule the…, Yield (node, parents, enclosing_func, source) for each Supabase I/O call., A guard that matches nothing would pass forever; make sure it has teeth., _supabase_calls(), test_guard_actually_sees_the_calls(), test_supabase_calls_are_awaited() (+1 more)

### Community 61 - "stock.py"
Cohesion: 0.31
Nodes (9): StockResult, check_stock(), _erp_ctx(), Field, ge, InjectedCtx, Check available stock for a product by its id (as returned by search_catalog).…, Set the stock quantity for a product to a specific count. Admin-only. (+1 more)

### Community 62 - "Environment Building"
Cohesion: 0.17
Nodes (12): Build the backend and world state, Choose each dependency, Choose the implementation and data, Coding agent, Define the backend contract, Docs search, Environment Building, Examples (+4 more)

### Community 63 - "app/config.py"
Cohesion: 0.21
Nodes (12): health(), preflight(), get, Onboarding preflight: verifies everything needed by /oauth/exchange is healthy., get, HTTP boundary for the WhatsApp Cloud API webhook., verify_webhook(), decrypt_token() (+4 more)

### Community 64 - "execute_confirmed_action tool"
Cohesion: 0.29
Nodes (8): Admin agent prompt contract, execute_confirmed_action tool, propose_product_change tool, propose_sale_cancellation tool, propose_stock_adjustment tool, propose_transaction tool, Admin write confirmation gate, Admin agent package README

### Community 65 - "Eval Engineering"
Cohesion: 0.18
Nodes (11): 1. Map the Harness and production Environment, 2. Propose eval directions, 3. Draft and approve the specs, 4. Build one Harbor task, 5. Run and audit, 6. Review and repeat, Boundaries, Eval Engineering (+3 more)

### Community 66 - "langgraph-fundamentals/SKILL.md"
Cohesion: 0.18
Nodes (10): Command, Common Fixes, Designing a LangGraph application, Edges, Error Handling, Nodes, Running Graphs: Invoke and Stream, Send API (+2 more)

### Community 67 - "langgraph-human-in-the-loop/SKILL.md"
Cohesion: 0.18
Nodes (10): Approval Workflow, Basic Interrupt + Resume, Command(resume) Warning, Fixes, Multiple Interrupts, Requirements, Side Effects Before Interrupt Must Be Idempotent, Subgraph re-execution on resume (+2 more)

### Community 68 - "LangSmith Online Evaluator API Reference"
Cohesion: 0.18
Nodes (11): 1. Define the response schema, 2. Build and push the prompt, 3. Create the evaluator, Async patterns, Attach evaluator to a project (run rules), Create an LLM-as-judge evaluator, Inspect traces, LangSmith Online Evaluator API Reference (+3 more)

### Community 69 - "services/vision.py"
Cohesion: 0.31
Nodes (8): analyze_product_image(), _clean_str(), _get_client(), _normalize_tags(), Análisis de imágenes de productos con Gemini (autodescripción/etiquetado).…, Cliente genai perezoso (singleton). La API key sale del entorno/config., Devuelve {ai_ok, name, description, tags} sugeridos por Gemini para la imagen., Minúsculas, trim, sin vacíos, sin duplicados, máximo _MAX_TAGS.

### Community 70 - "search_catalog tool (public catalog)"
Cohesion: 0.67
Nodes (3): search_catalog tool (admin view), search_catalog tool (public catalog), storefront.search_catalog (Agno era)

### Community 71 - "product_creation.py"
Cohesion: 0.25
Nodes (9): Single-operation product creation with one required primary image., delete_product_image(), Subida de imágenes de productos a Supabase Storage. Reusa el cliente…, Sube `data` (WebP) al bucket de productos y devuelve su URL pública. El path se…, Upload a WebP and retain its path so callers can compensate on failure., Delete one product image by Storage path., upload_product_image(), upload_product_image_asset() (+1 more)

### Community 87 - "langgraph-persistence/SKILL.md"
Cohesion: 0.20
Nodes (9): Checkpointer Setup, Fixes, Long-Term Memory (Store), Parallel subgraph namespacing, State History & Time Travel, Subgraph Checkpointer Scoping, Thread Management, What You Should NOT Do (+1 more)

### Community 88 - "patch"
Cohesion: 0.21
Nodes (5): Verify Meta's X-Hub-Signature-256 header on webhook POST requests., verify_webhook_signature(), patch, DashboardApiTests, OAuthApiTests

### Community 89 - "_ResponderModel"
Cohesion: 0.29
Nodes (3): BaseChatModel, Contesta con su propia etiqueta, así el test sabe quién atendió el turno., _ResponderModel

### Community 90 - "eval-engineering/SKILL.md"
Cohesion: 0.25
Nodes (3): Calibrate and audit, Harbor wiring, Multi-turn Simulation

### Community 91 - "Evaluator Design"
Cohesion: 0.22
Nodes (9): Access `run` as a dict, Anti-patterns, Code evaluator best practices, Descriptive keys, Evaluator Design, LLM-as-judge vs code: decision framework, Mental verification checklist, Return types (+1 more)

### Community 92 - "Trace Inspection"
Cohesion: 0.22
Nodes (9): Code evaluators: `run["inputs"]` and `run["outputs"]`, Handling variations, Inconsistent schemas, LLM evaluators: `variable_mapping`, Mapping fields to evaluators, Missing outputs, Nested structures, Procedure (+1 more)

### Community 93 - "graphify reference: extra exports and benchmark"
Cohesion: 0.22
Nodes (8): graphify reference: extra exports and benchmark, Step 6b - Wiki (only if --wiki flag), Step 7 - Neo4j export (only if --neo4j or --neo4j-push flag), Step 7a - FalkorDB export (only if --falkordb or --falkordb-push flag), Step 7b - SVG export (only if --svg flag), Step 7c - GraphML export (only if --graphml flag), Step 7d - MCP server (only if --mcp flag), Step 8 - Token reduction benchmark (only if total_words > 5000)

### Community 94 - "supabase.py"
Cohesion: 0.14
Nodes (7): Dobles reutilizables para pruebas sin servicios externos., FakeResult, Implementación mínima en memoria del query builder asíncrono de Supabase., Builder filtrado realista: permite ``eq``/``execute``, no ``select``., StrictFilteredMutation, StrictMutationQuery, StrictSupabase

### Community 95 - "langchain-rag/SKILL.md"
Cohesion: 0.25
Nodes (7): Complete RAG Pipeline, Document Loaders, Retrieval, Text Splitting, Vector Stores, What You CAN Configure, What You CANNOT Configure

### Community 96 - "receive_webhook"
Cohesion: 0.40
Nodes (5): BackgroundTasks, post, Request, Verify and delegate the payload. Always return 200 so Meta does not retry., receive_webhook()

### Community 97 - "routers/erp/clients.py"
Cohesion: 0.23
Nodes (11): ClientCreate, ClientUpdate, create_client(), get_by_phone(), get_by_whatsapp(), list_clients(), get, post (+3 more)

### Community 98 - "ScriptedModel"
Cohesion: 0.25
Nodes (3): BaseChatModel, Emite una lista fija de tool calls, una por vuelta, y después contesta. Se hace…, ScriptedModel

### Community 99 - "Task Design"
Cohesion: 0.29
Nodes (6): Examples, Judge evidence, Rules, Task Design, The contract, Write `task.md`

### Community 100 - "Trace Sourcing"
Cohesion: 0.29
Nodes (7): LangSmith commands, Retrieve traces, Review the batch, Scope, Summarize relevant evidence, Trace Sourcing, Use traces in the eval

### Community 101 - "Verifier Design"
Cohesion: 0.29
Nodes (7): Failure semantics, Match evidence to the outcome, Match validation to use, Test the verifier, Use deterministic gates narrowly, Verifier Design, Write one rubric

### Community 102 - "langchain-fundamentals/SKILL.md"
Cohesion: 0.29
Nodes (6): Agent Configuration Options, Creating Agents with create_agent, Defining Tools, Middleware for Agent Control, Model Configuration, Structured Output

### Community 103 - "Online Eval Engineering"
Cohesion: 0.29
Nodes (7): 1. Inspect traces, 2. Discuss and choose an eval direction, 3. Build one evaluator, 4. Test, attach, and verify, 5. Review with the user, Invariants, Online Eval Engineering

### Community 104 - "client_ip"
Cohesion: 0.48
Nodes (5): client_ip(), Real client IP, honoring X-Forwarded-For first hop (behind Traefik)., _FakeReq, test_falls_back_to_client_host(), test_uses_xff_first_hop()

### Community 105 - "SKILL.md Format"
Cohesion: 0.33
Nodes (5): Directory Structure, SKILL.md Format, SKILL.md Format, What Agents CAN Configure, What Agents CANNOT Configure

### Community 106 - "deep-agents-orchestration/SKILL.md"
Cohesion: 0.33
Nodes (5): Human-in-the-Loop (Approval Workflows), Subagents (Task Delegation), TodoList (Task Planning), What Agents CAN Configure, What Agents CANNOT Configure

### Community 107 - "Harness"
Cohesion: 0.33
Nodes (6): Choose what Harbor runs, Harness, Preserve the production interface, Record the rollout, Sessions and multi-turn runs, Write `harness.md`

### Community 108 - "LLM-as-judge best practices"
Cohesion: 0.33
Nodes (6): Grounded rubrics, LLM-as-judge best practices, One quality per evaluator, Reasoning-first schema, Scoring types, Variable mapping

### Community 109 - "graphify reference: query, path, explain"
Cohesion: 0.33
Nodes (5): For /graphify explain, For /graphify path, graphify reference: query, path, explain, Step 0 — Constrained query expansion (REQUIRED before traversal), Step 1 — Traversal

### Community 110 - "Harbor Task and Run Contract"
Cohesion: 0.40
Nodes (4): Environment and evidence, Harbor Task and Run Contract, Lifecycle, Source and run output

### Community 111 - "langchain-middleware/SKILL.md"
Cohesion: 0.40
Nodes (4): Custom Middleware Hooks, Human-in-the-Loop, What You CAN Configure, What You CANNOT Configure

### Community 112 - "Common field name patterns"
Cohesion: 0.40
Nodes (5): Chatbot / conversational agent, Common field name patterns, Custom chains, RAG / retrieval chain, Tool-calling agent

### Community 114 - "Create a code evaluator"
Cohesion: 0.50
Nodes (4): Create a code evaluator, Create the evaluator, Example: check whether output exists, Function signature

### Community 115 - "List, update, and delete evaluators"
Cohesion: 0.50
Nodes (4): Delete an evaluator, List all evaluators, List, update, and delete evaluators, Update an evaluator

### Community 116 - "graphify reference: add a URL and watch a folder"
Cohesion: 0.50
Nodes (3): For /graphify add, For --watch, graphify reference: add a URL and watch a folder

### Community 117 - "graphify reference: commit hook and native CLAUDE.md integration"
Cohesion: 0.50
Nodes (3): For git commit hook, For native CLAUDE.md integration, graphify reference: commit hook and native CLAUDE.md integration

### Community 118 - "graphify reference: incremental update and cluster-only"
Cohesion: 0.50
Nodes (3): For --cluster-only, For --update (incremental re-extraction), graphify reference: incremental update and cluster-only

### Community 129 - "ingest_webhook"
Cohesion: 0.22
Nodes (11): debounce_bot_response(), ingest_webhook(), log_whatsapp_statuses(), AsyncClient, Start every debounce waiter from one Meta payload concurrently., Coalesce one conversation's message burst before invoking the agent., Ingest all message/status changes contained in one verified Meta payload., run_scheduled_responses() (+3 more)

### Community 130 - "routers/erp/sales.py"
Cohesion: 0.32
Nodes (7): CreateSaleRequest, cancel_sale(), create_sale(), post, Sales endpoints. Thin: validate, delegate to SalesService (atomic RPCs)., get_erp_context(), Dependency for owner-facing ERP endpoints. Reuses Doppel's Supabase Auth flow.

## Knowledge Gaps
- **289 isolated node(s):** `MAX_BATCH_SIZE`, `RESERVED_COLUMNS`, `CachedTable`, `cache`, `Directory Structure` (+284 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **23 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get_supabase()` connect `get_supabase` to `dashboard.py`, `ingest_webhook`, `meta.py`, `turn.py`, `product_creation.py`, `tenant.py`, `supabase_client.py`, `services/erp/export.py`, `whatsapp/webhook.py`, `ERPContext`, `admin_view.py`, `NotFound`, `dependencies.py`, `SalesService`, `app/config.py`?**
  _High betweenness centrality (0.091) - this node is a cross-community bridge._
- **Why does `TenantConfig` connect `TenantConfig` to `ToolContextMiddleware`, `test_admin_deep_agent.py`, `ScriptedModel`, `test_ai_core_tools.py`, `test_ai_core_invariants.py`, `test_public_routing.py`, `bridge.py`, `tenant.py`, `test_turn_outbox.py`, `test_admin_tool_payloads.py`, `ToolContext`, `admin/agent.py`, `test_admin_product_photo.py`, `_ResponderModel`, `FakeSupabase`?**
  _High betweenness centrality (0.066) - this node is a cross-community bridge._
- **Why does `ERPContext` connect `ERPContext` to `routers/erp/clients.py`, `routers/erp/sales.py`, `routers/erp/inventory.py`, `routers/erp/finance.py`, `product_creation.py`, `langfuse.py`, `test_admin_tool_payloads.py`, `services/erp/export.py`, `supabase_client.py`, `ToolContext`, `routers/erp/products.py`, `admin_view.py`, `test_admin_product_photo.py`, `get_supabase`, `test_product_creation.py`, `NotFound`, `SalesService`?**
  _High betweenness centrality (0.050) - this node is a cross-community bridge._
- **Are the 15 inferred relationships involving `TenantConfig` (e.g. with `InputTooLongError` and `MessageWindowMiddleware`) actually correct?**
  _`TenantConfig` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `ToolContext` (e.g. with `TurnOutbox` and `TenantConfig`) actually correct?**
  _`ToolContext` has 3 INFERRED edges - model-reasoned connections that need verification._
- **What connects `MAX_BATCH_SIZE`, `RESERVED_COLUMNS`, `CachedTable` to the rest of the system?**
  _289 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `dashboard.py` be split into smaller, more focused modules?**
  _Cohesion score 0.055501460564751706 - nodes in this community are weakly interconnected._