"use client";

import { useState } from "react";
import { getStatus } from "@/src/lib/api";

export default function StatusPage() {
  const [trip, setTrip] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<any | null>(null);

  async function fetchStatus() {
    setError(null);
    setLoading(true);
    try {
      const res = await getStatus(trip);
      setStatus(res);
    } catch (e: any) {
      setError(e.message || "Failed to fetch status");
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-black text-white p-6">
      <h1 className="text-2xl font-bold mb-4">Expense Status</h1>

      <div className="flex gap-2 mb-4">
        <input
          value={trip}
          onChange={(e) => setTrip(e.target.value)}
          placeholder="Enter trip name (e.g., Education Trip)"
          className="p-2 rounded bg-gray-900 border border-gray-700 w-80"
        />
        <button
          onClick={fetchStatus}
          className="bg-blue-600 hover:bg-blue-700 px-3 py-2 rounded"
          disabled={!trip || loading}
        >
          {loading ? "Loading…" : "Get Status"}
        </button>
      </div>

      {error && <div className="text-red-400 mb-3">{error}</div>}

      {status && (
        <div className="bg-gray-950 border border-gray-700 rounded p-4">
          <h2 className="font-semibold mb-2">{status.trip} — {status.status}</h2>
          <div className="text-sm text-gray-300 mb-4">
            Total: {status.summary?.total ?? 0} — Approved: {status.summary?.approved ?? 0} — Pending: {status.summary?.pending ?? 0}
          </div>

          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="text-left text-gray-400">
                <th className="py-2">ID</th>
                <th>Employee</th>
                <th>Vendor</th>
                <th>Amount</th>
                <th>Date</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {status.expenses && status.expenses.length > 0 ? (
                status.expenses.map((e: any) => (
                  <tr key={e.expense_id} className="border-t border-gray-800">
                    <td className="py-2">{e.expense_id}</td>
                    <td>{e.employee_name || "—"}</td>
                    <td>{e.vendor}</td>
                    <td>₹{e.amount?.toFixed?.(2) ?? e.amount}</td>
                    <td>{e.expense_date ?? "—"}</td>
                    <td>{e.status}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={6} className="py-4 text-gray-400">No expenses found for this trip.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
