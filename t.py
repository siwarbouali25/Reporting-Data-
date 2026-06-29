# ============================================================
# 15. Run End-to-End
# Paths adapted to your local UPLOADS folder structure
# + Azure OpenAI instead of MockLLM
# ============================================================

import os
from pathlib import Path
from getpass import getpass

# ------------------------------------------------------------
# 1) Locate UPLOADS folder
# ------------------------------------------------------------
def find_uploads_dir(start: Path = Path.cwd()) -> Path:
    """
    Finds the UPLOADS folder from the current working directory
    or one of its parent folders.
    """
    candidates = [start / "UPLOADS"] + [p / "UPLOADS" for p in start.parents]

    for c in candidates:
        if c.exists() and c.is_dir():
            return c.resolve()

    raise FileNotFoundError(
        "Could not find UPLOADS folder. "
        "Either run the notebook from the project root or set UPLOADS manually."
    )


UPLOADS = find_uploads_dir()

REQ_DIR = UPLOADS / "section_by_section_requirements" / "json"
PAYLOAD_DIR = UPLOADS / "payloads"
STYLE_PATH = UPLOADS / "global_style_guide.json"

OUT_DIR = UPLOADS.parent / "ifrs_output"

print("UPLOADS     :", UPLOADS)
print("REQ_DIR     :", REQ_DIR)
print("PAYLOAD_DIR :", PAYLOAD_DIR)
print("STYLE_PATH  :", STYLE_PATH)
print("OUT_DIR     :", OUT_DIR)


# ------------------------------------------------------------
# 2) Resolve notebook input paths
# ------------------------------------------------------------
def resolve_paths():
    req = {
        "general_requirements": REQ_DIR / "general_requirements_requirements.json",
        "governance": REQ_DIR / "governance_requirements.json",
        "strategy": REQ_DIR / "strategy_requirements.json",
        "risk_management": REQ_DIR / "risk_management_requirements.json",
        "metrics_and_targets": REQ_DIR / "metrics_and_targets_requirements.json",
    }

    pay = {
        "general_requirements": PAYLOAD_DIR / "payload_BANK01_general_requirements.json",
        "governance": PAYLOAD_DIR / "payload_BANK01_governance.json",
        "strategy": PAYLOAD_DIR / "payload_BANK01_strategy.json",
        "risk_management": PAYLOAD_DIR / "payload_BANK01_risk_management.json",
        "metrics_and_targets": PAYLOAD_DIR / "payload_BANK01_metrics_targets.json",
    }

    return req, pay, STYLE_PATH


def check_paths_exist(paths: dict, label: str):
    missing = []
    for key, path in paths.items():
        if not Path(path).exists():
            missing.append((key, path))

    if missing:
        msg = f"Missing {label} files:\n"
        msg += "\n".join([f"- {key}: {path}" for key, path in missing])
        raise FileNotFoundError(msg)


req_paths, pay_paths, style_path = resolve_paths()

check_paths_exist(req_paths, "requirement")
check_paths_exist(pay_paths, "payload")

if not style_path.exists():
    raise FileNotFoundError(f"Missing style guide: {style_path}")

requirements, payloads, style_guide = load_all(req_paths, pay_paths, style_path)


# ------------------------------------------------------------
# 3) Azure OpenAI setup
# ------------------------------------------------------------
# Put your real Azure endpoint here.
# Example format:
# https://YOUR-RESOURCE-NAME.openai.azure.com/

os.environ["AZURE_OPENAI_ENDPOINT"] = "https://YOUR-RESOURCE-NAME.openai.azure.com/"

# Safer than hardcoding the API key in the notebook.
if not os.getenv("AZURE_OPENAI_API_KEY"):
    os.environ["AZURE_OPENAI_API_KEY"] = getpass("Azure OpenAI API key: ")

# Use the API version configured for your Azure resource.
os.environ["AZURE_OPENAI_API_VERSION"] = "2024-10-21"

# IMPORTANT:
# These must be your Azure DEPLOYMENT NAMES, not just the model names,
# unless you named your deployments exactly like this.
os.environ["AZURE_WRITER_DEPLOYMENT"] = "YOUR_WRITER_DEPLOYMENT_NAME"
os.environ["AZURE_EXTRACTOR_DEPLOYMENT"] = "YOUR_EXTRACTOR_DEPLOYMENT_NAME"
os.environ["AZURE_JUDGE_DEPLOYMENT"] = "YOUR_JUDGE_DEPLOYMENT_NAME"
os.environ["AZURE_REVISER_DEPLOYMENT"] = "YOUR_REVISER_DEPLOYMENT_NAME"

