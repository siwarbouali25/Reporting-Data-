# ============================================================
# STYLE ARTIFACT VALIDATION — NO COPYING / NO CONTENT LEAKAGE
# Updated version: excludes control files that intentionally
# contain forbidden reference terms.
# ============================================================

import re
import json
from pathlib import Path

import pandas as pd


# ------------------------------------------------------------
# 1. Terms from the reference report that must NOT appear
#    in reusable style artifacts.
# ------------------------------------------------------------

FORBIDDEN_REFERENCE_TERMS = [
    "Emirates NBD",
    "Emirates NBD Group",
    "DenizBank",
    "Emirates Islamic",
    "Emirates NBD Capital",
    "Emirates NBD Asset Management",
    "Vijay Bains",
    "Manoj Chawla",
    "Patrick Sullivan",
    "BNRESGC",
    "Board Nomination, Remuneration and Environmental Social Governance Committee",
    "BRC",
    "Board Risk Committee",
    "GRC",
    "Group Risk Committee",
    "EXCO",
    "Group Executive Committee",
    "Sustainable Finance Forum",
    "Group Model Oversight Committee",
    "Management Credit Committee",
    "Responsible Investment Committee",
    "AED",
    "USD",
    "Dubai",
    "UAE",
    "MENA",
    "MENAT",
    "CBUAE",
    "KPMG",
    "Sustainalytics",
    "Microsoft Sustainability Manager",
]


# ------------------------------------------------------------
# 2. Regex for suspicious hard-coded metrics, dates, currencies.
# ------------------------------------------------------------

AMOUNT_OR_METRIC_PATTERN = re.compile(
    r"("
    r"\b\d+(\.\d+)?\s?%"              # percentages
    r"|\bUSD\b"                       # USD
    r"|\bAED\b"                       # AED
    r"|\b\d+(\.\d+)?\s?(million|billion|mn|bn)\b"
    r"|\b20\d{2}\b"                   # years like 2024, 2025, 2030
    r")",
    flags=re.IGNORECASE,
)


# ------------------------------------------------------------
# 3. Files to exclude from validation.
# ------------------------------------------------------------

# These files are expected to contain reference terms or raw reference notes.
# They should NOT be used directly by generation agents.
VALIDATION_EXCLUDE_FILENAMES = {
    "forbidden_reference_terms.json",   # intentionally contains blocked terms
    "style_chunk_notes.json",           # raw extraction notes, intermediate only
    "global_style_result.json",         # combined raw object; optional, not direct generation input
}

VALIDATION_EXCLUDE_DIR_PARTS = {
    "_intermediate",                    # raw/intermediate extraction files
}


# ------------------------------------------------------------
# 4. Helpers
# ------------------------------------------------------------

def read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def should_validate_artifact(path: Path) -> bool:
    path_parts = set(path.parts)

    if path.name in VALIDATION_EXCLUDE_FILENAMES:
        return False

    if path_parts.intersection(VALIDATION_EXCLUDE_DIR_PARTS):
        return False

    return path.suffix.lower() in {".json", ".md"}


def validate_artifact_file(path: Path) -> dict:
    text = read_text_file(path)

    forbidden_hits = [
        term for term in FORBIDDEN_REFERENCE_TERMS
        if term.lower() in text.lower()
    ]

    metric_hits = [
        match[0]
        for match in AMOUNT_OR_METRIC_PATTERN.findall(text)
    ]

    return {
        "file": str(path),
        "filename": path.name,
        "forbidden_reference_terms": forbidden_hits,
        "amount_or_metric_like_patterns": metric_hits[:30],
        "forbidden_reference_term_count": len(forbidden_hits),
        "amount_or_metric_like_pattern_count": len(metric_hits),
        "has_copying_risk": bool(forbidden_hits or metric_hits),
    }


# ------------------------------------------------------------
# 5. Collect artifacts to validate
# ------------------------------------------------------------

artifact_paths = [
    path
    for path in STYLE_OUTPUT_DIR.rglob("*")
    if path.is_file() and should_validate_artifact(path)
]

print("Files selected for validation:", len(artifact_paths))

for path in artifact_paths:
    print("-", path.relative_to(STYLE_OUTPUT_DIR))


# ------------------------------------------------------------
# 6. Run validation
# ------------------------------------------------------------

validation_rows = [
    validate_artifact_file(path)
    for path in artifact_paths
]

validation_df = pd.DataFrame(validation_rows)

validation_path = STYLE_OUTPUT_DIR / "style_artifact_validation.csv"
validation_df.to_csv(validation_path, index=False, encoding="utf-8-sig")

display(validation_df)


# ------------------------------------------------------------
# 7. Report risky files
# ------------------------------------------------------------

risky = validation_df[validation_df["has_copying_risk"] == True].copy()

if len(risky):
    print("WARNING: Some reusable style artifacts may contain reference-specific terms or hard-coded metrics.")
    print("Review these files manually before using them in generation:")
    display(risky[[
        "file",
        "forbidden_reference_terms",
        "amount_or_metric_like_patterns",
    ]])
else:
    print("Validation passed: no obvious reference-specific leakage detected.")


# ------------------------------------------------------------
# 8. Save forbidden reference terms as a control file
#    This file is intentionally excluded from validation.
# ------------------------------------------------------------

forbidden_terms_path = LANGUAGE_RULES_DIR / "forbidden_reference_terms.json"

with open(forbidden_terms_path, "w", encoding="utf-8") as f:
    json.dump(FORBIDDEN_REFERENCE_TERMS, f, ensure_ascii=False, indent=2)

print("Saved validation:", validation_path)
print("Saved forbidden terms control file:", forbidden_terms_path)
print("Note: forbidden_reference_terms.json is intentionally excluded from leakage validation.")