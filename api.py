from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
import uuid

from orchestrator.graph import build_orchestrator
from mcp_server.tools.prompt_router import handle_prompt as route_prompt
from mcp_server.tools.db import (
    get_report_by_trip,
    get_expenses_by_report,
    get_connection,
)

# -------------------------------------------------
# APP
# -------------------------------------------------
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------
# GRAPH (UPLOAD PIPELINE ONLY)
# -------------------------------------------------
graph = build_orchestrator()

# -------------------------------------------------
# PROMPT ENDPOINT (UNIFIED COMMAND CENTER)
# -------------------------------------------------
@app.post("/prompt")
async def prompt_endpoint(
    request: Request,
    prompt: Optional[str] = Form(None),
    receipts: Optional[List[UploadFile]] = File(None),
):
    """
    Handles ALL prompt-based actions:
    - Status check
    - Manager actions
    - Upload & file (only case that hits graph)
    """

    # -------------------------------
    # 1️⃣ JSON PROMPT (NO FILES)
    # -------------------------------
    if request.headers.get("content-type", "").startswith("application/json"):
        body = await request.json()
        prompt = body.get("prompt")
        images = []

    # -------------------------------
    # 2️⃣ MULTIPART (PROMPT + FILES)
    # -------------------------------
    else:
        images = [await r.read() for r in receipts] if receipts else []

    headers = {k.lower(): v for k, v in request.headers.items()}

    # -------------------------------
    # 3️⃣ INTENT FIRST (CRITICAL)
    # -------------------------------
    route_result = route_prompt(prompt, images, headers)

    # ✅ If intent is handled → RETURN IMMEDIATELY
    if route_result.get("handled"):
        return route_result["response"]

    # -------------------------------
    # 4️⃣ ONLY UPLOAD FLOWS REACH GRAPH
    # -------------------------------
    if not images:
        return {
            "error": "receipts_required",
            "message": "Please attach receipt files to file expenses."
        }

    state = {
        "prompt": prompt,
        "thread_id": str(uuid.uuid4()),
        "receipts": images,
        "trip_name": None,
        "extracted": [],
        "messages": [],
        "awaiting_trip": False,
        "flagged_count": 0,
    }

    result = graph.invoke(state)

    # Sanitize result before returning to avoid sending raw bytes (receipts)
    safe = {
        "messages": result.get("messages", []),
        "awaiting_trip": result.get("awaiting_trip", False),
        "trip": result.get("trip_name"),
        "extraction_details": result.get("extraction_details", []),
        "processing_steps": result.get("processing_steps", []),
        "flagged_count": result.get("flagged_count", 0),
    }

    # Include a short extraction summary if present
    if result.get("extracted"):
        safe["extracted"] = [
            {
                "vendor": e.get("vendor"),
                "amount": e.get("amount"),
                "date": e.get("date"),
                "confidence": e.get("confidence", 0.0),
                "type": e.get("type", "unknown"),
            }
            for e in result.get("extracted", [])
        ]

    return safe


# -------------------------------------------------
# STATUS API (OPTIONAL – UI POLLING)
# -------------------------------------------------
@app.get("/expenses/status")
def expense_status(trip_name: str):
    report = get_report_by_trip(trip_name)
    if not report:
        return {
            "trip": trip_name,
            "status": "NOT_FOUND",
            "expenses": [],
            "message": f"No report found for '{trip_name}'."
        }

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
            "approved": r[5] == "APPROVED",
        }
        for r in rows
    ]

    approved = sum(1 for e in expenses if e["approved"])
    pending = len(expenses) - approved

    return {
        "trip": trip_name,
        "status": status,
        "expenses": expenses,
        "summary": {
            "total": len(expenses),
            "approved": approved,
            "pending": pending,
        },
    }


# -------------------------------------------------
# MANAGER APPROVAL (DIRECT)
# -------------------------------------------------
@app.post("/manager/approve")
def approve_expense(expense_id: int):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT amount FROM expenses WHERE id=%s", (expense_id,))
        row = cur.fetchone()
        if not row:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="expense_not_found")

        amount = float(row[0] or 0)
        if amount < 5000:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="amount_below_manager_threshold")

        cur.execute("UPDATE expenses SET status='APPROVED' WHERE id=%s", (expense_id,))
        conn.commit()
    finally:
        cur.close()
        conn.close()

    return {"message": "Expense approved"}

@app.post("/manager/reject")
def reject_expense(expense_id: int):
    """Mark an expense as rejected. Simple manager action endpoint."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT amount FROM expenses WHERE id=%s", (expense_id,))
        row = cur.fetchone()
        if not row:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="expense_not_found")

        amount = float(row[0] or 0)
        if amount < 5000:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="amount_below_manager_threshold")

        cur.execute(
            "UPDATE expenses SET status='REJECTED' WHERE id=%s",
            (expense_id,),
        )

        conn.commit()
    finally:
        cur.close()
        conn.close()

    return {"message": "Expense rejected"}


# -------------------------------------------------
# SERVER
# -------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
