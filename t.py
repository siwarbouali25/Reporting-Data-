# ============================================================
# URL-based Azure/OpenAI-compatible LLM client
# Uses full URLs directly, no endpoint/deployment parsing
# ============================================================

import os
import time
import requests


class AzureURLLLM(LLMClient):
    """
    Calls full completion URLs directly.

    Expected env vars:
      AZURE_WRITER_URL
      AZURE_EXTRACTOR_URL
      AZURE_JUDGE_URL
      AZURE_REVISER_URL
      AZURE_OPENAI_API_KEY

    This does NOT require:
      AZURE_OPENAI_ENDPOINT
      AZURE_OPENAI_API_VERSION
      AZURE_*_DEPLOYMENT
    """

    def __init__(
        self,
        *,
        writer_url: str | None = None,
        extractor_url: str | None = None,
        judge_url: str | None = None,
        reviser_url: str | None = None,
        api_key: str | None = None,
        auth_mode: str = "api-key",
        max_retries: int = 4,
        timeout: int = 120,
    ) -> None:
        self._urls = {
            "writer": writer_url or os.environ["AZURE_WRITER_URL"],
            "extractor": extractor_url or os.environ["AZURE_EXTRACTOR_URL"],
            "judge": judge_url or os.environ["AZURE_JUDGE_URL"],
            "reviser": reviser_url or os.environ["AZURE_REVISER_URL"],
        }

        self._api_key = api_key or os.getenv("AZURE_OPENAI_API_KEY")
        self._auth_mode = auth_mode
        self._max_retries = max_retries
        self._timeout = timeout
        self._cfg = SETTINGS.model

    def _headers(self) -> dict:
        headers = {
            "Content-Type": "application/json",
        }

        if self._auth_mode == "api-key":
            if not self._api_key:
                raise ValueError("Missing AZURE_OPENAI_API_KEY.")
            headers["api-key"] = self._api_key

        elif self._auth_mode == "bearer":
            if not self._api_key:
                raise ValueError("Missing AZURE_OPENAI_API_KEY.")
            headers["Authorization"] = f"Bearer {self._api_key}"

        elif self._auth_mode == "none":
            pass

        else:
            raise ValueError(
                "auth_mode must be one of: 'api-key', 'bearer', 'none'"
            )

        return headers

    def complete(
        self,
        *,
        role: Role,
        system: str,
        user: str,
        json_mode: bool = False,
    ) -> str:
        url = self._urls[role]
        temperature = self._cfg.temperature_for(role)

        payload = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
        }

        # Only include this when the notebook explicitly asks for JSON mode.
        # Some Azure/custom endpoints may not support it.
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        last_err = None

        for attempt in range(self._max_retries):
            try:
                response = requests.post(
                    url,
                    headers=self._headers(),
                    json=payload,
                    timeout=self._timeout,
                )

                if response.status_code >= 400:
                    raise RuntimeError(
                        f"HTTP {response.status_code}: {response.text[:1000]}"
                    )

                data = response.json()

                # Standard chat/completions format
                if "choices" in data:
                    return data["choices"][0]["message"]["content"] or ""

                # Some gateway/custom formats
                if "output_text" in data:
                    return data["output_text"] or ""

                if "content" in data:
                    return data["content"] or ""

                raise RuntimeError(
                    f"Unexpected response format: {str(data)[:1000]}"
                )

            except Exception as err:
                last_err = err
                print(
                    f"[URL LLM retry {attempt + 1}/{self._max_retries}] "
                    f"role={role} url={url[:120]} error={repr(err)}"
                )
                time.sleep(min(2**attempt, 8))

        raise RuntimeError(
            f"URL LLM call failed after retries.\n"
            f"role={role}\n"
            f"url={url}\n"
            f"last_error={repr(last_err)}"
        )
    



    # ============================================================
# Azure URLs setup
# You use full URLs directly, not endpoint/deployment names
# ============================================================

import os
from getpass import getpass

# Paste your real URLs here.
# These should be the full URL that accepts a POST request for chat completion.
os.environ["AZURE_WRITER_URL"] = "PASTE_WRITER_URL_HERE"
os.environ["AZURE_EXTRACTOR_URL"] = "PASTE_EXTRACTOR_URL_HERE"
os.environ["AZURE_JUDGE_URL"] = "PASTE_JUDGE_URL_HERE"
os.environ["AZURE_REVISER_URL"] = "PASTE_REVISER_URL_HERE"

if not os.getenv("AZURE_OPENAI_API_KEY"):
    os.environ["AZURE_OPENAI_API_KEY"] = getpass("Azure API key: ")

print("Writer URL:", os.environ["AZURE_WRITER_URL"][:120])
print("Extractor URL:", os.environ["AZURE_EXTRACTOR_URL"][:120])
print("Judge URL:", os.environ["AZURE_JUDGE_URL"][:120])
print("Reviser URL:", os.environ["AZURE_REVISER_URL"][:120])





# ============================================================
# Test one URL before running the full pipeline
# ============================================================

test_llm = AzureURLLLM(
    writer_url=os.environ["AZURE_WRITER_URL"],
    extractor_url=os.environ["AZURE_EXTRACTOR_URL"],
    judge_url=os.environ["AZURE_JUDGE_URL"],
    reviser_url=os.environ["AZURE_REVISER_URL"],
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    auth_mode="api-key",
)

test_response = test_llm.complete(
    role="extractor",
    system="You are a test assistant.",
    user="Reply with only: OK",
)

print("Test response:", test_response)