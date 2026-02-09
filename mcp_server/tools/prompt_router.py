import re
from typing import List, Optional, Dict, Any
from fastapi import UploadFile
from mcp_server.tools.vision import vision_agent
from mcp_server.tools import db as db_tools
from mcp_server.tools.db import get_connection


def parse_prompt(text: str) -> Dict[str, Any]:
    t = text.lower()
    # upload and file
    if any(k in t for k in ["upload", "file", "file for", "file these", "file receipts"]):
        m = re.search(r"for\s+(?P<loc>\w+)", t)
        loc = m.group("loc") if m else None
        return {"intent": "upload_and_file", "slots": {"location": loc}, "confidence": 0.9}

    # check status (capture word before 'report' more reliably)
    if "status" in t:
        # e.g. "status of my delhi report" or "status for delhi"
        m = re.search(r"(?P<trip>\w+)\s+report", t)
        if not m:
            m = re.search(r"status.*?(?:for|of my)?\s*(?P<trip>\w+)", t)
        trip = m.group("trip") if m else None
        return {"intent": "check_status", "slots": {"trip": trip}, "confidence": 0.9}

    # manager list pending
    if "pending" in t or "pending approvals" in t or "team members" in t:
        return {"intent": "manager_list_pending", "slots": {}, "confidence": 0.9}

    # manager approve
    if "approve" in t:
        m = re.search(r"approve(?: expense)?(?: for)?\s+(?P<name>[a-zA-Z]+)", t)
        name = m.group("name") if m else None
        m_id = re.search(r"id\s*(?P<id>\d+)", t)
        expense_id = int(m_id.group("id")) if m_id else None
        return {"intent": "manager_approve", "slots": {"employee_name": name, "expense_id": expense_id}, "confidence": 0.9}

    return {"intent": "unknown", "slots": {}, "confidence": 0.0}


def _build_trip_status(trip_name: str) -> Optional[Dict[str, Any]]:
    if not trip_name:
        return None
    report = db_tools.get_report_by_trip(trip_name)
    if not report:
        return None
    report_id, status, duplicate_count = report
    rows = db_tools.get_expenses_by_report(report_id)

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

    return {
        "trip": trip_name,
        "status": status,
        "duplicate_count": duplicate_count,
        "expenses": expenses,
        "summary": {"total": len(expenses), "approved": approved_count, "pending": pending_count},
    }


def handle_prompt(prompt: str, receipts: List[bytes], headers: Dict[str, str]) -> Dict[str, Any]:
    parsed = parse_prompt(prompt)
    intent = parsed["intent"]

    # Upload & file -> let upstream graph handle it (signal fallback)
    if intent == "upload_and_file":
        return {"handled": False, "reason": "delegate_to_graph", "parsed": parsed}

    # Check status
    if intent == "check_status":
        trip = parsed["slots"].get("trip")
        result = _build_trip_status(trip)
        if not result:
            return {"handled": True, "response": {"message": f"No report found for '{trip}'", "trip": trip}}
        return {"handled": True, "response": {"message": f"Status for {trip}", "trip_status": result}}

    # Manager: list pending
    if intent == "manager_list_pending":
        role = headers.get("x-user-role", "")
        if role.lower() != "manager":
            return {"handled": True, "response": {"error": "manager_role_required"}}

        # Simple: list all pending expenses
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT e.id, r.employee_name, e.vendor, e.amount, e.status
                    FROM expenses e
                    JOIN expense_reports r ON e.report_id = r.id
                    WHERE e.status != 'APPROVED'
                    ORDER BY r.employee_name
                    LIMIT 200
                    """
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        items = [
            {"expense_id": r[0], "employee": r[1], "vendor": r[2], "amount": float(r[3]), "status": r[4]}
            for r in rows
        ]

        return {"handled": True, "response": {"pending": items}}

    # Manager: approve
    if intent == "manager_approve":
        role = headers.get("x-user-role", "")
        if role.lower() != "manager":
            return {"handled": True, "response": {"error": "manager_role_required"}}

        expense_id = parsed["slots"].get("expense_id")
        employee_name = parsed["slots"].get("employee_name")

        conn = get_connection()
        try:
            with conn.cursor() as cur:
                if expense_id:
                    cur.execute("UPDATE expenses SET status='APPROVED' WHERE id=%s", (expense_id,))
                elif employee_name:
                    # Approve the latest pending expense for this employee
                    cur.execute(
                        """
                        UPDATE expenses
                        SET status='APPROVED'
                        WHERE id IN (
                            SELECT e.id FROM expenses e JOIN expense_reports r ON e.report_id=r.id
                            WHERE r.employee_name ILIKE %s AND e.status != 'APPROVED'
                            ORDER BY e.id DESC LIMIT 1
                        )
                        """,
                        (employee_name + "%",),
                    )
                else:
                    return {"handled": True, "response": {"error": "no_target_specified"}}

                conn.commit()
        finally:
            conn.close()

        return {"handled": True, "response": {"message": "Expense approved"}}

    return {"handled": False, "reason": "unknown_intent", "parsed": parsed}
