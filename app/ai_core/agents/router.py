from textwrap import dedent
from typing import Literal
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command, RetryPolicy
from app.ai_core.agents.llm import build_chat_model
from app.ai_core.agents.state import RouterState
from app.ai_core.config.tenant import TenantConfig

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
        "handles": "finding products, product details, prices, variants, categories, and availability using catalog and stock tools",
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


def _message_to_langchain(msg):
    """Normalize a message dict or BaseMessage into a LangChain message for the router."""
    if isinstance(msg, BaseMessage):
        return msg
    role = msg.get("role") or msg.get("type")
    content = msg.get("content", "")
    if role in ("assistant", "ai"):
        return AIMessage(content=content)
    if role == "tool":
        return ToolMessage(content=str(content), tool_call_id=msg.get("tool_call_id", ""))
    return HumanMessage(content=content)


def build_router_graph(tenant: TenantConfig):
    # Thinking is disabled centrally so DeepSeek accepts the specific
    # tool_choice used by function-calling structured output.
    model = build_chat_model("router", temperature=0).with_structured_output(
        IntentClassification, method="function_calling"
    )

    def classify_intent(state: RouterState):
        system_prompt = _classifier_prompt(tenant)
        messages = [SystemMessage(content=system_prompt)] + [
            _message_to_langchain(msg) for msg in state["messages"]
        ]
        result = model.invoke(messages)
        return {
            "intent": result.intent,
            "confidence": result.confidence,
        }

    def confidence_check(state: RouterState):
        # Confidence is recorded for observability, not used to force a weak
        # generic fallback. The classifier must select the closest specialist.
        return {}

    def dispatch(state: RouterState) -> Command[Literal["__end__"]]:
        return Command(update={"selected_specialist": state["intent"]}, goto=END)

    builder = StateGraph(RouterState)
    # Transient provider errors (rate limits, network) retry instead of
    # failing the customer's turn.
    builder.add_node("classify_intent", classify_intent, retry_policy=RetryPolicy(max_attempts=3))
    builder.add_node("confidence_check", confidence_check)
    builder.add_node("dispatch", dispatch)

    builder.add_edge(START, "classify_intent")
    builder.add_edge("classify_intent", "confidence_check")
    builder.add_edge("confidence_check", "dispatch")

    return builder.compile()
