"""
test_openai_api_key.py
======================

Purpose:
    Minimal script to test if OPENAI_API_KEY works.
"""

import os
import json
import urllib.request
import urllib.error
from dotenv import load_dotenv

# Load .env if present
load_dotenv()

# =========================================================
# CONFIG
# =========================================================

OPENAI_API_URL = "https://eyq-incubator.europe.fabric.ey.com/eyq/eu/api/openai/deployments/gpt-4o-mini/chat/completions"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
LLM_MODEL = "gpt-4o-mini"


# =========================================================
# API TEST
# =========================================================

def test_openai_api_key():
    if not OPENAI_API_KEY:
        raise EnvironmentError(
            "OPENAI_API_KEY is not set.\n\n"
            "In PowerShell, run:\n"
            '$env:OPENAI_API_KEY="your_key_here"\n\n'
            "Or create a .env file with:\n"
            "OPENAI_API_KEY=your_key_here"
        )

    payload = {
        "model": LLM_MODEL,
        "max_tokens": 80,
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": "You are a simple API test assistant."
            },
            {
                "role": "user",
                "content": "Reply with exactly: API key works."
            }
        ],
    }

    try:
        req = urllib.request.Request(
            OPENAI_API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "api-key":OPENAI_API_KEY,
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        print("Status: SUCCESS")
        print("Model:", data.get("model"))
        print("Response:")
        print(data["choices"][0]["message"]["content"])

        usage = data.get("usage", {})
        print("\nToken usage:")
        print("Prompt tokens:", usage.get("prompt_tokens"))
        print("Completion tokens:", usage.get("completion_tokens"))
        print("Total tokens:", usage.get("total_tokens"))

    except urllib.error.HTTPError as e:
        error_body = e.read().decode(errors="replace")
        print("Status: FAILED")
        print(f"HTTP error: {e.code}")
        print("Error body:")
        print(error_body)

    except urllib.error.URLError as e:
        print("Status: FAILED")
        print("Connection / network error:")
        print(e)

    except Exception as e:
        print("Status: FAILED")
        print("Unexpected error:")
        print(e)


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":
    test_openai_api_key()