from api import app

state = {
    "prompt": "File these for my Delhi trip",
    "receipts": ["sample_receipt.jpg"]
}

result = app.invoke(state)
print(result)
