# orchestrator/graph.py
from typing import TypedDict, List, Optional
from langgraph.graph import StateGraph, END
import re

from mcp_server.tools.vision import vision_agent
from mcp_server.tools.db import (
    get_or_create_report,
    add_expense,
    is_duplicate,
    update_report_status,   # ✅ import here
)
from mcp_server.tools.policy import apply_policy


# -----------------------------
# STATE
# -----------------------------
class OrchestratorState(TypedDict):
    prompt: str
    thread_id: str
    receipts: List[bytes]

    trip_name: Optional[str]
    employee_name: Optional[str]
    extracted: List[dict]

    messages: List[str]
    awaiting_trip: bool
    flagged_count: int
    
    # ✅ NEW: Track processing details for frontend
    extraction_details: List[dict]  # [{vendor, amount, date, type, status}]
    processing_steps: List[dict]    # [{step, status, details}]


# -----------------------------
# HELPERS
# -----------------------------
def extract_trip(prompt: str) -> Optional[str]:
    match = re.search(
        r"(?:for|to)\s+(?:my\s+)?(.+?)\s*(?:trip|report)?$",
        prompt,
        re.I,
    )
    if match:
        return match.group(1).strip().title()

    match = re.search(r"\b(\w+)\s+trip\b", prompt, re.I)
    if match:
        return match.group(1).strip().title()

    return None


# -----------------------------
# ROUTER
# -----------------------------
def router(state: OrchestratorState):
    # ✅ Initialize collections if they don't exist
    if "extraction_details" not in state or not isinstance(state.get("extraction_details"), list):
        state["extraction_details"] = []
    if "processing_steps" not in state or not isinstance(state.get("processing_steps"), list):
        state["processing_steps"] = []
    # Ensure basic keys exist to support minimal test state
    if "messages" not in state or not isinstance(state.get("messages"), list):
        state["messages"] = []
    if "awaiting_trip" not in state:
        state["awaiting_trip"] = False
    if "flagged_count" not in state:
        state["flagged_count"] = 0
    if "receipts" not in state or state.get("receipts") is None:
        state["receipts"] = []
    if "extracted" not in state or state.get("extracted") is None:
        state["extracted"] = []
    
    if not state["receipts"]:
        state["messages"].append(
            "Agent: I don’t see any receipts attached. Please add receipt images first."
        )
        return state

    if not state.get("trip_name"):
        trip = extract_trip(state["prompt"])
        if not trip:
            state["awaiting_trip"] = True
            state["messages"].append(
                f"Agent: I have {len(state['receipts'])} receipt(s) ready. Which trip should I file them under?"
            )
            return state

        state["trip_name"] = f"{trip} Trip"

    state["messages"].append(
        f"Agent: Processing {len(state['receipts'])} receipt(s) for **{state['trip_name']}**..."
    )
    return state


# -----------------------------
# VISION
# -----------------------------
def vision(state: OrchestratorState):
    extracted = []
    extraction_details = []

    for idx, img in enumerate(state["receipts"], 1):
        try:
            result = vision_agent(img)
            extracted.append(result)
            
            # ✅ Track extraction details for frontend
            extraction_details.append({
                "receipt_id": idx,
                "vendor": result.get("vendor"),
                "amount": result.get("amount"),
                "date": result.get("date"),
                "type": result.get("type", "unknown"),
                "status": "EXTRACTED",
            })
        except Exception as e:
            result = {
                "vendor": None,
                "amount": None,
                "date": None,
                "confidence": 0.0,
                "text": f"OCR failed for receipt {idx}: {str(e)[:100]}",
                "type": "failed",
            }
            extracted.append(result)
            extraction_details.append({
                "receipt_id": idx,
                "vendor": None,
                "amount": None,
                "date": None,
                "type": "failed",
                "status": "FAILED",
            })

    return {
        "extracted": extracted,
        "extraction_details": extraction_details,
    }


# -----------------------------
# POLICY + DB
# -----------------------------
def policy_db(state: OrchestratorState):
    if state.get("awaiting_trip"):
        return state

    report_id = get_or_create_report(
        trip_name=state["trip_name"],
        employee_name=state.get("employee_name"),
        thread_id=state["thread_id"],
    )

    filed = 0
    flagged = 0
    skipped = 0

    # ✅ Keep original extraction details and just update status
    extraction_details = state.get("extraction_details", [])
    
    for idx, item in enumerate(state["extracted"], 1):
        vendor = item.get("vendor") or "UNKNOWN"
        amount = item.get("amount") or 0.0
        raw_date = item.get("date")

        # ✅ HARD sanitize date for PostgreSQL
        if not raw_date or raw_date in ("NA", "N/A", "UNKNOWN", "", "0000-00-00"):
            date = None
        else:
            date = raw_date

        text = item.get("text", "")
        confidence = item.get("confidence", 0.0)

        # Skip totally unreadable receipts
        if amount <= 0 and confidence < 0.25 and not text.strip():
            skipped += 1
            if idx <= len(extraction_details):
                extraction_details[idx - 1]["status"] = "SKIPPED"
            continue

        # Duplicate check (only if amount exists)
        if amount > 0 and is_duplicate(report_id, vendor, amount, date):
            skipped += 1
            if idx <= len(extraction_details):
                extraction_details[idx - 1]["status"] = "DUPLICATE"
            continue

        policy = apply_policy(item)

        add_expense(
            report_id=report_id,
            expense_date=date,
            vendor=vendor,
            amount=amount,
            category=policy["category"],
            status=policy["status"],
            ocr_text=text,
        )

        # ✅ Update only the status in extraction_details
        if idx <= len(extraction_details):
            if policy.get("requires_review"):
                extraction_details[idx - 1]["status"] = "FLAGGED"
                flagged += 1
                state["messages"].append(
                    f"⚠️ FLAGGED: {vendor} — ₹{amount:.2f}"
                )
            else:
                extraction_details[idx - 1]["status"] = "APPROVED"
                filed += 1

    state["extraction_details"] = extraction_details
    state["flagged_count"] = flagged

    # ✅ Persist FINAL status in DB
    update_report_status(report_id, "COMPLETED")

    # Final user-facing output
    state["messages"].append(
        f"Agent: Processing completed for **{state['trip_name']}**."
    )
    state["messages"].append(
        f"Agent: Status set to **COMPLETED**."
    )

    summary_parts = []
    if filed:
        summary_parts.append(f"{filed} filed")
    if flagged:
        summary_parts.append(f"{flagged} flagged")
    if skipped:
        summary_parts.append(f"{skipped} skipped")

    if summary_parts:
        state["messages"].append(
            f"Agent: Summary → " + " | ".join(summary_parts)
        )

    return state


# -----------------------------
# BUILD GRAPH
# -----------------------------
def build_orchestrator():
    g = StateGraph(OrchestratorState)

    g.add_node("router", router)
    g.add_node("vision", vision)
    g.add_node("policy_db", policy_db)

    g.set_entry_point("router")

    def should_continue(state: OrchestratorState):
        if state.get("awaiting_trip") or not state.get("receipts"):
            return END
        return "vision"

    g.add_conditional_edges(
        "router",
        should_continue,
        {
            END: END,
            "vision": "vision",
        },
    )

    g.add_edge("vision", "policy_db")
    g.add_edge("policy_db", END)

    return g.compile()
