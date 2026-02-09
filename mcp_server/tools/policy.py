# ============================================
# POLICY AGENT - SRS Compliance
# ============================================
# Rules:
# Rule A: Flag any single expense > ₹5,000 as "Requires Manual Review"
# Rule B: Detect duplicate receipts (same date/amount/vendor)
# Rule C: Map categories automatically

HIGH_VALUE_LIMIT = 5000  # 5,000 rupees

CATEGORY_MAP = {
    "indigo": "Travel",
    "air": "Travel",
    "spicejet": "Travel",
    "goair": "Travel",
    "bmi": "Travel",
    "flydubai": "Travel",
    "emirates": "Travel",
    "qatar": "Travel",
    "etihad": "Travel",
    "uber": "Travel",
    "ola": "Travel",
    "rapido": "Travel",
    "meru": "Travel",
    "train": "Travel",
    "railway": "Travel",
    "irctc": "Travel",
    "starbucks": "Food",
    "dunkin": "Food",
    "cafe": "Food",
    "restaurant": "Food",
    "dining": "Food",
    "pizza": "Food",
    "burger": "Food",
    "hotel": "Accommodation",
    "lodge": "Accommodation",
    "resort": "Accommodation",
    "airbnb": "Accommodation",
    "oyo": "Accommodation",
    "stay": "Accommodation",
    "taxi": "Travel",
    "electricity": "Utilities",
    "power": "Utilities",
    "water": "Utilities",
    "internet": "Utilities"
}


def detect_category(text: str, vendor: str) -> str:
    """
    Auto-detect expense category from OCR text and vendor name.
    SRS Requirement: Rule C - Map categories automatically.
    """
    full_text = (text + " " + vendor).lower()
    
    # Check vendor map first
    for keyword, category in CATEGORY_MAP.items():
        if keyword in full_text:
            return category
    
    return "Other"


def policy_agent(amount: float) -> str:
    """
    Simplified policy agent that returns status string.
    SRS Requirement: Rule A - Flag > ₹5,000 as "Requires Manual Review".
    """
    if amount > HIGH_VALUE_LIMIT:
        return "FLAGGED"  # Requires manual review
    return "APPROVED"


def apply_policy(expense: dict) -> dict:
    """
    Full policy check with compliance rules.
    
    Input: {vendor, amount, date, category, text}
    Output: {status, flag_reason, category, requires_review}
    """
    amount = expense.get("amount", 0) or 0
    vendor = (expense.get("vendor") or "").lower()
    text = expense.get("text", "")
    
    status = "APPROVED"
    flag_reason = None
    requires_review = False
    
    # Rule A: High value expense
    if amount > HIGH_VALUE_LIMIT:
        status = "FLAGGED"
        flag_reason = f"Expense amount ₹{amount:.2f} exceeds policy limit of ₹{HIGH_VALUE_LIMIT}"
        requires_review = True
    
    # Auto-detect category
    category = detect_category(text, vendor)
    
    return {
        "status": status,
        "flag_reason": flag_reason,
        "category": category,
        "requires_review": requires_review,
        "amount": amount,
        "vendor": vendor
    }


def check_amount_limit(amount: float) -> bool:
    """
    SRS Rule A: Check if amount exceeds limit.
    """
    return amount > HIGH_VALUE_LIMIT


def auto_category(vendor: str) -> str:
    """
    Auto category mapping for vendor.
    """
    vendor = vendor.lower()

    if any(k in vendor for k in ["uber", "ola", "rapido", "indigo", "air", "flydubai"]):
        return "Travel"

    if any(k in vendor for k in ["hotel", "oyo", "taj", "marriott"]):
        return "Lodging"

    if any(k in vendor for k in ["restaurant", "cafe", "starbucks", "food"]):
        return "Food"

    if any(k in vendor for k in ["bescom", "electric", "power"]):
        return "Utilities"

    if any(k in vendor for k in ["government", "fssai"]):
        return "Government Fees"

    return "Miscellaneous"
def policy_agent(amount: float) -> str:
    if amount > 5000:
        return "Action Required"
    return "Pending"


def policy_check(expense: dict) -> dict:
    """Compatibility wrapper used by tests — returns the apply_policy result."""
    try:
        return apply_policy(expense)
    except Exception as e:
        return {"status": "ERROR", "flag_reason": str(e)}
