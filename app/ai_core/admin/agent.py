import logging
import time
import uuid
from typing import Any

from deepagents import (
    FilesystemMiddleware,
    HarnessProfile,
    create_deep_agent,
    register_harness_profile,
)
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from deepagents.middleware.filesystem import FilesystemPermission
from deepagents.profiles.harness.harness_profiles import GeneralPurposeSubagentProfile
from langchain.agents.middleware import TodoListMiddleware
from langchain_core.messages import AIMessage, HumanMessage

from app.ai_core.admin.tools import ADMIN_TOOLS
from app.ai_core.common.llm import build_chat_model, resolve_model_name
from app.ai_core.common.middleware import (
    InputTooLongError,
    sanitize_user_input,
    specialist_middleware,
)
from app.ai_core.common.prompts import allowed_tools_for, load_prompt
from app.ai_core.channel.outbox import TurnRuntime
from app.ai_core.config.tenant import TenantConfig
from app.ai_core.observability.langfuse import (
    invocation_config,
    trace_attributes,
)
from app.ai_core.observability.tracing import trace_turn
from app.ai_core.persistence.checkpointer import open_checkpointer
from app.ai_core.persistence.store import open_store

logger = logging.getLogger(__name__)

# Ruta del filesystem virtual que queda respaldada por el Store (persistente entre
# conversaciones). Todo lo que no empiece con esto cae al `StateBackend`, que sí se
# serializa al checkpoint — por eso `_MEMORY_PERMISSIONS` prohíbe escribir afuera.
MEMORY_ROUTE = "/memories/"
MEMORY_FILE = f"{MEMORY_ROUTE}AGENTS.md"

# Primera regla que matchea gana. Escribir sólo dentro de `/memories/`: fuerza que todo lo
# que el agente guarde vaya al Store namespaceado por tenant, y de paso impide que engorde
# el checkpoint (el `StateBackend` se serializa entero en cada paso del grafo).
_MEMORY_PERMISSIONS = [
    FilesystemPermission(operations=["write"], paths=[f"{MEMORY_ROUTE}**"], mode="allow"),
    FilesystemPermission(operations=["write"], paths=["/**"], mode="deny"),
]

# Tools de filesystem que ve el modelo. `glob`/`grep`/`delete` no aportan sobre un único
# archivo de notas, y `execute` (shell) ni siquiera se registraría porque el backend no
# implementa `SandboxBackendProtocol` — se listan explícitamente igual para que la
# superficie quede fija y no dependa de los defaults de deepagents.
_FS_TOOLS = ["ls", "read_file", "write_file", "edit_file"]

# `create_deep_agent` no expone estas dos decisiones como parámetros, así que van por el
# registry de harness profiles. OJO: `register_harness_profile` es un registry GLOBAL de
# proceso keyeado por proveedor, no config por agente. Hoy es inocuo porque el admin es el
# único que corre sobre deepagents; si el agente público migra, hereda esto.
#
# - Sin `SummarizationMiddleware`: reescribe el historial con un resumen generado por LLM.
#   Es una llamada extra al modelo por turno, se pisa con `MessageWindowMiddleware` que ya
#   acota el prompt, y puede borrar el `HumanMessage` cuyo id usa `run_admin_agent_turn`
#   para recortar `turn_messages`.
# - Sin subagente general-purpose: sin él tampoco se registra la tool `task`. El admin no
#   delega, y un subagente genérico con las tools ERP del dueño es superficie sin beneficio.
register_harness_profile(
    "deepseek",
    HarnessProfile(
        excluded_middleware={"SummarizationMiddleware"},
        general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
    ),
)

_INPUT_TOO_LONG_RESPONSE = (
    "El mensaje es demasiado largo. Envíalo en partes más cortas. / "
    "The message is too long. Send it in shorter parts."
)
_EMPTY_INPUT_RESPONSE = "Mensaje vacío. / Empty message."


def memory_namespace(tenant_id: str) -> tuple[str, ...]:
    """Store namespace holding one tenant's admin memories."""
    return (tenant_id, "admin", "memories")


def _namespace_factory(tenant_id: str):
    """Build the `StoreBackend` namespace factory for one tenant.

    **This is the multi-tenant isolation boundary, so it is worth being precise about why it
    holds.** Every `StoreBackend` operation resolves its namespace through this callable and
    hands the resulting tuple to the store (`store.aget(namespace, file_path)`). The model
    controls `file_path` — the key *inside* the namespace — and nothing else. There is no
    tool argument, state field, or message text that reaches the tuple, so a prompt injection
    cannot move the agent into another tenant's namespace. Path traversal does not help
    either: `/memories/../../otro/x` is routed by prefix, stripped to `/../../otro/x`, and
    looked up as a literal key in the *same* namespace.

    The tenant is captured here at build time rather than read from the runtime, because
    `bridge._get_or_build_agent` already caches one agent per `(tenant_id, role)` keyed to a
    config fingerprint — exactly like the system prompt and the tool allow-list. That makes
    the namespace a property of the agent instance instead of something that has to survive
    the trip through `context=`.

    The runtime check below is defence in depth for the one way that could still go wrong: a
    caching bug handing tenant B's turn to tenant A's agent. It fails loudly instead of
    silently reading the wrong tenant's memories.
    """

    namespace = memory_namespace(tenant_id)

    def factory(runtime) -> tuple[str, ...]:
        turn_tenant = getattr(getattr(runtime, "context", None), "tenant_id", "")
        # Empty means the graph was invoked without a `TurnRuntime` (tests, CLI): there is
        # nothing to cross-check against, and the build-time tenant is still authoritative.
        if turn_tenant and turn_tenant != tenant_id:
            raise RuntimeError(
                "Admin memory namespace mismatch: agent built for tenant "
                f"{tenant_id!r} but invoked for tenant {turn_tenant!r}. Refusing to touch "
                "the store."
            )
        return namespace

    return factory


