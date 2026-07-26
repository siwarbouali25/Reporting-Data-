# ============================================================
# CELL 2 — ROBUST AZURE OPENAI CLIENT
# Replaces the engine notebook's current Cell 2
# ============================================================

import json
import os
import random
import re
import time
import urllib.error
import urllib.request

from typing import Any, Dict, Optional


# ============================================================
# Azure configuration
# ============================================================

AZURE_OPENAI_API_KEY = (
    os.getenv("AZURE_OPENAI_API_KEY")
    or os.getenv("OPENAI_API_KEY")
)


def _clean_url(value: Optional[str]) -> Optional[str]:
    if not value:
        return None

    value = str(value).strip().strip('"').strip("'")

    markdown_match = re.search(
        r"\]\((https://[^)\s]+)\)",
        value,
    )

    if markdown_match:
        value = markdown_match.group(1).strip()

    https_positions = [
        match.start()
        for match in re.finditer(r"https://", value)
    ]

    if https_positions:
        value = value[https_positions[-1]:]

    return value.strip().strip("[]").rstrip(").,;")


AZURE_STRONG_URL = _clean_url(
    os.getenv("AZURE_OPENAI_GPT52_DEPLOYMENT_URL")
)

AZURE_FAST_URL = (
    _clean_url(
        os.getenv("AZURE_OPENAI_FAST_DEPLOYMENT_URL")
    )
    or AZURE_STRONG_URL
)


# ============================================================
# Model routing
# ============================================================

MODEL_TIERS = {
    "writer": "strong",
    "patch_writer": "strong",
    "binding_verifier": "fast",
    "applicability_assessor": "fast",
    "coverage_verifier": "strong",
    "claims_checker": "strong",
    "style_judge": "fast",
    "editorial": "strong",
}


# ============================================================
# Validate configuration
# ============================================================

def validate_llm_config() -> None:
    missing = []

    if not AZURE_OPENAI_API_KEY:
        missing.append("AZURE_OPENAI_API_KEY")

    if not AZURE_STRONG_URL:
        missing.append(
            "AZURE_OPENAI_GPT52_DEPLOYMENT_URL"
        )

    if not AZURE_FAST_URL:
        missing.append(
            "AZURE_OPENAI_FAST_DEPLOYMENT_URL"
        )

    if missing:
        raise ValueError(
            "Missing Azure configuration:\n"
            + "\n".join(f"- {name}" for name in missing)
        )

    for name, url in {
        "strong": AZURE_STRONG_URL,
        "fast": AZURE_FAST_URL,
    }.items():
        if not url.startswith("https://"):
            raise ValueError(
                f"The {name} Azure URL must start with https://"
            )

        if "/chat/completions" not in url:
            raise ValueError(
                f"The {name} Azure URL must contain "
                f"'/chat/completions'."
            )


validate_llm_config()


# ============================================================
# LLM logging
# ============================================================

_LLM_CALL_LOG = STAGE_DIRS["logs"] / "llm_calls.jsonl"
_LLM_CALL_LOG.parent.mkdir(parents=True, exist_ok=True)


def _log_llm(record: Dict[str, Any]) -> None:
    with open(
        _LLM_CALL_LOG,
        "a",
        encoding="utf-8",
    ) as file:
        file.write(
            json.dumps(
                record,
                ensure_ascii=False,
                default=str,
            )
            + "\n"
        )


# ============================================================
# Azure HTTP errors
# ============================================================

class AzureHTTPError(RuntimeError):
    def __init__(
        self,
        status_code: int,
        response_body: str,
        headers: Optional[Dict[str, str]] = None,
    ):
        self.status_code = status_code
        self.response_body = response_body
        self.headers = headers or {}

        super().__init__(
            f"Azure HTTP {status_code}:\n"
            f"{response_body[:3000]}"
        )


def _azure_request(
    url: str,
    body: Dict[str, Any],
    timeout: int = 240,
) -> Dict[str, Any]:

    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "api-key": AZURE_OPENAI_API_KEY or "",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout,
        ) as response:
            return json.loads(
                response.read().decode("utf-8")
            )

    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode(
            "utf-8",
            errors="replace",
        )

        headers = (
            dict(exc.headers.items())
            if exc.headers
            else {}
        )

        raise AzureHTTPError(
            status_code=exc.code,
            response_body=response_body,
            headers=headers,
        ) from exc


