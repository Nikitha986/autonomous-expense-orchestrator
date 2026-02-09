
from typing import TypedDict, List, Optional, Dict, Any
from langgraph.graph import StateGraph, END
import re

from mcp_server.tools.vision import vision_agent
from mcp_server.tools.db import (
    get_or_create_report,
    add_expense,
    is_duplicate,
    update_report_status,
    get_report_by_trip,
    get_expenses_by_report,
    save_orchestrator_state,
    load_orchestrator_state,
)
from mcp_server.tools.policy import apply_policy

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
    
    extraction_details: List[dict]  # [{vendor, amount, date, type, status}]
    processing_steps: List[dict]    # [{step, status, details}]


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


def router(state: OrchestratorState):

    if "extraction_details" not in state or not isinstance(state.get("extraction_details"), list):
        state["extraction_details"] = []
    if "processing_steps" not in state or not isinstance(state.get("processing_steps"), list):
        state["processing_steps"] = []
   
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
        # If user is asking for status, answer without receipts
        prompt_l = state.get("prompt", "").lower()
        if "status" in prompt_l:
            trip = extract_trip(state.get("prompt", ""))
            def router(state):
                # ✅ Allow prompt-only flows (status / manager / approve)
                if not state["receipts"]:
                    return state

                if not state.get("trip_name"):
                    trip = extract_trip(state["prompt"])
                    if not trip:
                        state["awaiting_trip"] = True
                        state["messages"].append(
                            f"Agent: I have {len(state['receipts'])} receipt(s). Which trip should I file them under?"
                        )
                        return state

                    state["trip_name"] = f"{trip} Trip"

                state["messages"].append(
                    f"Agent: Processing {len(state['receipts'])} receipt(s) for **{state['trip_name']}**..."
                )
                return state


            trip_name = f"{trip} Trip"
            report = get_report_by_trip(trip_name.strip().lower())
            if not report:
                state["messages"].append(f"Agent: No report found for '{trip_name}'.")
                return state

            report_id, status, duplicate_count = report
            rows = get_expenses_by_report(report_id)

            expenses = [
                {
                    "expense_id": r[0],
                    "expense_date": r[1].isoformat() if r[1] else None,
                    "vendor": r[2],
                    "amount": float(r[3]),
                    "category": r[4],
                    "status": r[5],
                    "ocr_text": r[6],
                    "approved": r[5] == "APPROVED",
                }
                for r in rows
            ]

            approved_count = sum(1 for e in expenses if e["approved"])
            pending_count = len(expenses) - approved_count

            msg_parts = [f"**{trip_name}**: {len(expenses)} total"]
            if approved_count:
                msg_parts.append(f"{approved_count} approved")
            if pending_count:
                msg_parts.append(f"{pending_count} pending")
            if duplicate_count:
                msg_parts.append(f"{duplicate_count} duplicates")

            state["messages"].append(f"Agent: {' | '.join(msg_parts)}")
            return state

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


def vision(state: OrchestratorState):
    extracted = []
    extraction_details = []

    for idx, img in enumerate(state["receipts"], 1):
        try:
            result = vision_agent(img)
            extracted.append(result)

            # If vision extracted an employee name and state doesn't have one yet, set it
            try:
                emp = result.get("employee_name")
                if emp and not state.get("employee_name"):
                    state["employee_name"] = emp
            except Exception:
                pass
            
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

    extraction_details = state.get("extraction_details", [])
    
    for idx, item in enumerate(state["extracted"], 1):
        vendor = item.get("vendor") or "UNKNOWN"
        amount = item.get("amount") or 0.0
        raw_date = item.get("date")

      
        if not raw_date or raw_date in ("NA", "N/A", "UNKNOWN", "", "0000-00-00"):
            date = None
        else:
            date = raw_date

        text = item.get("text", "")
        confidence = item.get("confidence", 0.0)


        if amount <= 0 and confidence < 0.25 and not text.strip():
            skipped += 1
            if idx <= len(extraction_details):
                extraction_details[idx - 1]["status"] = "SKIPPED"
            continue

  
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

    update_report_status(report_id, "COMPLETED")

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

    compiled = g.compile()

    class OrchestratorWrapper:
        def __init__(self, compiled_graph):
            self._compiled = compiled_graph

        def _load(self, thread_id: Optional[str], state: OrchestratorState):
            if not thread_id:
                return state
            try:
                stored = load_orchestrator_state(thread_id)
            except Exception:
                stored = None
            if not stored:
                return state

            # Merge lists conservatively: prefer new receipts if provided, otherwise reuse stored
            if not state.get("receipts") and stored.get("receipts"):
                state["receipts"] = stored.get("receipts")

            for key in ("extracted", "extraction_details", "messages", "trip_name", "awaiting_trip", "flagged_count", "employee_name"):
                if not state.get(key) and stored.get(key) is not None:
                    state[key] = stored.get(key)

            return state

        def _save(self, thread_id: Optional[str], state: OrchestratorState):
            if not thread_id:
                return
            try:
                # Persist a small subset of the state
                payload = {
                    "receipts": state.get("receipts", []),
                    "extracted": state.get("extracted", []),
                    "extraction_details": state.get("extraction_details", []),
                    "messages": state.get("messages", []),
                    "trip_name": state.get("trip_name"),
                    "awaiting_trip": state.get("awaiting_trip"),
                    "flagged_count": state.get("flagged_count", 0),
                    "employee_name": state.get("employee_name"),
                }
                # If processing completed (no receipts left), clear receipts to avoid reprocessing
                if not state.get("receipts"):
                    payload["receipts"] = []
                save_orchestrator_state(thread_id, payload)
            except Exception:
                pass

        def invoke(self, state: OrchestratorState):
            thread_id = state.get("thread_id")
            state = self._load(thread_id, state)

            result = self._compiled.invoke(state)

            # Save back important pieces for future calls
            try:
                self._save(thread_id, result)
            except Exception:
                pass

            return result

    return OrchestratorWrapper(compiled)
