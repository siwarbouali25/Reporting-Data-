# ============================================================
# DISCLOSURE CATALOG VALIDATION
# ============================================================

import json
import re
from pathlib import Path
from collections import Counter, defaultdict

import pandas as pd

# ── PATHS ───────────────────────────────────────────────────
OUTPUT_DIR = Path("outputs/ifrs_disclosures")

IFRS_PARAGRAPHS_JSON = OUTPUT_DIR / "ifrs_paragraphs.json"
DISCLOSURES_JSON = OUTPUT_DIR / "disclosures_source_grounded.json"
DISCLOSURES_CSV = OUTPUT_DIR / "disclosures_source_grounded.csv"
VALIDATION_REPORT = OUTPUT_DIR / "validation_report.md"

# ── REQUIRED FIELDS ─────────────────────────────────────────
REQUIRED_DISCLOSURE_FIELDS = [
    "disclosure_id",
    "standard",
    "core_area",
    "paragraph_ref",
    "requirement_summary",
    "required_evidence",
    "source_paragraph_ids",
    "source_quote",
]

VALID_STANDARDS = {"IFRS_S1", "IFRS_S2"}

VALID_CORE_AREAS = {
    "Governance",
    "Strategy",
    "Risk Management",
    "Metrics and Targets",
    "General Requirements",
}

IMPORTANT_CORE_AREAS = {
    "Governance",
    "Strategy",
    "Risk Management",
    "Metrics and Targets",
}


# ============================================================
# HELPERS
# ============================================================

def load_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_text(text: str) -> str:
    """Normalize whitespace for quote matching."""
    if text is None:
        return ""
    text = str(text).replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_json_list(value):
    """
    Convert CSV JSON-string lists back to Python lists if needed.
    Works for both JSON files and CSV-loaded values.
    """
    if isinstance(value, list):
        return value
    if value is None:
        return []
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else [parsed]
        except json.JSONDecodeError:
            return [value]
    return [value]


def quote_is_in_source(source_quote: str, paragraph_text: str) -> bool:
    """
    Validate that the source quote appears inside the referenced IFRS paragraph.
    Allows whitespace-normalized matching and ignores trailing ellipsis.
    """
    quote = normalize_text(source_quote).replace("...", "").strip()
    paragraph = normalize_text(paragraph_text)

    if not quote:
        return False

    return quote in paragraph


def is_bank_specific(text: str) -> bool:
    """
    Disclosure catalog should not contain bank-specific facts.
    This catches obvious generated evidence that belongs in payloads, not IFRS requirements.
    """
    if not text:
        return False

    text_l = str(text).lower()

    forbidden_patterns = [
        r"\beurolux\b",
        r"\bbank01\b",
        r"\bey\b",
        r"\b\d+(\.\d+)?%\b",
        r"\b€\s?\d+",
        r"\beur\s?\d+",
        r"\bscope 1 .*?\d+",
        r"\bscope 2 .*?\d+",
        r"\bscope 3 .*?\d+",
        r"\bboard comprises \d+",
        r"\b\d+ members\b",
    ]

    return any(re.search(pattern, text_l) for pattern in forbidden_patterns)


def requirement_is_too_vague(summary: str) -> bool:
    """
    Detect very weak requirement summaries that are not useful for the Judge.
    """
    if not summary:
        return True

    summary_l = summary.lower().strip()

    vague_phrases = {
        "disclose information",
        "provide information",
        "disclose sustainability information",
        "disclose climate-related information",
        "disclose required information",
    }

    if summary_l in vague_phrases:
        return True

    if len(summary_l.split()) < 6:
        return True

    return False


def requirement_is_too_long(summary: str) -> bool:
    """
    A disclosure row should be checkable. Very long summaries are hard to use.
    """
    if not summary:
        return False
    return len(summary.split()) > 55


def required_evidence_is_useful(required_evidence) -> bool:
    """
    Required evidence should help the Judge compare the generated section to the bank payload.
    """
    evidence = parse_json_list(required_evidence)

    if len(evidence) == 0:
        return False

    joined = " ".join(str(x).lower() for x in evidence)

    weak_terms = [
        "evidence required by the source paragraph",
        "entity-specific facts supporting the disclosure",
    ]

    # If it only contains generic fallback phrases, it is weak.
    if all(any(term in str(item).lower() for term in weak_terms) for item in evidence):
        return False

    return True


# ============================================================
# LOAD FILES
# ============================================================

paragraphs = load_json(IFRS_PARAGRAPHS_JSON)
disclosures = load_json(DISCLOSURES_JSON)

paragraph_map = {
    (p.get("standard"), p.get("paragraph_id")): p
    for p in paragraphs
}

