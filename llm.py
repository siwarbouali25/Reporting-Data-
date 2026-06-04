import os
import json
import urllib.request
from dotenv import load_dotenv

load_dotenv(override=True)

AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT").rstrip("/")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")

url = (
    f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/"
    f"{AZURE_OPENAI_DEPLOYMENT}/chat/completions"
    f"?api-version={AZURE_OPENAI_API_VERSION}"
)

payload = {
    "messages": [
        {"role": "user", "content": "Reply with: Azure works"}
    ],
    "temperature": 0.2,
    "max_tokens": 20,
}

req = urllib.request.Request(
    url,
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "Content-Type": "application/json",
        "api-key": AZURE_OPENAI_API_KEY,
    },
    method="POST",
)

with urllib.request.urlopen(req, timeout=60) as resp:
    data = json.loads(resp.read().decode("utf-8"))

print(data["choices"][0]["message"]["content"])