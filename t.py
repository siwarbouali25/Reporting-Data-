# ============================================================
# Load and validate Azure URLs from .env
# ============================================================

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    raise ImportError("Install python-dotenv first: pip install python-dotenv")


def find_dotenv(start: Path = Path.cwd()) -> Path | None:
    candidates = [start / ".env"] + [p / ".env" for p in start.parents]
    for p in candidates:
        if p.exists():
            return p
    return None


dotenv_path = find_dotenv()

if dotenv_path:
    load_dotenv(dotenv_path, override=True)
    print("Loaded .env from:", dotenv_path)
else:
    load_dotenv(override=True)
    print("No .env file found, using system environment variables.")


required_env = [
    "AZURE_WRITER_URL",
    "AZURE_EXTRACTOR_URL",
    "AZURE_JUDGE_URL",
    "AZURE_REVISER_URL",
]

for key in required_env:
    value = os.getenv(key)

    if not value:
        raise ValueError(f"Missing environment variable: {key}")

    if not value.startswith("http"):
        raise ValueError(
            f"{key} is not a valid URL. Current value is: {value}"
        )

    print(f"{key} =", value[:120])





    # ============================================================
# URL-based Azure/OpenAI-compatible LLM client
# Reads full URLs directly from env
# ============================================================

import os
import time
import requests


class AzureURLLLM(LLMClient):
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
            "writer": self._resolve_url(writer_url, "AZURE_WRITER_URL"),
            "extractor": self._resolve_url(extractor_url, "AZURE_EXTRACTOR_URL"),
            "judge": self._resolve_url(judge_url, "AZURE_JUDGE_URL"),
            "reviser": self._resolve_url(reviser_url, "AZURE_REVISER_URL"),
        }

        self._api_key = api_key or os.getenv("AZURE_OPENAI_API_KEY")
        self._auth_mode = auth_mode
        self._max_retries = max_retries
        self._timeout = timeout
        self._cfg = SETTINGS.model

    def _resolve_url(self, value: str | None, env_name: str) -> str:
        """
        Resolves either:
        - None -> os.environ[env_name]
        - "AZURE_EXTRACTOR_URL" -> os.environ["AZURE_EXTRACTOR_URL"]
        - "https://..." -> direct URL
        """
        if value is None:
            value = os.getenv(env_name)

        elif value in os.environ:
            value = os.getenv(value)

        if not value:
            raise ValueError(f"Missing URL for {env_name}")

        value = value.strip()

        if not value.startswith("http"):
            raise ValueError(
                f"{env_name} must be a real URL starting with http/https. "
                f"Current value is: {value}"
            )

        return value

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
            raise ValueError("auth_mode must be: 'api-key', 'bearer', or 'none'")

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
                    f"role={role} url={url[:100]} error={repr(err)}"
                )
                time.sleep(min(2**attempt, 8))

        raise RuntimeError(
            f"URL LLM call failed after retries.\n"
            f"role={role}\n"
            f"url={url}\n"
            f"last_error={repr(last_err)}"
        )