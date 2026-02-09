# 🤖 Autonomous Expense Orchestrator

An AI-powered, **prompt-driven expense management system** that allows users and managers to file, track, and approve expenses using **natural language + receipts** — all through a **single unified prompt interface (FR4)**.

Built with **FastAPI, LangGraph, PostgreSQL, and Next.js**, this project demonstrates an end-to-end **agentic workflow** for real-world enterprise automation.

---

## 🚀 Key Features

### ✅ FR1: Multimodal Ingestion
- Accepts **text prompts + multiple receipt images/PDFs**
- OCR extracts **Vendor, Amount, Date**
- Supports mixed batches (digital, scanned, PDF)

### ✅ FR2: Intent & Context Mapping
- Automatically detects **Trip Name** from prompt  
  _Example_: `"Upload these and file for Delhi"`
- If missing, agent asks:
  > “Which trip should I file these under?”

### ✅ FR3: Automated Compliance & Policy Checks
- Flags expenses **> ₹5,000** for manual review
- Detects **duplicate receipts** (vendor + amount + date)
- Auto-maps categories (e.g. Travel, Food, Utilities)

### ✅ FR4: Unified Command Center (Single Prompt Interface)
All actions work via **one `/prompt` endpoint**:
