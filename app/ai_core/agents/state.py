from typing import Annotated
import operator
from typing_extensions import TypedDict


class RouterState(TypedDict):
    messages: Annotated[list[dict], operator.add]
    intent: str
    confidence: float
    redirect_count: int
    selected_specialist: str
