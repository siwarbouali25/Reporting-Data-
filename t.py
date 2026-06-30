# ============================================================
# Simple env-only URL LLM client
# ============================================================

import os
import time
import requests


class AzureURLLLM(LLMClient):
    def __init__(
        self,
        *,
        api_key: str | None = None,
        auth_mode: str = "api-key",
        max_retries: int = 4,
        timeout: int = 120,
    ) -> None:
        self._urls = {
            "writer": os.environ.get("AZURE_WRITER_URL"),
            "extractor": os.environ.get("AZURE_EXTRACTOR_URL"),
            "judge": os.environ.get("AZURE_JUDGE_URL"),
            "reviser": os.environ.get("AZURE_REVISER_URL"),
        }

        for role, url in self._urls.items():
            print(f"[AzureURLLLM init] {role} URL =", repr(url)[:160])

            if not url:
                raise ValueError(f"Missing URL for role={role}")

            if not url.startswith("http"):
                raise ValueError(
                    f"Invalid URL for role={role}. "
                    f"Current value is: {repr(url)}. "
                    f"It must start with https://"
                )

        self._api_key = api_key or os.environ.get("AZURE_OPENAI_API_KEY")
        self._auth_mode = auth_mode
        self._max_retries = max_retries
        self._timeout = timeout
        self._cfg = SETTINGS.model

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}

        if self._auth_mode == "api-key":
            if not self._api_key:
                raise ValueError("Missing AZURE_OPENAI_API_KEY")
            headers["api-key"] = self._api_key

        elif self._auth_mode == "bearer":
            if not self._api_key:
                raise ValueError("Missing AZURE_OPENAI_API_KEY")
            headers["Authorization"] = f"Bearer {self._api_key}"

        elif self._auth_mode == "none":
            pass

        else:
            raise ValueError("auth_mode must be 'api-key', 'bearer', or 'none'")

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
                        f"HTTP {response.status_code}: {response.text[:1500]}"
                    )

                data = response.json()

                if "choices" in data:
                    return data["choices"][0]["message"]["content"] or ""

                if "output_text" in data:
                    return data["output_text"] or ""

                if "content" in data:
                    return data["content"] or ""

                raise RuntimeError(f"Unexpected response format: {str(data)[:1500]}")

            except Exception as err:
                last_err = err
                print(
                    f"[URL LLM retry {attempt + 1}/{self._max_retries}] "
                    f"role={role} error={repr(err)}"
                )
                time.sleep(min(2**attempt, 8))

        raise RuntimeError(
            f"URL LLM call failed after retries.\n"
            f"role={role}\n"
            f"url={url}\n"
            f"last_error={repr(last_err)}"
        )