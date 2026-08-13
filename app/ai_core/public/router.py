import logging
from textwrap import dedent
from typing import Literal
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from app.ai_core.common.llm import build_chat_model
from app.ai_core.config.tenant import TenantConfig

logger = logging.getLogger(__name__)

# How many recent turn messages the classifier sees. Kept small: intent
# classification needs recent context, not the full history.
ROUTER_CONTEXT_MESSAGES = 10

# Transient provider errors (rate limits, network) are retried here rather than
# with a graph-level RetryPolicy: the node has to survive a final failure and
# fall back to the previous specialist, and a RetryPolicy can only re-run a node
# that raises -- an exception that escapes kills the whole turn.
ROUTER_MAX_ATTEMPTS = 3


class IntentClassification(BaseModel):
    intent: Literal["greeting", "catalog", "objection", "close"] = Field(
        description="Intent of the user's message"
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence of the classification")
    reason: str = Field(description="Brief reason for the classification")

ALLOWED_INTENTS = set(IntentClassification.model_fields["intent"].annotation.__args__)

# Keep the router's knowledge of the swarm next to its output schema.  This is
# deliberately more than a list of labels: the model needs to know what each
# specialist can actually do to make a useful first assignment.
SPECIALIST_PROFILES = {
    "greeting": {
        "agent": "greeter",
        "handles": "a first hello, welcome, and a short question to discover what the customer needs",
        "does_not_handle": "product details, objections, or completing an order",
        "signals": "hello, hi, buenos días, start of a casual conversation without a concrete sales request",
    },
    "catalog": {
        "agent": "catalog",
        "handles": "finding products, product details, prices, categories, and availability using catalog and stock tools",
        "does_not_handle": "persuading through a sales concern or finalizing an order",
        "signals": "what do you have, show me, price, size, color, stock, availability, compare products",
    },
    "objection": {
        "agent": "objection",
        "handles": "sales concerns about price, shipping, quality, trust, policies, or hesitation; it may use catalog and stock facts to answer",
        "does_not_handle": "a straightforward browse request or an already-confirmed checkout",
        "signals": "too expensive, is it worth it, shipping concern, quality concern, can I trust this, hesitation before buying",
    },
    "close": {
        "agent": "closer",
        "handles": "confirming chosen items, checking stock, requesting final confirmation, and creating an order",
        "does_not_handle": "discovery before the customer has selected what to buy",
        "signals": "I want to buy, place my order, checkout, confirm this item, purchase this",
    },
}


def router_view(messages: list) -> list:
    """History the classifier can see, without orphan ``tool_calls``.

    El router no necesita el tráfico de tools, pero no alcanza con filtrar los
    ``ToolMessage``: eso deja un mensaje del asistente cuyos ``tool_calls`` se
    quedan sin respuesta y el proveedor rechaza el request entero con un 400
    ("An assistant message with 'tool_calls' must be followed by tool
    messages"). El par se descarta completo: se van los ``ToolMessage`` y del
    asistente que los pidió se conserva sólo el texto (si tenía).
    """
    view: list = []
    for message in messages:
        if isinstance(message, ToolMessage):
            continue
        if getattr(message, "tool_calls", None):
            text = message.text
            if text:
                view.append(AIMessage(content=text))
            continue
        view.append(message)
    return view


def _classifier_prompt(tenant: TenantConfig) -> str:
    profiles = "\n\n".join(
        dedent(
            f"""\
            Intent: {intent} → specialist: {profile['agent']}
            Handles: {profile['handles']}.
            Does not handle: {profile['does_not_handle']}.
            Strong signals: {profile['signals']}."""
        )
        for intent, profile in SPECIALIST_PROFILES.items()
    )
    return dedent(
        f"""\
        You route incoming customer messages for {tenant.business_name} to one sales specialist.
        Return exactly one of greeting, catalog, objection, or close. Never return a generic,
        fallback, or human category: there is no generalist in this swarm.

        Choose the specialist that should take the next useful action, not merely the first
        keyword you spot. When a message has multiple parts, prioritize close for an explicit
        purchase/checkout request, objection for a concern blocking a purchase, catalog for a
        concrete product or availability question, and greeting only for a pure greeting.
        A vague request should still be assigned to the closest capable specialist (normally
        catalog for product-oriented questions); do not lower confidence simply because the
        wording is informal. Use the full conversation context, especially any selected product
        or unresolved concern.

        Specialist capabilities:
        {profiles}
        """
    )


def _continuity_prompt(active_agent: str) -> str:
    """Bias the classifier towards the specialist already handling the thread.

    The router runs on every turn, so without this a mid-checkout aside ("and in
    red?") reclassifies as `catalog` and drops the customer out of the close.
    This is a bias, not a lock: a clear change of need still moves the turn.
    """
    return dedent(
        f"""\
        The specialist currently handling this conversation is {active_agent}.
        Keep it unless the customer's message clearly asks for something else.
        Continuing an in-flight conversation is worth more than reclassifying on a
        stray word: a request for a detail in the middle of a checkout is still close,
        and a follow-up question while resolving a concern is still objection.
        """
    )


def classify_intent(tenant: TenantConfig):
    """Build the router node: classifies the next specialist for the current turn.

    Returned as a plain node function (matching the ``build_X(tenant) -> node``
    shape used for specialists) so it can be registered directly on the public
    agent's graph, instead of a separately compiled sub-graph. That keeps the
    intent classification call inside the same run as everything else, so it
    inherits the parent's config -- callbacks (Langfuse), recursion budget,
    thread_id -- instead of running as an untracked nested invocation.
    """
    # Thinking is disabled centrally so DeepSeek accepts the specific
    # tool_choice used by function-calling structured output.
    model = build_chat_model("router", temperature=0).with_structured_output(
        IntentClassification, method="function_calling"
    )
    system_prompt = _classifier_prompt(tenant)

    async def node(state) -> dict:
        recent_messages = router_view(state["messages"])[-ROUTER_CONTEXT_MESSAGES:]
        prompts = [SystemMessage(content=system_prompt)]
        # `route_dispatch` has not run yet this turn, so this is still the
        # specialist the previous turn settled on. Absent on a thread's first turn.
        active_agent = state.get("active_agent")
        if active_agent:
            prompts.append(SystemMessage(content=_continuity_prompt(active_agent)))

        for attempt in range(1, ROUTER_MAX_ATTEMPTS + 1):
            try:
                result = await model.ainvoke(prompts + recent_messages)
            except Exception:  # noqa: BLE001 - the turn must survive a dead classifier
                if attempt < ROUTER_MAX_ATTEMPTS:
                    continue
                logger.exception(
                    "Intent classification failed after %d attempts; "
                    "falling back to the previous specialist",
                    ROUTER_MAX_ATTEMPTS,
                )
                # `route_dispatch` reads this as "keep the previous specialist".
                # Raising instead would fail the whole turn, and `bridge.respond`
                # answers a failed turn with silence.
                return {"intent": None, "confidence": None}
            return {"intent": result.intent, "confidence": result.confidence}

    return node