async def build_admin_agent(tenant: TenantConfig):
    system_prompt = load_prompt(tenant, "admin", "admin_agent")
    tools = allowed_tools_for(tenant, "admin", ADMIN_TOOLS)
    model = build_chat_model("admin", temperature=0.3)
    checkpointer = await open_checkpointer()
    store = await open_store()

    # `/memories/` -> Store (persistente, namespaceado por tenant). Todo lo demás -> state
    # del grafo (efímero por thread), aunque `_MEMORY_PERMISSIONS` lo deja de sólo lectura.
    backend = CompositeBackend(
        default=StateBackend(),
        routes={
            MEMORY_ROUTE: StoreBackend(
                store=store,
                namespace=_namespace_factory(tenant.tenant_id),
            ),
        },
    )

    agent = create_deep_agent(
        name="admin_agent",
        model=model,
        system_prompt=system_prompt,
        tools=tools,
        backend=backend,
        checkpointer=checkpointer,
        store=store,
        permissions=_MEMORY_PERMISSIONS,
        context_schema=TurnRuntime,
        middleware=[
            # `create_deep_agent` NO trae planning: `write_todos` sale de langchain y hay
            # que sumarlo a mano (verificado en deepagents 0.7.5 y en la doc oficial).
            TodoListMiddleware(),
            # Reemplaza a la `FilesystemMiddleware` built-in: `_apply_custom_middleware`
            # matchea por `.name` y hace replace in-place. Es la única forma de acotar
            # `tools=` y de apagar el eviction automático de resultados grandes a archivo,
            # que escribiría fuera de `/memories/` sin pasar por los permisos.
            FilesystemMiddleware(
                backend=backend,
                tools=_FS_TOOLS,
                tool_token_limit_before_evict=None,
                _permissions=_MEMORY_PERMISSIONS,
            ),
            *specialist_middleware(tenant, "admin"),
        ],
    )

    return agent


async def run_admin_agent_turn(
    agent,
    tenant: TenantConfig,
    thread_id: str,
    user_message: str,
    message_id: str | None = None,
    confirmed_action_id: str | None = None,
    images: list[dict] | None = None,
) -> dict[str, Any]:
    """Run one admin turn with input guardrails and per-turn tracing.

    Mirrors the public agent's entry point so both roles get the same
    robustness (sanitized input) and observability (trace per turn).
    """
    try:
        user_message = sanitize_user_input(user_message)
    except InputTooLongError:
        logger.info("Rejected over-long admin message on thread %s", thread_id)
        return {"messages": [AIMessage(content=_INPUT_TOO_LONG_RESPONSE)]}
    if not user_message:
        return {"messages": [AIMessage(content=_EMPTY_INPUT_RESPONSE)]}

    # See `run_public_agent_turn`: the graph message id is per invocation, the
    # turn id is stable across a redelivery of the same inbound message.
    turn_id = message_id or str(uuid.uuid4())
    message_id = str(uuid.uuid4())
    turn_runtime = TurnRuntime(tenant_id=tenant.tenant_id)
    start = time.time()
    run_name = "admin-support-turn"
    with trace_attributes(
        thread_id=thread_id,
        tenant_id=tenant.tenant_id,
        role="admin",
        run_name=run_name,
    ):
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=user_message, id=message_id)]},
            config=invocation_config(thread_id, run_name, turn_id=turn_id,
                                     confirmed_action_id=confirmed_action_id, images=images),
            context=turn_runtime,
        )
    latency_ms = int((time.time() - start) * 1000)

    messages = list(result.get("messages", []))
    turn_start = next(
        (
            index
            for index, message in enumerate(messages)
            if getattr(message, "id", None) == message_id
        ),
        max(len(messages) - 1, 0),
    )
    turn_messages = messages[turn_start:]
    last_message = turn_messages[-1] if turn_messages else None
    output_text = (
        last_message.content
        if last_message is not None and hasattr(last_message, "content")
        else ""
    )

    try:
        await trace_turn(
            tenant=tenant,
            thread_id=thread_id,
            role="admin",
            subagent="admin_agent",
            model=resolve_model_name("admin"),
            input_text=user_message,
            output_text=output_text,
            tokens=0,
            tools_called="[]",
            latency_ms=latency_ms,
        )
    except Exception as exc:  # noqa: BLE001 - tracing must never fail an admin turn
        logger.warning("Admin turn tracing failed: %s", exc)

    return {
        **result,
        "messages": turn_messages,
        "channel_actions": turn_runtime.outbox.drain(),
    }
