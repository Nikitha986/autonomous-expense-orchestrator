# SRS Compliance Audit: Autonomous Expense Orchestrator

Date: February 9, 2026

## Executive Summary
**Compliance: 65%** - Core functionality present but missing critical features per SRS

---

## Detailed Audit

### 1. PROJECT OVERVIEW
✅ **PASS** - Zero-Touch expense management portal concept understood
✅ **PASS** - MCP architecture identified in codebase

---

### 2. SYSTEM ARCHITECTURE
- **Orchestrator (LangGraph)**: ✅ IMPLEMENTED
- **MCP Server**: ⚠️ PARTIAL
  - Has tools (vision, policy, db) but NOT using FastMCP protocol
  - Backend exposes endpoints but not standardized MCP format
- **Agents/Tools**: ✅ IMPLEMENTED
  - Vision Agent: ✓
  - DB Agent: ✓
  - Policy Agent: ✓

### 3. FUNCTIONAL REQUIREMENTS

#### FR1: Multimodal Ingestion
- ✅ Accepts text prompt + image attachments
- ✅ Extracts Date, Amount, Vendor
- ❌ **GAP**: No explicit PDF support (only images)
- ❌ **GAP**: No test coverage for 3 receipt formats (digital, thermal, handwritten)
- ❌ **GAP**: No batch processing metrics

#### FR2: Intent & Context Mapping
- ✅ Identifies trip name from prompt
- ✅ Proactively asks for trip name if missing
- **Status**: FULLY IMPLEMENTED ✓

#### FR3: Automated Compliance Check
- ⚠️ **PARTIAL** Rule A: >₹5000 flagging exists but:
  - Returns "REJECTED" status, not "Requires Manual Review"
  - No aggregation of flagged expenses
  - No link generation to view flagged items
  
- ⚠️ **PARTIAL** Rule B: Duplicate detection works but:
  - Not properly counted in summary
  - No detailed duplicate report
  
- ⚠️ **PARTIAL** Rule C: Category mapping exists but:
  - Very basic keyword matching
  - No auto-detection from OCR text
  - detect_category() function exists but not integrated

#### FR4: Unified Command Center
- ✅ File expenses: "Upload these and file for Delhi" - WORKS
- ✅ Check Status: "What is the status of my Delhi report?" - WORKS
- ✅ Approve expense: "Approve expense 5" - WORKS
- ❌ **MISSING**: Manager Mode "Show pending expenses for my team members"
- ❌ **MISSING**: Manager Mode "Approve expense for Rajesh"
- ❌ **MISSING**: No multi-user/team support
- ❌ **MISSING**: No expense assignment by employee name

### 4. TECHNICAL SPECIFICATIONS

#### A. The Agentic Stack
- ✅ Framework: LangGraph - **IMPLEMENTED**
- ⚠️ Protocol: MCP - **NOT USING FASTMCP**
  - Current: FastAPI endpoints (not MCP format)
  - Required: FastMCP standardized protocol
- ❌ LLM: Claude 3.5 Sonnet - **NOT SPECIFIED**
  - No LLM selection in code
  - Using basic string extraction instead
- ✅ Database: PostgreSQL - **IMPLEMENTED**

#### B. Database Schema Requirements
- ✅ expense_reports table: YES
- ✅ expenses table: YES
- ❌ **MISSING**: thread_id column for conversation tracking
- ❌ **MISSING**: employee_name/user_id column
- ❌ **MISSING**: manager_id column for team tracking
- ❌ **MISSING**: approval_timestamp, approval_reason columns
- ❌ **MISSING**: expense_flag/requires_review flag column

---

## 5. USER JOURNEY VERIFICATION: "The Delhi Trip"

**Step 1**: User uploads 8 receipts → ✅ **WORKS**
**Step 2**: Vision Tool called via MCP → ⚠️ **PARTIAL** (works but not MCP format)
**Step 3**: Policy Tool flags high bill → ⚠️ **PARTIAL** (flags but status is "REJECTED", not "flagged for review")
**Step 4**: DB creates report → ⚠️ **PARTIAL** (creates but status is generic "PROCESSING")
**Step 5**: Agent responds with summary → ⚠️ **PARTIAL** (no link generation)

---

## 6. IMPLEMENTATION PHASES

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 1: Basic MCP | ✅ JSON data persistence works | But not MCP protocol |
| Phase 2: Vision LLM | ✅ OCR extraction works | Using Tesseract, not Claude |
| Phase 3: LangGraph State | ✅ Stateful workflow works | Missing thread persistence |
| Phase 4: Next.js UI | ✅ Status table works | No manager team view |

---

## CRITICAL GAPS SUMMARY

1. **MCP Protocol**: Not using FastMCP - needs implementation
2. **LLM Integration**: No Claude/Gemini integration for vision
3. **Manager Mode**: No team member expense management
4. **Policy Flagging**: Flags exist but not properly surfaced
5. **Thread Persistence**: No conversation memory
6. **Advanced Features**: No approval workflows, penalties for delays

---

## Required Actions for Full Compliance

### IMMEDIATE (Blocking)
1. Integrate FastMCP protocol ✗
2. Add employee/user tracking ✗
3. Implement manager team view ✗
4. Fix policy flagging status ✗
5. Add thread_id persistence ✗

### HIGH PRIORITY
6. Integrate Claude 3.5 Sonnet ✗
7. Add PDF support ✗
8. Generate approval links ✗
9. Implement approval workflows ✗

### MEDIUM PRIORITY
10. Add expense audit trail ✗
11. Create admin dashboard ✗
12. Implement email notifications ✗

