"use client";

import { useEffect, useState } from "react";
import { fileExpenses, getStatus, approveExpense, rejectExpense } from "@/src/lib/api";

type Message = {
  role: "user" | "assistant";
  text: string;
};

type PreviewFile = {
  file: File;
  preview?: string;
};

type ExtractionDetail = {
  receipt_id: number;
  vendor: string | null;
  amount: number | null;
  date: string | null;
  type: string;
  confidence: number;
  status: string;
  employee_name?: string | null;
};

export default function Home() {
  const [prompt, setPrompt] = useState("");
  const [files, setFiles] = useState<PreviewFile[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [trip, setTrip] = useState<string | null>(null);
  const [polling, setPolling] = useState(false);
  const [allowPDF, setAllowPDF] = useState(true);
  const [extractionDetails, setExtractionDetails] = useState<ExtractionDetail[]>([]);
  const [isManager, setIsManager] = useState(false);

  // Clear everything
  function clearAll() {
    files.forEach(f => f.preview && URL.revokeObjectURL(f.preview));
    setPrompt("");
    setFiles([]);
    setMessages([]);
    setTrip(null);
    setPolling(false);
    setExtractionDetails([]);
  }

  // File handler (multi + preview)
  function handleFiles(selected: FileList | null) {
    if (!selected) return;

    const newFiles: PreviewFile[] = [];

    Array.from(selected).forEach((file) => {
      if (
        !allowPDF &&
        file.type === "application/pdf"
      ) return;

      const isImage = file.type.startsWith("image/");
      newFiles.push({
        file,
        preview: isImage ? URL.createObjectURL(file) : undefined,
      });
    });

    setFiles((prev) => {
      const map = new Map<string, PreviewFile>();
      [...prev, ...newFiles].forEach((f) =>
        map.set(f.file.name + f.file.size, f)
      );
      return Array.from(map.values());
    });
  }

  // Prompt submit handler
  async function handlePrompt() {
    if (!prompt.trim()) return;

    setMessages((m) => [...m, { role: "user", text: prompt }]);

    try {
      const res = await fileExpenses(
        prompt,
        files.map(f => f.file),
        isManager ? "manager" : undefined
      );

      // Handle manager pending list responses
      if (res.pending && Array.isArray(res.pending)) {
        const details = res.pending.map((p: any) => ({
          receipt_id: p.expense_id,
          vendor: p.vendor ?? null,
          amount: p.amount ?? null,
          date: null,
          type: "db",
          confidence: 1.0,
          status: p.status ?? "PENDING",
          employee_name: p.employee ?? null,
          _show_ocr: false,
        }));
        setExtractionDetails(details);
      }

      if (res.messages) {
        res.messages.forEach((m: string) =>
          reply(m.replace(/^Agent:\s*/, ""))
        );
      }

      // Support prompt-router direct responses (e.g., status queries)
      if (res.message) {
        reply(res.message.replace(/^Agent:\s*/, ""));
      }

      if (res.trip_status) {
        const ts = res.trip_status;
        reply(`Trip: ${ts.trip} — status: ${ts.status} — total ${ts.summary.total}, approved ${ts.summary.approved}, pending ${ts.summary.pending}`);
        // Populate detailed expenses view so user can inspect each item
        if (ts.expenses && Array.isArray(ts.expenses)) {
          const details = ts.expenses.map((e: any) => ({
            receipt_id: e.expense_id,
            vendor: e.vendor || null,
            amount: e.amount || null,
            date: e.expense_date || null,
            type: "db",
            confidence: 1.0,
            status: (e.approved ? "APPROVED" : (e.status || "PENDING")),
            ocr_text: e.ocr_text || null,
            _show_ocr: false,
          }));

          setExtractionDetails(details);
        }
      }

      // Store extraction details
      if (res.extraction_details) {
        setExtractionDetails(res.extraction_details);
      }

      setPolling(true);
    } catch (e: any) {
      reply("❌ Backend error: " + e.message);
    }
  }

  function reply(text: string) {
    setMessages((m) => [...m, { role: "assistant", text }]);
  }

  // Get status badge color
  function getStatusColor(status: string) {
    switch (status) {
      case "EXTRACTED":
        return "bg-blue-900 text-blue-200";
      case "APPROVED":
        return "bg-green-900 text-green-200";
      case "FLAGGED":
        return "bg-red-900 text-red-200";
      case "FAILED":
        return "bg-gray-900 text-gray-200";
      default:
        return "bg-gray-700 text-gray-200";
    }
  }

  // UI
  return (
    <main className="min-h-screen bg-black text-white p-6">
      <h1 className="text-2xl font-bold mb-3">
        🤖 Autonomous Expense Orchestrator
      </h1>

      {/* Chat */}
      <div className="border border-gray-700 rounded p-4 h-[220px] overflow-y-auto mb-4 bg-gray-950">
        {messages.map((m, i) => (
          <div
            key={i}
            className={`mb-2 text-sm ${
              m.role === "user" ? "text-blue-400" : "text-green-400"
            }`}
          >
            <b>{m.role === "user" ? "You" : "Agent"}:</b> {m.text}
          </div>
        ))}
      </div>

      {/* Prompt */}
      <textarea
        className="w-full p-3 bg-gray-900 border border-gray-700 rounded text-sm"
        rows={3}
        placeholder='e.g. "File these receipts for my Delhi trip"'
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
      />

      {/* PDF toggle */}
      <label className="flex items-center gap-2 mt-2 text-sm">
        <input
          type="checkbox"
          checked={allowPDF}
          onChange={(e) => setAllowPDF(e.target.checked)}
        />
        Allow PDF receipts
      </label>

      <label className="flex items-center gap-2 mt-2 text-sm">
        <input
          type="checkbox"
          checked={isManager}
          onChange={(e) => setIsManager(e.target.checked)}
        />
        Act as manager (send manager header)
      </label>

      {/* File input */}
      <input
        type="file"
        multiple
        className="mt-2 text-sm"
        accept={allowPDF ? "image/*,application/pdf" : "image/*"}
        onChange={(e) => {
          handleFiles(e.target.files);
          e.target.value = "";
        }}
      />

      {/* Previews */}
      {files.length > 0 && (
        <div className="mt-3 grid grid-cols-4 gap-2">
          {files.map((f, i) => (
            <div
              key={i}
              className="relative border border-gray-700 rounded p-2 bg-gray-900"
            >
              {f.preview ? (
                <img
                  src={f.preview}
                  className="h-20 w-full object-cover rounded"
                />
              ) : (
                <div className="text-xs text-gray-300 truncate">
                  📄 {f.file.name}
                </div>
              )}

              <button
                onClick={() =>
                  setFiles((prev) =>
                    prev.filter((_, idx) => idx !== i)
                  )
                }
                className="absolute top-0 right-0 text-red-400 text-xs px-1"
              >
                ❌
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Buttons */}
      <div className="flex gap-3 mt-3">
        <button
          onClick={handlePrompt}
          className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded text-sm"
        >
          Send
        </button>
        <button
          onClick={clearAll}
          className="bg-gray-700 hover:bg-gray-600 px-4 py-2 rounded text-sm"
        >
          Clear
        </button>
      </div>

      {/* OCR Results / Extraction Details */}
      {extractionDetails.length > 0 && (
        <div className="mt-6 border border-gray-700 rounded p-4 bg-gray-950">
          <h2 className="text-lg font-bold mb-3 text-cyan-400">👁️ OCR Results</h2>
          <div className="space-y-3">
            {extractionDetails.map((detail) => (
              <div
                key={detail.receipt_id}
                className={`p-3 rounded border border-gray-700 ${getStatusColor(detail.status)}`}
              >
                <div className="flex justify-between items-start mb-2">
                  <div>
                    <div className="font-bold">Receipt #{detail.receipt_id}</div>
                    <div className="text-xs">Type: <span className="font-semibold">{detail.type}</span></div>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div>
                    <span className="text-gray-400">Vendor:</span>
                    <div className="font-semibold">{detail.vendor || "—"}</div>
                  </div>
                  <div>
                    <span className="text-gray-400">Amount:</span>
                    <div className="font-semibold">₹{detail.amount?.toFixed(2) || "—"}</div>
                  </div>
                  <div className="col-span-2">
                    <span className="text-gray-400">Date:</span>
                    <div className="font-semibold">{detail.date || "—"}</div>
                  </div>
                    {/* Only show manager action buttons for amounts >= 5000 */}
                    {(detail.amount ?? 0) >= 5000 ? (
                      <div className="col-span-2 mt-2 flex gap-2">
                        <button
                          onClick={async () => {
                            try {
                              // Approve
                              // @ts-ignore
                              const res = await approveExpense(detail.receipt_id);
                              reply(res.message || "Approved");
                              setExtractionDetails((prev) =>
                                prev.map((p) =>
                                  p.receipt_id === detail.receipt_id
                                    ? { ...p, status: "APPROVED" }
                                    : p
                                )
                              );
                            } catch (e: any) {
                              reply("❌ Approval failed: " + e.message);
                            }
                          }}
                          className="bg-green-600 hover:bg-green-700 px-3 py-1 rounded text-xs"
                        >
                          Approve
                        </button>

                        <button
                          onClick={async () => {
                            try {
                              // @ts-ignore
                              const res = await rejectExpense(detail.receipt_id);
                              reply(res.message || "Rejected");
                              setExtractionDetails((prev) =>
                                prev.map((p) =>
                                  p.receipt_id === detail.receipt_id
                                    ? { ...p, status: "REJECTED" }
                                    : p
                                )
                              );
                            } catch (e: any) {
                              reply("❌ Rejection failed: " + e.message);
                            }
                          }}
                          className="bg-red-600 hover:bg-red-700 px-3 py-1 rounded text-xs"
                        >
                          Reject
                        </button>

                        <button
                          onClick={() => {
                            // Toggle OCR text visibility
                            setExtractionDetails((prev) =>
                              prev.map((p) =>
                                p.receipt_id === detail.receipt_id
                                  ? { ...p, _show_ocr: !p._show_ocr }
                                  : p
                              )
                            );
                          }}
                          className="bg-gray-700 hover:bg-gray-600 px-3 py-1 rounded text-xs"
                        >
                          View OCR
                        </button>
                      </div>
                    ) : null}
                    {detail._show_ocr && (
                      <div className="col-span-2 mt-2 text-xs text-gray-300 whitespace-pre-wrap">
                        {/* @ts-ignore */}
                        {detail.ocr_text || "(no OCR available)"}
                      </div>
                    )}
                </div>

                <div className="mt-2 text-xs">
                  <span className={`px-2 py-1 rounded ${getStatusColor(detail.status)}`}>
                    {detail.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </main>
  );
}
