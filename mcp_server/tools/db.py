import psycopg2
import os
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor

load_dotenv()

# -------------------------------
# Database Connection
# -------------------------------
def get_connection():
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
    )


# -------------------------------
# Helpers
# -------------------------------
def normalize_date(date):
    """
    PostgreSQL-safe date normalization.
    Converts invalid / missing dates to NULL.
    """
    if not date or date in ("0000-00-00", "", "1970-01-01"):
        return None
    return date


# -------------------------------
# Reports (Backward + SRS Compatible)
# -------------------------------
def get_or_create_report(
    trip_name: str,
    employee_name: str | None = None,
    thread_id: str | None = None,
):
    """
    ✔ Backward compatible
    ✔ Supports SRS: employee_name + thread_id
    """
    conn = get_connection()
    cur = conn.cursor()

    # 1️⃣ If thread_id exists → reuse report
    if thread_id:
        cur.execute(
            "SELECT id FROM expense_reports WHERE thread_id = %s",
            (thread_id,),
        )
        row = cur.fetchone()
        if row:
            cur.close()
            conn.close()
            return row[0]

    # 2️⃣ If trip already exists (old behavior)
    cur.execute(
        "SELECT id FROM expense_reports WHERE trip_name = %s",
        (trip_name,),
    )
    row = cur.fetchone()
    if row:
        cur.close()
        conn.close()
        return row[0]

    # 3️⃣ Create new report
    cur.execute(
        """
        INSERT INTO expense_reports
        (trip_name, employee_name, thread_id, status, duplicate_count)
        VALUES (%s, %s, %s, 'PROCESSING', 0)
        RETURNING id
        """,
        (trip_name, employee_name, thread_id),
    )

    report_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return report_id


def get_report_by_trip(trip_name: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, status, duplicate_count
        FROM expense_reports
        WHERE trip_name = %s
        """,
        (trip_name,),
    )

    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def update_report_status(report_id: int, status: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "UPDATE expense_reports SET status=%s WHERE id=%s",
        (status, report_id),
    )

    conn.commit()
    cur.close()
    conn.close()


def increment_duplicate_count(report_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE expense_reports
        SET duplicate_count = duplicate_count + 1
        WHERE id = %s
        """,
        (report_id,),
    )

    conn.commit()
    cur.close()
    conn.close()


# -------------------------------
# Expenses
# -------------------------------
def is_duplicate(report_id, vendor, amount, date):
    date = normalize_date(date)

    query = """
        SELECT 1
        FROM expenses
        WHERE report_id = %s
          AND vendor = %s
          AND amount = %s
          AND (
                %s IS NULL
                OR expense_date = %s
              )
        LIMIT 1
    """

    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Final safety guard — never trust callers
            if not date or date in ("NA", "N/A", "UNKNOWN", "", "0000-00-00"):
                date = None
            cur.execute(
                query,
                (report_id, vendor, amount, date, date)
            )
            return cur.fetchone() is not None
    finally:
        conn.close()


def add_expense(
    report_id,
    expense_date,
    vendor,
    amount,
    category,
    status,
    ocr_text,
):
    expense_date = normalize_date(expense_date)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO expenses
                (report_id, expense_date, vendor, amount, category, status, ocr_text)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    report_id,
                    expense_date,
                    vendor,
                    amount,
                    category,
                    status,
                    ocr_text,
                ),
            )
            conn.commit()
    finally:
        conn.close()


def get_expenses_by_report(report_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            id,
            expense_date,
            vendor,
            amount,
            category,
            status,
            ocr_text
        FROM expenses
        WHERE report_id=%s
        ORDER BY expense_date DESC NULLS LAST
        """,
        (report_id,),
    )

    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


import json
from datetime import datetime


def _ensure_state_table(conn):
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS orchestrator_state (
            thread_id TEXT PRIMARY KEY,
            state_json JSONB,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        )
        """
    )
    conn.commit()
    cur.close()


def save_orchestrator_state(thread_id: str, state: dict):
    if not thread_id:
        return
    conn = get_connection()
    try:
        _ensure_state_table(conn)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO orchestrator_state (thread_id, state_json, updated_at) VALUES (%s, %s, now()) "
            "ON CONFLICT (thread_id) DO UPDATE SET state_json = EXCLUDED.state_json, updated_at = EXCLUDED.updated_at",
            (thread_id, json.dumps(state)),
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()


def load_orchestrator_state(thread_id: str):
    if not thread_id:
        return None
    conn = get_connection()
    try:
        _ensure_state_table(conn)
        cur = conn.cursor()
        cur.execute("SELECT state_json FROM orchestrator_state WHERE thread_id=%s", (thread_id,))
        row = cur.fetchone()
        cur.close()
        if not row:
            return None
        try:
            return json.loads(row[0]) if isinstance(row[0], str) else row[0]
        except Exception:
            return None
    finally:
        conn.close()
