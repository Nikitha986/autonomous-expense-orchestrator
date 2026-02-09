from mcp_server.tools.policy import policy_check
from mcp_server.tools.db import (
    get_or_create_report,
    add_expense,
    is_duplicate,
    get_report_by_trip,
    get_expenses_by_report,
    approve_expense
)
# Vision Tool Endpoint
from fastapi import Form

@app.post("/tool/vision/extract")
async def vision_extract(file: UploadFile = File(...)):
    temp_path = f"temp_{file.filename}"
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    result = extract_receipt_data(temp_path)
    os.remove(temp_path)
    return result

# Policy Tool Endpoint
@app.post("/tool/policy/check")
async def policy_check_tool(
    date: str = Form(...),
    vendor: str = Form(...),
    amount: float = Form(...)
):
    expense = {"date": date, "vendor": vendor, "amount": amount}
    checked = policy_check(expense)
    return checked

# DB Tool Endpoints
@app.post("/tool/db/get_or_create_report")
async def db_get_or_create_report(trip_name: str = Form(...), thread_id: str = Form(...)):
    report_id = get_or_create_report(trip_name, thread_id)
    return {"report_id": report_id}

@app.post("/tool/db/add_expense")
async def db_add_expense(
    report_id: int = Form(...),
    date: str = Form(...),
    vendor: str = Form(...),
    amount: float = Form(...),
    category: str = Form(...),
    status: str = Form(...)
):
    add_expense(report_id, date, vendor, amount, category, status)
    return {"success": True}

@app.post("/tool/db/is_duplicate")
async def db_is_duplicate(
    date: str = Form(...),
    vendor: str = Form(...),
    amount: float = Form(...)
):
    duplicate = is_duplicate(date, vendor, amount)
    return {"duplicate": duplicate}
from fastapi import FastAPI
from pydantic import BaseModel
import json
import os
from fastapi import UploadFile, File
import shutil
from mcp_server.tools.vision import extract_receipt_data


app = FastAPI()

# -----------------------------
# Storage
# -----------------------------
DATA_FILE = "mcp_server/storage/data.json"
os.makedirs("mcp_server/storage", exist_ok=True)

if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump([], f)

# -----------------------------
# Test endpoint
# -----------------------------
@app.post("/add_numbers")
def add_numbers(a: int, b: int):
    return a + b

# -----------------------------
# Expense model
# -----------------------------
class Expense(BaseModel):
    thread_id: str
    date: str
    vendor: str
    amount: float
    category: str
    status: str

# -----------------------------
# Save expense
# -----------------------------
@app.post("/save_expense")
def save_expense(expense: Expense):
    with open(DATA_FILE, "r") as f:
        data = json.load(f)

    data.append(expense.dict())

    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

    return {"message": "Expense saved successfully"}

@app.post("/extract_receipt")
def extract_receipt(file: UploadFile = File(...)):
    """
    Upload a receipt image and extract date, vendor, amount
    """

    temp_path = f"temp_{file.filename}"

    # Save uploaded file temporarily
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Call vision agent
    result = extract_receipt_data(temp_path)

    return {
        "extracted_data": result
    }
