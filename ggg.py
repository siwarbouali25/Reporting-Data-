# ============================================================
# SECTION-BY-SECTION REQUIREMENTS EXPORT
# Input  : deterministic generation-ready requirements CSV
# Output : one CSV + one JSON per report section
# ============================================================

import json
import re
from pathlib import Path

import pandas as pd


# ------------------------------------------------------------
# 1. Paths
# ------------------------------------------------------------

OUTPUT_DIR = Path("ifrs_requirements_kb_outputs_final")

GENERATION_REQUIREMENTS_PATH = OUTPUT_DIR / "ifrs_s1_s2_generation_requirements.csv"

SECTION_OUTPUT_DIR = OUTPUT_DIR / "section_by_section_requirements"
SECTION_CSV_DIR = SECTION_OUTPUT_DIR / "csv"
SECTION_JSON_DIR = SECTION_OUTPUT_DIR / "json"

SECTION_CSV_DIR.mkdir(parents=True, exist_ok=True)
SECTION_JSON_DIR.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------
# 2. Load deterministic generation-ready requirements
# ------------------------------------------------------------

generation_df = pd.read_csv(GENERATION_REQUIREMENTS_PATH)

print("Loaded generation-ready requirements:", len(generation_df))
print("Columns:", list(generation_df.columns))


# ------------------------------------------------------------
# 3. Basic validation
# ------------------------------------------------------------

required_columns = [
    "requirement_id",
    "standard",
    "paragraph_id",
    "page",
    "report_section",
    "clean_requirement_text",
    "source_paragraph_text",
    "clause_path",
    "obligation_type",
    "mandatory",
    "evidence_tags",
    "banking_relevance",
]

missing_columns = [col for col in required_columns if col not in generation_df.columns]

if missing_columns:
    raise ValueError(
        "Missing required columns in generation requirements file: "
        + ", ".join(missing_columns)
    )

# Keep only mandatory rows, just in case the source file changed later
generation_df = generation_df[
    generation_df["mandatory"].astype(str).str.lower().isin(["true", "1", "yes"])
].copy()

print("Mandatory generation rows:", len(generation_df))


# ------------------------------------------------------------
# 4. Helpers
# ------------------------------------------------------------

SECTION_ORDER = [
    "General Requirements",
    "Governance",
    "Strategy",
    "Risk Management",
    "Metrics and Targets",
]

SECTION_SLUGS = {
    "General Requirements": "general_requirements",
    "Governance": "governance",
    "Strategy": "strategy",
    "Risk Management": "risk_management",
    "Metrics and Targets": "metrics_and_targets",
}


def slugify(value: str) -> str:
    value = str(value).strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value


def safe_json_list(value):
    """
    Converts evidence_tags / similar fields into clean lists.
    Handles:
    - actual lists
    - JSON strings
    - comma-separated strings
    - empty values
    """
    if pd.isna(value):
        return []

    if isinstance(value, list):
        return value

    text = str(value).strip()

    if not text:
        return []

    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
        return [parsed]
    except Exception:
        pass

    if "," in text:
        return [item.strip() for item in text.split(",") if item.strip()]

    return [text]


def to_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ["true", "1", "yes", "y"]


def sort_paragraph_key(paragraph_id):
    """
    Sorts paragraph IDs like:
    26, B37, B62A, D15
    in a stable readable order.
    """
    text = str(paragraph_id)

    match = re.match(r"^([A-Z]*)(\d+)([A-Z]*)$", text)
    if not match:
        return (text, 0, "")

    prefix, number, suffix = match.groups()
    return (prefix, int(number), suffix)


def build_requirement_record(row):
    return {
        "requirement_id": row["requirement_id"],
        "standard": row["standard"],
        "paragraph_id": row["paragraph_id"],
        "page": int(row["page"]) if pd.notna(row["page"]) else None,
        "report_section": row["report_section"],
        "official_section_heading": row.get("official_section_heading", None),
        "nearest_pdf_heading": row.get("nearest_pdf_heading", None),
        "requirement_text": row["clean_requirement_text"],
        "source_paragraph_text": row["source_paragraph_text"],
        "clause_path": row.get("clause_path", None),
        "obligation_type": row["obligation_type"],
        "mandatory": to_bool(row["mandatory"]),
        "evidence_tags": safe_json_list(row.get("evidence_tags", "")),
        "banking_relevance": row.get("banking_relevance", None),
        "paragraph_quality_score": float(row["paragraph_quality_score"])
        if "paragraph_quality_score" in row and pd.notna(row["paragraph_quality_score"])
        else None,
        "requirement_quality_score": float(row["requirement_quality_score"])
        if "requirement_quality_score" in row and pd.notna(row["requirement_quality_score"])
        else None,
    }


# ------------------------------------------------------------
# 5. Export one CSV and one JSON per section
# ------------------------------------------------------------

section_index_rows = []
all_sections_json = {}

for section_name in SECTION_ORDER:
    section_df = generation_df[
        generation_df["report_section"].astype(str).str.strip() == section_name
    ].copy()

    if section_df.empty:
        print(f"WARNING: no rows found for section: {section_name}")
        continue

    section_slug = SECTION_SLUGS.get(section_name, slugify(section_name))

    section_df["_paragraph_sort"] = section_df["paragraph_id"].apply(sort_paragraph_key)
    section_df = section_df.sort_values(
        by=["standard", "_paragraph_sort", "requirement_id"]
    ).drop(columns=["_paragraph_sort"])

    # -----------------------------
    # CSV export
    # -----------------------------
    section_csv_path = SECTION_CSV_DIR / f"{section_slug}_requirements.csv"
    section_df.to_csv(section_csv_path, index=False, encoding="utf-8-sig")

    # -----------------------------
    # JSON export
    # -----------------------------
    section_json = {
        "section_key": section_slug,
        "section_title": section_name,
        "source": "IFRS S1 and IFRS S2 deterministic generation-ready requirements",
        "row_count": int(len(section_df)),
        "standards": {},
    }

    for standard, standard_df in section_df.groupby("standard", sort=False):
        records = [
            build_requirement_record(row)
            for _, row in standard_df.iterrows()
        ]

        section_json["standards"][standard] = {
            "row_count": len(records),
            "requirements": records,
        }

    section_json_path = SECTION_JSON_DIR / f"{section_slug}_requirements.json"

    with open(section_json_path, "w", encoding="utf-8") as f:
        json.dump(section_json, f, ensure_ascii=False, indent=2)

    all_sections_json[section_slug] = section_json

    section_index_rows.append({
        "section_key": section_slug,
        "section_title": section_name,
        "row_count": int(len(section_df)),
        "csv_path": str(section_csv_path),
        "json_path": str(section_json_path),
    })

    print(f"Exported {section_name}: {len(section_df)} rows")


# ------------------------------------------------------------
# 6. Export global section index
# ------------------------------------------------------------

section_index_df = pd.DataFrame(section_index_rows)

section_index_path = SECTION_OUTPUT_DIR / "section_requirements_index.csv"
section_index_df.to_csv(section_index_path, index=False, encoding="utf-8-sig")

combined_json_path = SECTION_OUTPUT_DIR / "all_sections_requirements.json"

with open(combined_json_path, "w", encoding="utf-8") as f:
    json.dump(
        {
            "source": "IFRS S1 and IFRS S2 deterministic generation-ready requirements",
            "total_sections": len(all_sections_json),
            "sections": all_sections_json,
        },
        f,
        ensure_ascii=False,
        indent=2,
    )

print("\nDone.")
print("Section index:", section_index_path)
print("Combined JSON:", combined_json_path)

display(section_index_df)