const API_BASE = "http://127.0.0.1:8000";

/**
 * Unified prompt endpoint (SRS: Unified Command Center)
 * - Sends prompt
 * - Sends multiple receipts (images / PDFs)
 * - LangGraph decides what to do
 */
export async function fileExpenses(
  prompt: string,
  files: File[],
  role?: string
) {
  const formData = new FormData();
  formData.append("prompt", prompt);

  files.forEach((file) => {
    formData.append("receipts", file);
  });

  let res: Response;

  try {
    const headers: Record<string, string> = {};
    if (role) headers["X-User-Role"] = role;

    res = await fetch(`${API_BASE}/prompt`, {
      method: "POST",
      body: formData,
      headers,
    });
  } catch (err) {
    throw new Error("Backend not reachable. Is FastAPI running?");
  }

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Failed to process prompt");
  }

  return res.json();
}

/**
 * Poll expense report status by trip name
 */
export async function getStatus(tripName: string) {
  let res: Response;

  try {
    res = await fetch(
      `${API_BASE}/expenses/status?trip_name=${encodeURIComponent(tripName)}`
    );
  } catch (err) {
    throw new Error("Backend not reachable while fetching status");
  }

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Failed to fetch status");
  }

  return res.json();
}

/**
 * Manager: approve an expense (simple approval)
 */
export async function approveExpense(expenseId: number) {
  let res: Response;

  try {
    res = await fetch(
      `${API_BASE}/manager/approve?expense_id=${expenseId}`,
      { method: "POST", headers: { "X-User-Role": "manager" } }
    );
  } catch {
    throw new Error("Backend not reachable while approving expense");
  }

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Failed to approve expense");
  }

  return res.json();
}

export async function rejectExpense(expenseId: number) {
  let res: Response;

  try {
    res = await fetch(
      `${API_BASE}/manager/reject?expense_id=${expenseId}`,
      { method: "POST", headers: { "X-User-Role": "manager" } }
    );
  } catch {
    throw new Error("Backend not reachable while rejecting expense");
  }

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Failed to reject expense");
  }

  return res.json();
}

/**
 * Manager: approve expense with reason (audit trail)
 */
export async function approveExpenseWithReason(
  expenseId: number,
  approvedBy: string,
  reason?: string
) {
  const res = await fetch(`${API_BASE}/manager/approve_with_reason`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      expense_id: expenseId,
      approved_by: approvedBy,
      reason,
    }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Approval with reason failed");
  }

  return res.json();
}

/**
 * Manager: get all flagged expenses for team
 */
export async function getTeamFlaggedExpenses(managerName: string) {
  const res = await fetch(
    `${API_BASE}/manager/flagged?manager_name=${encodeURIComponent(managerName)}`
  );

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Failed to fetch team flagged expenses");
  }

  return res.json();
}

/**
 * Manager: get all expense reports for an employee
 */
export async function getEmployeeExpenses(employeeName: string) {
  const res = await fetch(
    `${API_BASE}/manager/employee?employee_name=${encodeURIComponent(employeeName)}`
  );

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Failed to fetch employee expenses");
  }

  return res.json();
}

/**
 * View all flagged expenses for a trip
 */
export async function getFlaggedByTrip(tripName: string) {
  const res = await fetch(
    `${API_BASE}/expenses/flagged?trip_name=${encodeURIComponent(tripName)}`
  );

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Failed to fetch flagged expenses");
  }

  return res.json();
}
