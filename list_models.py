import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY not found in .env")

client = genai.Client(api_key=api_key)

print("=== AVAILABLE MODELS ===")

for model in client.models.list():
    
    print("NAME:", model.name)
    if hasattr(model, "display_name"):
        print("DISPLAY:", model.display_name)
    print("----")
