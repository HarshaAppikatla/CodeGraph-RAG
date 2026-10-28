import requests
import json
import sys

# Ensure UTF-8 output on Windows console
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = "http://localhost:8000"

# Optional: Set your JWT token if authentication is enabled
JWT_TOKEN = ""

headers = {
    "Content-Type": "application/json",
}
if JWT_TOKEN:
    headers["Authorization"] = f"Bearer {JWT_TOKEN}"

payload = {
    "query": "What is the primary role of the Key Vault module in this project?",
    "model": "groq/llama-3.3-70b-versatile",
    "top_k": 3,
    "stream": False
}

print(f"🚀 Sending RAG Query using model: {payload['model']}...")

try:
    response = requests.post(f"{BASE_URL}/api/rag/query", headers=headers, json=payload)
    
    if response.status_code == 200:
        result = response.json()
        print("\n✅ RAG Query Succeeded!")
        print(f"📌 Model Used: {result.get('model')}")
        print(f"⏱️ Response Time: {result.get('execution_time', 'N/A')}s")
        print("\n🤖 Response Preview:\n" + "-" * 50)
        print(result.get("answer", result.get("response", "No answer field found")))
    else:
        print(f"\n❌ Query Failed (HTTP {response.status_code}):")
        print(response.text)

except Exception as e:
    print(f"\n⚠️ Connection Error: {e}")
