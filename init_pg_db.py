import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    dbname=os.getenv("DB_NAME", "expense_orchestrator"),
    user=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD", "postgres123"),
    host=os.getenv("DB_HOST", "localhost"),
    port=os.getenv("DB_PORT", "5432")
)

cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS expense_reports (
    id SERIAL PRIMARY KEY,
    trip_name TEXT NOT NULL,
    employee_name TEXT DEFAULT NULL,
    employee_id TEXT DEFAULT NULL,
    thread_id TEXT UNIQUE,
    status TEXT DEFAULT 'PROCESSING',
    duplicate_count INTEGER DEFAULT 0,
    flagged_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP DEFAULT NULL
);
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS expenses (
    id SERIAL PRIMARY KEY,
    report_id INTEGER NOT NULL REFERENCES expense_reports(id),
    expense_date DATE,
    vendor TEXT,
    amount NUMERIC(10,2),
    category TEXT,
    ocr_text TEXT,
    status TEXT DEFAULT 'PENDING',
    flagged BOOLEAN DEFAULT FALSE,
    flag_reason TEXT DEFAULT NULL,
    approved_by TEXT DEFAULT NULL,
    approved_at TIMESTAMP DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (report_id) REFERENCES expense_reports(id)
);
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS employee_manager (
    id SERIAL PRIMARY KEY,
    employee_id TEXT NOT NULL,
    employee_name TEXT NOT NULL,
    manager_id TEXT NOT NULL,
    manager_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS approval_history (
    id SERIAL PRIMARY KEY,
    expense_id INTEGER NOT NULL REFERENCES expenses(id),
    approved_by TEXT NOT NULL,
    approved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approval_reason TEXT,
    status TEXT
);
""")


cur.execute("CREATE INDEX IF NOT EXISTS idx_trip_name ON expense_reports(trip_name);")
cur.execute("CREATE INDEX IF NOT EXISTS idx_employee ON expense_reports(employee_name);")
cur.execute("CREATE INDEX IF NOT EXISTS idx_thread ON expense_reports(thread_id);")
cur.execute("CREATE INDEX IF NOT EXISTS idx_report_id ON expenses(report_id);")
cur.execute("CREATE INDEX IF NOT EXISTS idx_expense_status ON expenses(status);")

conn.commit()
cur.close()
conn.close()
print("PostgreSQL DB ready with SRS compliance schema")
