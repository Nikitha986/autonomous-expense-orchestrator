import json
import urllib.request

BASE = 'http://127.0.0.1:8000'

def post_prompt(prompt):
    url = BASE + '/prompt'
    data = json.dumps({'prompt': prompt}).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={
        'Content-Type': 'application/json',
        'X-User-Role': 'manager'
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read().decode('utf-8')
    except Exception as e:
        return f'ERROR: {e}'


def get_status(trip_name):
    import urllib.parse
    url = BASE + '/expenses/status?trip_name=' + urllib.parse.quote(trip_name)
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.read().decode('utf-8')
    except Exception as e:
        return f'ERROR: {e}'


def inspect_db():
    from mcp_server.tools.db import get_connection
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
        return rows
    finally:
        conn.close()


if __name__ == '__main__':
    print('POST: team-wide')
    print(post_prompt('Show the pending expenses for my team members'))
    print('\nPOST: scoped (education)')
    print(post_prompt('Show the pending expenses for education trip'))
    print('\nGET: status Education Trip')
    print(get_status('Education Trip'))
    print('\nDB rows:')
    rows = inspect_db()
    if not rows:
        print('No pending rows in DB (status != APPROVED).')
    else:
        for r in rows:
            print(r)