# ============================================================
# Response helpers
# ============================================================

def _strip_json_fences(text: str) -> str:
    text = str(text or "").strip()

    text = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\s*```$",
        "",
        text,
    )

    return text.strip()


def _parse_json_content(
    content: str,
    role_label: str,
) -> Dict[str, Any]:

    candidate = _strip_json_fences(content)

    try:
        return json.loads(candidate)

    except json.JSONDecodeError:
        # Handle short commentary before or after the JSON.
        first_brace = candidate.find("{")
        last_brace = candidate.rfind("}")

        if first_brace >= 0 and last_brace > first_brace:
            extracted = candidate[
                first_brace:last_brace + 1
            ]

            try:
                return json.loads(extracted)
            except json.JSONDecodeError:
                pass

        raise ValueError(
            f"LLM call '{role_label}' returned invalid JSON.\n"
            f"Response preview:\n{candidate[:2000]}"
        )


def _retry_after_seconds(
    headers: Dict[str, str],
) -> Optional[float]:

    value = (
        headers.get("Retry-After")
        or headers.get("retry-after")
    )

    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ============================================================
# Main engine LLM function
# ============================================================

def llm_json(
    role_label: str,
    system: str,
    user: str,
    max_tokens: int = 4000,
    temperature: Optional[float] = None,
) -> Dict[str, Any]:
    """
    JSON-returning Azure call used by the engine.

    The temperature argument remains in the signature so existing
    engine calls do not need to change. It is deliberately not sent,
    because some GPT-5/reasoning deployments reject temperature.
    """

    started_at = time.time()

    # --------------------------------------------------------
    # Mock mode
    # --------------------------------------------------------

    if LLM_MODE == "mock":
        handler_name = role_label.split(":")[0]
        handler = MOCK_HANDLERS.get(handler_name)

        if handler is None:
            raise RuntimeError(
                f"No mock handler for LLM role '{role_label}'"
            )

        output = handler(system, user)

        _log_llm({
            "role": role_label,
            "mode": "mock",
            "latency_s": round(
                time.time() - started_at,
                3,
            ),
        })

        return output

    # --------------------------------------------------------
    # Azure routing
    # --------------------------------------------------------

    role_name = role_label.split(":")[0]

    tier = MODEL_TIERS.get(
        role_name,
        "strong",
    )

    url = (
        AZURE_STRONG_URL
        if tier == "strong"
        else AZURE_FAST_URL
    )

    if not url or not AZURE_OPENAI_API_KEY:
        raise RuntimeError(
            "Azure URL or API key is not configured."
        )

    base_body = {
        "messages": [
            {
                "role": "system",
                "content": system,
            },
            {
                "role": "user",
                "content": user,
            },
        ],
        "response_format": {
            "type": "json_object",
        },
    }

    # Preferred field first; legacy fallback second.
    token_fields = [
        "max_completion_tokens",
        "max_tokens",
    ]

    max_attempts = 6
    last_error: Optional[Exception] = None

    for token_field in token_fields:
        body = dict(base_body)
        body[token_field] = max_tokens

        for attempt in range(1, max_attempts + 1):
            try:
                data = _azure_request(
                    url=url,
                    body=body,
                )

                try:
                    content = data[
                        "choices"
                    ][0][
                        "message"
                    ][
                        "content"
                    ]
                except (KeyError, IndexError, TypeError) as exc:
                    raise ValueError(
                        "Unexpected Azure response:\n"
                        + json.dumps(
                            data,
                            ensure_ascii=False,
                            indent=2,
                        )[:3000]
                    ) from exc

                result = _parse_json_content(
                    content=content,
                    role_label=role_label,
                )

                _log_llm({
                    "role": role_label,
                    "mode": "azure",
                    "tier": tier,
                    "token_field": token_field,
                    "attempt": attempt,
                    "latency_s": round(
                        time.time() - started_at,
                        3,
                    ),
                    "prompt_chars": len(system) + len(user),
                    "completion_chars": len(content),
                    "usage": data.get("usage", {}),
                })

                return result

            except AzureHTTPError as exc:
                last_error = exc

                _log_llm({
                    "role": role_label,
                    "mode": "azure",
                    "tier": tier,
                    "token_field": token_field,
                    "attempt": attempt,
                    "status_code": exc.status_code,
                    "response": exc.response_body[:1500],
                })

                # Request compatibility error.
                if exc.status_code in {400, 422}:
                    if token_field == "max_completion_tokens":
                        print(
                            f"{role_label}: "
                            "`max_completion_tokens` was rejected; "
                            "trying `max_tokens`."
                        )
                        break

                    raise RuntimeError(
                        f"LLM call '{role_label}' was rejected.\n"
                        f"{exc}"
                    ) from exc

                # Rate limit.
                if exc.status_code == 429:
                    if attempt < max_attempts:
                        retry_after = _retry_after_seconds(
                            exc.headers
                        )

                        wait = (
                            retry_after
                            if retry_after is not None
                            else min(
                                (2 ** attempt) + random.random(),
                                60,
                            )
                        )

                        print(
                            f"{role_label}: rate limited; "
                            f"retrying in {wait:.1f}s."
                        )

                        time.sleep(wait)
                        continue

                    raise

                # Temporary Azure/server errors.
                if exc.status_code in {
                    500,
                    502,
                    503,
                    504,
                }:
                    if attempt < max_attempts:
                        wait = min(
                            2 ** (attempt - 1)
                            + random.random(),
                            12,
                        )

                        print(
                            f"{role_label}: Azure error "
                            f"{exc.status_code}; retrying "
                            f"in {wait:.1f}s."
                        )

                        time.sleep(wait)
                        continue

                    raise

                raise

            except (
                urllib.error.URLError,
                TimeoutError,
                ConnectionError,
                OSError,
            ) as exc:
                last_error = exc

                _log_llm({
                    "role": role_label,
                    "mode": "azure",
                    "tier": tier,
                    "token_field": token_field,
                    "attempt": attempt,
                    "error": repr(exc)[:1500],
                })

                if attempt < max_attempts:
                    wait = min(
                        2 ** (attempt - 1)
                        + random.random(),
                        12,
                    )

                    print(
                        f"{role_label}: connection problem; "
                        f"retrying in {wait:.1f}s."
                    )

                    time.sleep(wait)
                    continue

                raise RuntimeError(
                    f"LLM call '{role_label}' failed because "
                    f"of a connection problem: {exc}"
                ) from exc

    raise RuntimeError(
        f"LLM call '{role_label}' failed.\n"
        f"Last Azure error:\n{last_error}"
    )


# ============================================================
# Prompt truncation — required by later engine cells
# ============================================================

def truncate_for_prompt(
    obj: Any,
    max_chars: int = 60000,
) -> str:

    text = json.dumps(
        obj,
        ensure_ascii=False,
        indent=1,
        default=str,
    )

    if len(text) <= max_chars:
        return text

    return (
        text[:max_chars - 60]
        + "\n...[truncated for prompt length]..."
    )


# Later cells register the mock handlers.
MOCK_HANDLERS: Dict[str, Any] = {}


# ============================================================
# Connection test
# ============================================================

def test_engine_llm(
    tier: str = "strong",
) -> Dict[str, Any]:

    role_label = (
        "writer:connection_test"
        if tier == "strong"
        else "style_judge:connection_test"
    )

    result = llm_json(
        role_label=role_label,
        system=(
            "Return one valid JSON object only. "
            "Do not use markdown."
        ),
        user='Return {"status": "ok"}.',
        max_tokens=500,
    )

    print(f"{tier} endpoint response:", result)
    return result


print(
    "LLM client ready | "
    f"mode={LLM_MODE} | "
    f"strong_url={'set' if AZURE_STRONG_URL else 'MISSING'} | "
    f"fast_url={'set' if AZURE_FAST_URL else 'MISSING'}"
)