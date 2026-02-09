import re
from typing import List, Dict, Any, Optional
from mcp_server.tools import db as db_tools
from mcp_server.tools.db import get_connection


# -------------------------------------------------
# PROMPT PARSER
# -------------------------------------------------
def parse_prompt(text: str) -> Dict[str, Any]:
    t = text.lower().strip()

    # -----------------------------
    # FILE / UPLOAD
    # -----------------------------
    if any(k in t for k in ["upload", "file", "file these", "file receipts", "upload these"]):
        m = re.search(r"for\s+(?P<trip>\w+)", t)
        trip = m.group("trip") if m else None
        return {
            "intent": "upload_and_file",
            "slots": {"trip": trip},
            "confidence": 0.9,
        }

    # -----------------------------
    # CHECK STATUS (FIXED)
    # -----------------------------
    if "status" in t:
        # Matches:
        # - "education trip"
        # - "delhi report"
        # - "status of my delhi"
        m = re.search(r"(?P<trip>\w+)\s+(trip|report)", t)
        if not m:
            m = re.search(r"status.*?(?:for|of my)?\s*(?P<trip>\w+)", t)

        trip = m.group("trip") if m else None
        return {
            "intent": "check_status",
            "slots": {"trip": trip},
            "confidence": 0.9,
        }

    # -----------------------------
    # MANAGER: LIST PENDING
    # -----------------------------
    if any(k in t for k in ["pending", "team members", "pending expenses"]):
        # capture optional trip name: 'pending expenses for education trip'
        m = re.search(r"(?:for|of|in)\s+(?P<trip>\w+)", t)
        trip = m.group("trip") if m else None
        return {
            "intent": "manager_list_pending",
            "slots": {"trip": trip},
            "confidence": 0.9,
        }

    # -----------------------------
    # MANAGER: APPROVE
    # -----------------------------
    if "approve" in t:
        # capture multi-word names (e.g., 'approve expense for Rajesh Kumar')
        m_name = re.search(r"approve(?: expense)?(?: for)?\s+(?P<name>[a-zA-Z][a-zA-Z\s'.-]{0,60})", t)
        m_id = re.search(r"id\s*(?P<id>\d+)", t)

        return {
            "intent": "manager_approve",
            "slots": {
                "employee_name": m_name.group("name") if m_name else None,
                "expense_id": int(m_id.group("id")) if m_id else None,
            },
            "confidence": 0.9,
        }

    return {
        "intent": "unknown",
        "slots": {},
        "confidence": 0.0,
    }


# -------------------------------------------------
# BUILD STATUS RESPONSE
# -------------------------------------------------
def _build_trip_status(trip_name: Optional[str]) -> Optional[Dict[str, Any]]:
    if not trip_name:
        return None
    # Try several normalized variants so queries like "education" match
    # stored report names like "Education Trip".
    candidates = []
    t = trip_name.strip()
    if t:
        candidates.append(t)
        candidates.append(t.title())
        if not t.lower().endswith("trip"):
            candidates.append(f"{t} Trip")
            candidates.append(f"{t.title()} Trip")

    # Deduplicate while preserving order
    seen = set()
    candidates = [c for c in candidates if c and not (c in seen or seen.add(c))]

    report = None
    used_name = None
    for cand in candidates:
        report = db_tools.get_report_by_trip(cand)
        if report:
            used_name = cand
            break

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
            "approved": r[5] == "APPROVED",
        }
        for r in rows
    ]

    approved = sum(1 for e in expenses if e["approved"])
    pending = len(expenses) - approved

    return {
        "trip": used_name or trip_name,
        "status": status,
        "duplicate_count": duplicate_count,
        "expenses": expenses,
        "summary": {
            "total": len(expenses),
            "approved": approved,
            "pending": pending,
        },
    }


