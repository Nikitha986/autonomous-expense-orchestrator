import os
import requests

# Example: End-to-end test for Delhi trip
state = {
    "prompt": "File these for my Delhi trip",
    "receipts": ["sample_receipt1.jpg", "sample_receipt2.jpg", "sample_receipt3.jpg"]
}

# Prepare files list but only include existing files to avoid CI failures
files = []
for f in state["receipts"]:
    if os.path.exists(f):
        files.append(("receipts", open(f, "rb")))

# 1. File expenses (simulate orchestrator call)
resp = requests.post("http://127.0.0.1:8000/expenses/file", data={"prompt": state["prompt"]}, files=files if files else None)
print("File Expenses Response:", resp.json() if resp is not None else "no response")

# 2. Check status
status_resp = requests.get("http://127.0.0.1:8000/expenses/status", params={"trip_name": "Delhi trip"})
print("Status Response:", status_resp.json())

# 3. Approve first pending expense (if any)
expenses = status_resp.json().get("expenses", [])
for e in expenses:
    if not e.get("approved"):
        approve_resp = requests.post("http://127.0.0.1:8000/manager/approve", params={"expense_id": e["expense_id"]})
        print(f"Approved expense {e['expense_id']}: ", approve_resp.json())
        break