# Rebuild SETTINGS so it reads the Azure deployment env vars above.
SETTINGS = Settings()


# ------------------------------------------------------------
# 4) Run with Azure instead of MockLLM
# ------------------------------------------------------------
llm = AzureOpenAILLM(
    endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    api_version=os.environ["AZURE_OPENAI_API_VERSION"],
)

pipeline = Pipeline(llm, style_guide, SETTINGS)
final = pipeline.run(requirements, payloads, bank_id="BANK01")

audit = final["audit"]
audit.run_metadata.update(build_run_metadata(payloads, SETTINGS.model))

out = Path(OUT_DIR)
out.mkdir(parents=True, exist_ok=True)

(out / "BANK01_sustainability_report.md").write_text(
    final["final_report"],
    encoding="utf-8"
)

paths = export_audit(
    audit,
    final["report_score"],
    final["consistency_report"],
    out
)

score = final["report_score"]

print("coverage=", score["coverage"], " style=", score["style"],
      " integrity_min=", score["integrity_min"],
      "PASS" if score["integrity_ok"] else "FAIL")

for k, s in score["per_section"].items():
    print(
        f"  {k:24s} cov={s['coverage']:.3f} "
        f"int={s['integrity']:.3f} sty={s['style']:.3f} "
        f"disclosable={s['disclosable_count']:>3} "
        f"excluded_missing={s['excluded_missing']:>3}"
    )

print("gap ledger audit-only:", len(audit.gap_ledger), "entries")
print("consistency:", "CONSISTENT" if final["consistency_report"]["consistent"] else "ISSUES")
print("artifacts:", paths)


# ============================================================
# Azure OpenAI diagnostic test
# Run this BEFORE the full pipeline
# ============================================================

import os
import requests
from getpass import getpass
from openai import AzureOpenAI

# ------------------------------------------------------------
# Fill these with your real Azure values
# ------------------------------------------------------------
os.environ["AZURE_OPENAI_ENDPOINT"] = "https://YOUR-RESOURCE-NAME.openai.azure.com"
os.environ["AZURE_OPENAI_API_VERSION"] = "2024-10-21"

if not os.getenv("AZURE_OPENAI_API_KEY"):
    os.environ["AZURE_OPENAI_API_KEY"] = getpass("Azure OpenAI API key: ")

# IMPORTANT:
# These are Azure DEPLOYMENT NAMES, not necessarily model names.
os.environ["AZURE_WRITER_DEPLOYMENT"] = "YOUR_WRITER_DEPLOYMENT_NAME"
os.environ["AZURE_EXTRACTOR_DEPLOYMENT"] = "YOUR_EXTRACTOR_DEPLOYMENT_NAME"
os.environ["AZURE_JUDGE_DEPLOYMENT"] = "YOUR_JUDGE_DEPLOYMENT_NAME"
os.environ["AZURE_REVISER_DEPLOYMENT"] = "YOUR_REVISER_DEPLOYMENT_NAME"

endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].strip().rstrip("/")
api_key = os.environ["AZURE_OPENAI_API_KEY"].strip()
api_version = os.environ["AZURE_OPENAI_API_VERSION"].strip()

print("Endpoint:", endpoint)
print("API version:", api_version)
print("Extractor deployment:", os.environ["AZURE_EXTRACTOR_DEPLOYMENT"])

# ------------------------------------------------------------
# 1) Basic endpoint/deployments connectivity test
# ------------------------------------------------------------
deployments_url = f"{endpoint}/openai/deployments"

try:
    r = requests.get(
        deployments_url,
        headers={"api-key": api_key},
        params={"api-version": api_version},
        timeout=20,
    )

    print("Deployments status:", r.status_code)
    print("Deployments response preview:")
    print(r.text[:1000])

    r.raise_for_status()

except Exception as e:
    print("\nAzure endpoint connection failed.")
    print("Error:", repr(e))
    raise


# ------------------------------------------------------------
# 2) Tiny chat completion test
# ------------------------------------------------------------
try:
    client = AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=api_version,
    )

    resp = client.chat.completions.create(
        model=os.environ["AZURE_EXTRACTOR_DEPLOYMENT"],
        messages=[
            {"role": "system", "content": "You are a test assistant."},
            {"role": "user", "content": "Reply with only: OK"},
        ],
        temperature=0,
    )

    print("Chat test response:", resp.choices[0].message.content)

except Exception as e:
    print("\nAzure chat completion failed.")
    print("Error:", repr(e))
    raise


# ------------------------------------------------------------
# 3) Rebuild SETTINGS after env vars are set
# ------------------------------------------------------------
SETTINGS = Settings()

print("\nAzure preflight passed.")