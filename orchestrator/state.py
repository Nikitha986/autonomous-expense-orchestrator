from typing import TypedDict, List, Optional

class OrchestratorState(TypedDict):
    prompt: str
    thread_id: str
    receipts: List[bytes]

    intent: Optional[str]
    trip_name: Optional[str]
    expense_id: Optional[int]

    extracted: List[dict]
    messages: List[str]

    awaiting_info: bool
