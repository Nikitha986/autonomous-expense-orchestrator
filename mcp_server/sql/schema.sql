-- PostgreSQL schema for Autonomous Expense Orchestrator
-- Creates expense_reports and expenses tables. Includes thread_id on reports

CREATE TABLE IF NOT EXISTS expense_reports (
  id SERIAL PRIMARY KEY,
  trip_name TEXT NOT NULL,
  employee_name TEXT,
  thread_id TEXT UNIQUE,
  status TEXT DEFAULT 'PROCESSING',
  duplicate_count INTEGER DEFAULT 0,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE TABLE IF NOT EXISTS expenses (
  id SERIAL PRIMARY KEY,
  report_id INTEGER NOT NULL REFERENCES expense_reports(id) ON DELETE CASCADE,
  expense_date DATE,
  vendor TEXT,
  amount NUMERIC(12,2) DEFAULT 0.0,
  category TEXT,
  status TEXT DEFAULT 'PENDING',
  ocr_text TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Useful indexes
CREATE INDEX IF NOT EXISTS idx_expenses_report_id ON expenses(report_id);
CREATE INDEX IF NOT EXISTS idx_reports_thread_id ON expense_reports(thread_id);
CREATE INDEX IF NOT EXISTS idx_expenses_vendor_amount ON expenses(vendor, amount);

-- Example: grant minimal privileges (adjust role names as necessary)
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO your_app_role;