# -------------------------------------------------
# MAIN ROUTER
# -------------------------------------------------
def handle_prompt(
    prompt: str,
    receipts: List[bytes],
    headers: Dict[str, str],
) -> Dict[str, Any]:

    parsed = parse_prompt(prompt)
    intent = parsed["intent"]

    # -----------------------------
    # FILE → Let LangGraph handle
    # -----------------------------
    if intent == "upload_and_file":
        return {
            "handled": False,
            "reason": "delegate_to_graph",
            "parsed": parsed,
        }

    # -----------------------------
    # STATUS (NO FILES REQUIRED)
    # -----------------------------
    if intent == "check_status":
        trip = parsed["slots"].get("trip")
        if trip:
            trip = trip.strip().lower() 
        result = _build_trip_status(trip)

        if not result:
            return {
                "handled": True,
                "response": {
                    "message": f"No report found for '{trip}'",
                    "trip": trip,
                },
            }

        return {
            "handled": True,
            "response": {
                "message": f"Status for {trip}",
                "trip_status": result,
            },
        }

    # -----------------------------
    # MANAGER: LIST PENDING
    # -----------------------------
    if intent == "manager_list_pending":
        # Debug: log incoming headers and parsed slots
        print(f"[prompt_router] manager_list_pending parsed={parsed} headers_keys={[k for k in headers.keys()]}")

        if headers.get("x-user-role", "").lower() != "manager":
            return {
                "handled": True,
                "response": {"error": "manager_role_required"},
            }
        # If prompt included a trip name, try to scope to that report
        trip = parsed.get("slots", {}).get("trip")
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                if trip:
                    # Try normalized variants similar to _build_trip_status
                    candidates = [trip, trip.title()]
                    if not trip.lower().endswith("trip"):
                        candidates.extend([f"{trip} Trip", f"{trip.title()} Trip"])

                    report_id = None
                    for cand in candidates:
                        cur.execute(
                            "SELECT id FROM expense_reports WHERE trip_name = %s",
                            (cand,),
                        )
                        r = cur.fetchone()
                        if r:
                            report_id = r[0]
                            break

                    if not report_id:
                        return {
                            "handled": True,
                            "response": {"message": f"No report found for '{trip}'", "pending": []},
                        }

                    cur.execute(
                        """
                        SELECT e.id, r.employee_name, e.vendor, e.amount, e.status
                        FROM expenses e
                        JOIN expense_reports r ON e.report_id = r.id
                        WHERE e.report_id = %s AND e.status != 'APPROVED'
                        ORDER BY e.id DESC
                        """,
                        (report_id,),
                    )
                else:
                    # Return all pending across reports
                    cur.execute(
                        """
                        SELECT e.id, r.employee_name, e.vendor, e.amount, e.status
                        FROM expenses e
                        JOIN expense_reports r ON e.report_id = r.id
                        WHERE e.status != 'APPROVED'
                        ORDER BY r.employee_name
                        """
                    )

                rows = cur.fetchall()
                # Debug: number of rows fetched
                print(f"[prompt_router] manager_list_pending: fetched {len(rows)} rows for trip={trip}")
        finally:
            conn.close()

        return {
            "handled": True,
            "response": {
                "pending": [
                    {
                        "expense_id": r[0],
                        "employee": r[1],
                        "vendor": r[2],
                        "amount": float(r[3]),
                        "status": r[4],
                    }
                    for r in rows
                ]
            },
        }

    # -----------------------------
    # MANAGER: APPROVE
    # -----------------------------
    if intent == "manager_approve":
        if headers.get("x-user-role", "").lower() != "manager":
            return {
                "handled": True,
                "response": {"error": "manager_role_required"},
            }

        expense_id = parsed["slots"].get("expense_id")
        employee_name = parsed["slots"].get("employee_name")

        conn = get_connection()
        try:
            with conn.cursor() as cur:
                # Approve-by-id: validate amount threshold first
                if expense_id:
                    cur.execute("SELECT amount FROM expenses WHERE id=%s", (expense_id,))
                    row = cur.fetchone()
                    if not row:
                        return {"handled": True, "response": {"error": "expense_not_found"}}
                    amount = float(row[0] or 0)
                    if amount < 5000:
                        return {"handled": True, "response": {"error": "amount_below_manager_threshold", "amount": amount}}

                    cur.execute(
                        "UPDATE expenses SET status='APPROVED' WHERE id=%s",
                        (expense_id,),
                    )

                elif employee_name:
                    # Find most recent pending expense for the employee and validate amount
                    cur.execute(
                        """
                        SELECT e.id, e.amount
                        FROM expenses e
                        JOIN expense_reports r ON e.report_id = r.id
                        WHERE r.employee_name ILIKE %s
                          AND e.status != 'APPROVED'
                        ORDER BY e.id DESC
                        LIMIT 1
                        """,
                        ("%" + employee_name + "%",),
                    )
                    row = cur.fetchone()

                    # If not found by employee, try matching by vendor name in expenses
                    if not row:
                        cur.execute(
                            """
                            SELECT e.id, e.amount
                            FROM expenses e
                            WHERE e.vendor ILIKE %s
                              AND e.status != 'APPROVED'
                            ORDER BY e.id DESC
                            LIMIT 1
                            """,
                            ("%" + employee_name + "%",),
                        )
                        row = cur.fetchone()
                        if not row:
                            return {"handled": True, "response": {"error": "no_pending_for_employee_or_vendor"}}

                    target_id, amount = row[0], float(row[1] or 0)
                    if amount < 5000:
                        return {"handled": True, "response": {"error": "amount_below_manager_threshold", "amount": amount}}

                    cur.execute(
                        "UPDATE expenses SET status='APPROVED' WHERE id=%s",
                        (target_id,),
                    )
                else:
                    return {
                        "handled": True,
                        "response": {"error": "no_target_specified"},
                    }

                conn.commit()
        finally:
            conn.close()

        return {
            "handled": True,
            "response": {"message": "Expense approved"},
        }

    # -----------------------------
    # FALLBACK
    # -----------------------------
    return {
        "handled": False,
        "reason": "unknown_intent",
        "parsed": parsed,
    }