print(f"Loaded IFRS paragraphs: {len(paragraphs)}")
print(f"Loaded disclosure rows: {len(disclosures)}")


# ============================================================
# VALIDATION
# ============================================================

errors = []
warnings = []

seen_ids = set()
id_counts = Counter(d.get("disclosure_id") for d in disclosures)

for idx, row in enumerate(disclosures, start=1):
    row_id = row.get("disclosure_id", f"ROW_{idx}")

    # 1. Required fields
    for field in REQUIRED_DISCLOSURE_FIELDS:
        value = row.get(field)
        if value is None or value == "" or value == []:
            errors.append({
                "disclosure_id": row_id,
                "severity": "error",
                "check": "required_field",
                "message": f"Missing required field: {field}",
            })

    # 2. Duplicate disclosure ID
    if row.get("disclosure_id") and id_counts[row.get("disclosure_id")] > 1:
        errors.append({
            "disclosure_id": row_id,
            "severity": "error",
            "check": "duplicate_id",
            "message": "Duplicate disclosure_id.",
        })

    # 3. Valid standard
    standard = row.get("standard")
    if standard not in VALID_STANDARDS:
        errors.append({
            "disclosure_id": row_id,
            "severity": "error",
            "check": "standard",
            "message": f"Invalid standard: {standard}",
        })

    # 4. Valid core area
    core_area = row.get("core_area")
    if core_area not in VALID_CORE_AREAS:
        errors.append({
            "disclosure_id": row_id,
            "severity": "error",
            "check": "core_area",
            "message": f"Invalid core_area: {core_area}",
        })

    # 5. Source paragraph exists
    source_ids = parse_json_list(row.get("source_paragraph_ids"))

    if not source_ids:
        errors.append({
            "disclosure_id": row_id,
            "severity": "error",
            "check": "source_paragraph_ids",
            "message": "No source_paragraph_ids provided.",
        })

    for pid in source_ids:
        key = (standard, str(pid))
        if key not in paragraph_map:
            errors.append({
                "disclosure_id": row_id,
                "severity": "error",
                "check": "source_paragraph_exists",
                "message": f"Referenced paragraph not found: {standard} §{pid}",
            })
            continue

        # 6. Source quote appears in paragraph
        source_quote = row.get("source_quote", "")
        paragraph_text = paragraph_map[key].get("text", "")

        if not quote_is_in_source(source_quote, paragraph_text):
            errors.append({
                "disclosure_id": row_id,
                "severity": "error",
                "check": "source_quote",
                "message": f"source_quote not found in {standard} §{pid}",
            })

    # 7. Paragraph ref should look like an IFRS reference
    paragraph_ref = str(row.get("paragraph_ref", ""))
    if "IFRS" not in paragraph_ref or "§" not in paragraph_ref:
        warnings.append({
            "disclosure_id": row_id,
            "severity": "warning",
            "check": "paragraph_ref_format",
            "message": f"paragraph_ref format may be weak: {paragraph_ref}",
        })

    # 8. Requirement summary quality
    summary = row.get("requirement_summary", "")

    if requirement_is_too_vague(summary):
        warnings.append({
            "disclosure_id": row_id,
            "severity": "warning",
            "check": "summary_too_vague",
            "message": "requirement_summary may be too vague for Judge use.",
        })

    if requirement_is_too_long(summary):
        warnings.append({
            "disclosure_id": row_id,
            "severity": "warning",
            "check": "summary_too_long",
            "message": "requirement_summary may be too long and hard to check.",
        })

    # 9. Required evidence usefulness
    if not required_evidence_is_useful(row.get("required_evidence")):
        warnings.append({
            "disclosure_id": row_id,
            "severity": "warning",
            "check": "required_evidence_weak",
            "message": "required_evidence is generic or not useful for payload comparison.",
        })

    # 10. No bank-specific facts
    combined_text = " ".join([
        str(row.get("requirement_summary", "")),
        str(row.get("source_quote", "")),
        " ".join(parse_json_list(row.get("required_evidence"))),
        str(row.get("notes", "")),
    ])

    if is_bank_specific(combined_text):
        errors.append({
            "disclosure_id": row_id,
            "severity": "error",
            "check": "bank_specific_content",
            "message": "Disclosure catalog contains bank-specific facts. These belong in payloads, not IFRS requirements.",
        })


# ============================================================
# COVERAGE VALIDATION
# ============================================================

df = pd.DataFrame(disclosures)

coverage_by_standard = (
    df.groupby("standard").size().to_dict()
    if not df.empty and "standard" in df.columns
    else {}
)

coverage_by_core_area = (
    df.groupby("core_area").size().to_dict()
    if not df.empty and "core_area" in df.columns
    else {}
)

