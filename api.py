from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import List
import uuid

from orchestrator.graph import build_orchestrator
from mcp_server.tools.prompt_router import handle_prompt as route_prompt

from mcp_server.tools.db import (
    get_report_by_trip,
    get_expenses_by_report,
    update_report_status,
    get_connection,
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------
# GRAPH (SINGLE SOURCE OF TRUTH)
# -------------------------------------------------
graph = build_orchestrator()

# Backwards-compatibility: expose graph.invoke on the FastAPI app for legacy tests
try:
    app.invoke = graph.invoke
except Exception:
    pass

# -------------------------------------------------
# PROMPT ENDPOINT (CHAT STYLE)
# -------------------------------------------------
from typing import Optional
from fastapi import Request

@app.post("/prompt")
async def handle_prompt(
    request: Request,
    prompt: Optional[str] = Form(None),
    receipts: Optional[List[UploadFile]] = File(None),
):
    # -----------------------------------
    # 1️⃣ JSON BODY (prompt-only)
    # -----------------------------------
    if request.headers.get("content-type", "").startswith("application/json"):
        body = await request.json()
        prompt = body.get("prompt")
        receipts = []

    # -----------------------------------
    # 2️⃣ MULTIPART (prompt + files)
    # -----------------------------------
    images = [await r.read() for r in receipts] if receipts else []

    # -----------------------------------
    # 3️⃣ HEADER PASS-THROUGH (manager mode)
    # -----------------------------------
    headers = {k.lower(): v for k, v in request.headers.items()}

    # Prompt router (status / manager commands)
    route_result = route_prompt(prompt, images, headers)
    if route_result.get("handled"):
        return route_result["response"]

    # -----------------------------------
    # 4️⃣ ORCHESTRATOR GRAPH
    # -----------------------------------
    state = {
        "prompt": prompt,
        "thread_id": str(uuid.uuid4()),
        "receipts": images,
        "intent": None,
        "trip_name": None,
        "extracted": [],
        "messages": [f"You: {prompt}"],
        "awaiting_trip": False,
        "flagged_count": 0,
    }

    result = graph.invoke(state)

    trip_name = result.get("trip_name")
    enriched = _build_trip_status(trip_name) if trip_name else None

    return {
        "messages": result["messages"],
        "awaiting_trip": result["awaiting_trip"],
        "trip": trip_name,
        "status": enriched["status"] if enriched else None,
        "summary": enriched["summary"] if enriched else None,
        "expenses": enriched["expenses"] if enriched else [],
    }


# -------------------------------------------------
# FILE EXPENSES ENDPOINT (USED BY FRONTEND)
# -------------------------------------------------
@app.post("/expenses/file")
async def file_expenses(
    prompt: str = Form(...),
    trip_name: str = Form(default=None),
    receipts: List[UploadFile] = File(default=[]),
):
    images = [await r.read() for r in receipts]

    thread_id = str(uuid.uuid4())

    state = {
        "prompt": prompt,
        "thread_id": thread_id,
        "receipts": images,
        "intent": None,
        "trip_name": trip_name,
        "extracted": [],
        "extraction_details": [],
        "processing_steps": [],
        "messages": [f"You: {prompt}"],
        "awaiting_trip": False,
        "flagged_count": 0,
    }

    result = graph.invoke(state)

    final_trip = result.get("trip_name")

    enriched = _build_trip_status(final_trip) if final_trip else None

    return {
        "messages": result["messages"],
        "awaiting_trip": result["awaiting_trip"],
        "trip": final_trip,
        "status": enriched["status"] if enriched else None,
        "duplicate_count": enriched["duplicate_count"] if enriched else 0,
        "expenses": enriched["expenses"] if enriched else [],
        "summary": enriched["summary"] if enriched else None,
        "extraction_details": result.get("extraction_details", []),
    }


# -------------------------------------------------
# STATUS API (USED BY UI POLLING)
# -------------------------------------------------
@app.get("/expenses/status")
def expense_status(trip_name: str):
    enriched = _build_trip_status(trip_name)

    if not enriched:
        return {
            "trip": trip_name,
            "status": "NOT_FOUND",
            "duplicate_count": 0,
            "expenses": [],
            "message": f"No expenses found for '{trip_name}'. Try filing some first.",
        }

    return enriched


# -------------------------------------------------
# INTERNAL: BUILD FULL TRIP STATUS (SINGLE FORMAT)
# -------------------------------------------------
def _build_trip_status(trip_name: str):
    report = get_report_by_trip(trip_name)
    if not report:
        return None

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

    return {
        "trip": trip_name,
        "status": status,
        "duplicate_count": duplicate_count,
        "expenses": expenses,
        "summary": {
            "total": len(expenses),
            "approved": approved_count,
            "pending": pending_count,
        },
        "message": f"Agent: {' | '.join(msg_parts)}",
    }


# -------------------------------------------------
# MANAGER APPROVAL
# -------------------------------------------------
@app.post("/manager/approve")
def approve_expense(expense_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "UPDATE expenses SET status='APPROVED' WHERE id=%s",
        (expense_id,),
    )

    conn.commit()
    cur.close()
    conn.close()

    return {"message": "Expense approved"}


# -------------------------------------------------
# SERVER STARTUP
# -------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
