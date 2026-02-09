from mcp_server.tools.db import get_connection

def main():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT e.id, r.trip_name, r.employee_name, e.vendor, e.amount, e.status
            FROM expenses e
            JOIN expense_reports r ON e.report_id = r.id
            WHERE e.status != 'APPROVED'
            ORDER BY r.trip_name, r.employee_name
            LIMIT 200
        """)
        rows = cur.fetchall()
        if not rows:
            print("No pending expenses found (status != 'APPROVED').")
            return

        print(f"Found {len(rows)} pending expenses:")
        for r in rows:
            print(r)
    finally:
        conn.close()

if __name__ == '__main__':
    main()