missing_core_areas = [
    area for area in IMPORTANT_CORE_AREAS
    if coverage_by_core_area.get(area, 0) == 0
]

for area in missing_core_areas:
    errors.append({
        "disclosure_id": "CATALOG",
        "severity": "error",
        "check": "coverage",
        "message": f"No disclosure rows found for core area: {area}",
    })


# ============================================================
# SCORING
# ============================================================

error_count = len(errors)
warning_count = len(warnings)
total_rows = len(disclosures)

source_grounding_errors = [
    e for e in errors
    if e["check"] in {
        "source_paragraph_exists",
        "source_quote",
        "source_paragraph_ids",
        "required_field",
    }
]

coverage_errors = [
    e for e in errors
    if e["check"] == "coverage"
]

bank_specific_errors = [
    e for e in errors
    if e["check"] == "bank_specific_content"
]

# Start from 10 and subtract penalties.
score = 10.0
score -= len(source_grounding_errors) * 1.0
score -= len(coverage_errors) * 1.0
score -= len(bank_specific_errors) * 1.5
score -= (error_count - len(source_grounding_errors) - len(coverage_errors) - len(bank_specific_errors)) * 0.5
score -= warning_count * 0.15
score = max(0, round(score, 1))

if score >= 9:
    status = "ready_for_judge"
elif score >= 7:
    status = "usable_with_manual_review"
elif score >= 5:
    status = "needs_cleanup"
else:
    status = "not_reliable_yet"

summary = {
    "total_disclosure_rows": total_rows,
    "total_ifrs_paragraphs": len(paragraphs),
    "errors": error_count,
    "warnings": warning_count,
    "source_grounding_errors": len(source_grounding_errors),
    "coverage_errors": len(coverage_errors),
    "bank_specific_errors": len(bank_specific_errors),
    "coverage_by_standard": coverage_by_standard,
    "coverage_by_core_area": coverage_by_core_area,
    "missing_core_areas": missing_core_areas,
    "score": score,
    "status": status,
}

print(json.dumps(summary, indent=2, ensure_ascii=False))


# ============================================================
# EXPORT VALIDATION FILES
# ============================================================

validation_results = {
    "summary": summary,
    "errors": errors,
    "warnings": warnings,
}

validation_json_path = OUTPUT_DIR / "disclosure_catalog_validation_results.json"
with open(validation_json_path, "w", encoding="utf-8") as f:
    json.dump(validation_results, f, indent=2, ensure_ascii=False)

# Markdown report
report_lines = []

report_lines.append("# Disclosure Catalog Validation Report")
report_lines.append("")
report_lines.append("## Summary")
report_lines.append("")
report_lines.append(f"- Total disclosure rows: **{total_rows}**")
report_lines.append(f"- Total IFRS paragraphs: **{len(paragraphs)}**")
report_lines.append(f"- Errors: **{error_count}**")
report_lines.append(f"- Warnings: **{warning_count}**")
report_lines.append(f"- Score: **{score}/10**")
report_lines.append(f"- Status: **{status}**")
report_lines.append("")

report_lines.append("## Coverage by standard")
report_lines.append("")
for key, value in coverage_by_standard.items():
    report_lines.append(f"- {key}: {value}")
report_lines.append("")

report_lines.append("## Coverage by core area")
report_lines.append("")
for key, value in coverage_by_core_area.items():
    report_lines.append(f"- {key}: {value}")
report_lines.append("")

report_lines.append("## Missing core areas")
report_lines.append("")
if missing_core_areas:
    for area in missing_core_areas:
        report_lines.append(f"- {area}")
else:
    report_lines.append("- None")
report_lines.append("")

report_lines.append("## Errors")
report_lines.append("")
if errors:
    for e in errors[:100]:
        report_lines.append(
            f"- `{e['disclosure_id']}` [{e['check']}]: {e['message']}"
        )
    if len(errors) > 100:
        report_lines.append(f"- ... {len(errors) - 100} more errors")
else:
    report_lines.append("- None")
report_lines.append("")

report_lines.append("## Warnings")
report_lines.append("")
if warnings:
    for w in warnings[:100]:
        report_lines.append(
            f"- `{w['disclosure_id']}` [{w['check']}]: {w['message']}"
        )
    if len(warnings) > 100:
        report_lines.append(f"- ... {len(warnings) - 100} more warnings")
else:
    report_lines.append("- None")
report_lines.append("")

VALIDATION_REPORT.write_text("\n".join(report_lines), encoding="utf-8")

print(f"\nValidation JSON saved to: {validation_json_path}")
print(f"Validation report saved to: {VALIDATION_REPORT}")