# ============================================================
# IFRS S1/S2 SOURCE-GROUNDED DISCLOSURE CATALOG GENERATOR
# ============================================================
#
# Purpose:
# - Convert IFRS S1 and IFRS S2 PDFs to Markdown.
# - Parse the Markdown into paragraph-level JSON.
# - Detect disclosure-requirement paragraphs.
# - Optionally use an LLM only to structure requirements from source paragraphs.
# - Validate every disclosure row against the extracted IFRS source text.
# - Export:
#     outputs/ifrs_s1.md
#     outputs/ifrs_s2.md
#     outputs/ifrs_paragraphs.json
#     outputs/disclosures_source_grounded.csv
#     outputs/disclosures_source_grounded.json
#     outputs/validation_report.md
#
# Recommended input layout:
#   data/ifrs/ifrs_s1.pdf
#   data/ifrs/ifrs_s2.pdf
#
# Install if needed:
#   pip install pymupdf4llm pymupdf pandas python-dotenv

from __future__ import annotations

import os
import re
import json
import time
import hashlib
import urllib.request
import urllib.error
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Any

import pandas as pd

try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(), override=True)
except Exception:
    pass

# ============================================================
# 0. CONFIG
# ============================================================

BASE_DIR = Path.cwd()

# Change these paths if your PDFs are somewhere else.
IFRS_S1_PDF = BASE_DIR / "gen_data" / "IFRS" / "ifrs_s1.pdf"
IFRS_S2_PDF = BASE_DIR / "gen_data" / "IFRS" / "ifrs_s2.pdf"

OUTPUT_DIR = BASE_DIR / "gen_data" / "IFRS" / "ifrs_disclosures"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

S1_MD_PATH = OUTPUT_DIR / "ifrs_s1.md"
S2_MD_PATH = OUTPUT_DIR / "ifrs_s2.md"

IFRS_PARAGRAPHS_JSON = OUTPUT_DIR / "ifrs_paragraphs.json"
DISCLOSURES_JSON = OUTPUT_DIR / "disclosures_source_grounded.json"
DISCLOSURES_CSV = OUTPUT_DIR / "disclosures_source_grounded.csv"
VALIDATION_REPORT = OUTPUT_DIR / "validation_report.md"

# If True, the notebook calls your Azure/OpenAI-compatible endpoint to structure each candidate paragraph.
# If False, it creates deterministic draft disclosure rows from candidate paragraphs.
USE_LLM = False

# Full Azure/OpenAI-compatible chat-completions URL.
# Example:
# AZURE_OPENAI_DISCLOSURE_URL=https://.../openai/deployments/gpt-5.2/chat/completions?api-version=...
DISCLOSURE_LLM_URL = os.getenv("AZURE_OPENAI_DISCLOSURE_URL") or os.getenv("AZURE_OPENAI_JUDGE_URL")
DISCLOSURE_LLM_KEY = (
    os.getenv("AZURE_OPENAI_DISCLOSURE_API_KEY")
    or os.getenv("AZURE_OPENAI_JUDGE_API_KEY")
    or os.getenv("AZURE_OPENAI_API_KEY")
)

print("Base directory:", BASE_DIR)
print("Output directory:", OUTPUT_DIR)
print("S1 PDF exists:", IFRS_S1_PDF.exists(), IFRS_S1_PDF)
print("S2 PDF exists:", IFRS_S2_PDF.exists(), IFRS_S2_PDF)
print("USE_LLM:", USE_LLM)

# ============================================================
# 1. PDF → MARKDOWN
# ============================================================

def convert_pdf_to_markdown(pdf_path: Path, md_path: Path) -> str:
    """
    Convert a PDF to Markdown using pymupdf4llm.

    Markdown is used as an intermediate because it usually preserves headings,
    paragraph numbers, lists, and appendices better than plain PDF text.
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    try:
        import pymupdf4llm
    except ImportError as exc:
        raise ImportError(
            "pymupdf4llm is required. Install it with: pip install pymupdf4llm"
        ) from exc

    md_text = pymupdf4llm.to_markdown(str(pdf_path))
    md_path.write_text(md_text, encoding="utf-8")
    return md_text


s1_md = convert_pdf_to_markdown(IFRS_S1_PDF, S1_MD_PATH)
s2_md = convert_pdf_to_markdown(IFRS_S2_PDF, S2_MD_PATH)

print("Markdown exported:")
print("-", S1_MD_PATH, len(s1_md), "chars")
print("-", S2_MD_PATH, len(s2_md), "chars")

# ============================================================
# 2. PARAGRAPH MODEL
# ============================================================

@dataclass
class IFRSParagraph:
    standard: str
    paragraph_id: str
    core_area: str
    heading: str
    text: str
    source_document: str
    source_markdown: str
    order_index: int
    is_appendix: bool
    source_hash: str
    raw_block: str = ""


@dataclass
class DisclosureRequirement:
    disclosure_id: str
    standard: str
    core_area: str
    subtopic: str
    paragraph_ref: str
    requirement_summary: str
    required_evidence: list[str]
    source_paragraph_ids: list[str]
    source_quote: str
    is_climate_specific: bool
    priority: str
    notes: str = ""


# ============================================================
# 3. PARAGRAPH PARSING
# ============================================================

# Captures IFRS paragraph IDs like:
# 6
# 6(a)
# 6(a)(i)
# B13
# B13(a)
# C2
# D4
# E1
PARA_START_PATTERN = re.compile(
    r"""
    ^\s*
    (?P<bold_open>\*\*)?
    (?P<pid>
        (?:[A-E]\d+[A-Za-z]?(?:\([a-z]\))?(?:\([ivx]+\))?)
        |
        (?:\d+[A-Za-z]?(?:\([a-z]\))?(?:\([ivx]+\))?)
    )
    (?P<bold_close>\*\*)?
    [\.\s]+
    (?P<rest>.+?)
    \s*$
    """,
    re.VERBOSE | re.IGNORECASE,
)

HEADING_PATTERN = re.compile(
    r"""
    ^\s*
    (?:
        \#{1,6}\s+
        |
        \*\*
    )?
    (?P<heading>
        [A-Z][A-Za-z\s,\-/&:()]{3,120}
    )
    (?:
        \*\*
    )?
    \s*$
    """,
    re.VERBOSE,
)

CORE_AREA_KEYWORDS = {
    "Governance": [
        "governance",
        "board",
        "committee",
        "management responsibility",
        "remuneration",
        "oversight",
    ],
    "Strategy": [
        "strategy",
        "business model",
        "value chain",
        "financial effects",
        "climate resilience",
        "scenario analysis",
        "resilience",
    ],
    "Risk Management": [
        "risk management",
        "identify",
        "assess",
        "prioritise",
        "prioritize",
        "monitor",
        "risk process",
    ],
    "Metrics and Targets": [
        "metrics",
        "targets",
        "greenhouse gas",
        "ghg",
        "emissions",
        "scope 1",
        "scope 2",
        "scope 3",
        "industry-based",
    ],
    "General Requirements": [
        "materiality",
        "fair presentation",
        "connected information",
        "judgements",
        "uncertainty",
        "basis of preparation",
        "comparative",
        "errors",
        "statement of compliance",
        "location of disclosures",
    ],
}


def normalize_text(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_markdown_line(line: str) -> str:
    line = line.strip()
    line = re.sub(r"^\s*#+\s*", "", line)
    line = line.strip("*").strip()
    line = re.sub(r"\s+", " ", line)
    return line


def infer_core_area(standard: str, pid: str, heading: str, text: str) -> str:
    """
    Infer core area from heading/text and known IFRS S1/S2 paragraph ranges.

    This is a practical mapping for report-generation checklists.
    Always keep paragraph_ref/source_quote for traceability.
    """
    combined = f"{heading} {text}".lower()

    for area, keywords in CORE_AREA_KEYWORDS.items():
        if any(k.lower() in combined for k in keywords):
            return area

    # Fallback range mapping based on common IFRS S1/S2 structures.
    # This is used only when heading keywords are not enough.
    num_match = re.match(r"(\d+)", pid)
    if num_match:
        n = int(num_match.group(1))

        if standard == "IFRS_S2":
            if 5 <= n <= 7:
                return "Governance"
            if 8 <= n <= 22:
                return "Strategy"
            if 24 <= n <= 27:
                return "Risk Management"
            if 28 <= n <= 37:
                return "Metrics and Targets"

        if standard == "IFRS_S1":
            if 26 <= n <= 27:
                return "Governance"
            if 28 <= n <= 42:
                return "Strategy"
            if 43 <= n <= 44:
                return "Risk Management"
            if 45 <= n <= 53:
                return "Metrics and Targets"
            return "General Requirements"

    if pid.upper().startswith(("B", "C", "D", "E")):
        return "General Requirements"

    return "General Requirements"


def parse_ifrs_markdown(
    md_text: str,
    standard: str,
    source_document: str,
    source_markdown: str,
) -> list[IFRSParagraph]:
    """
    Parse Markdown into paragraph-level IFRS records.

    The parser starts a new record whenever a line begins with an IFRS paragraph ID.
    Continuation lines are appended until the next paragraph ID.
    """
    md_text = normalize_text(md_text)
    lines = md_text.splitlines()

    paragraphs: list[IFRSParagraph] = []
    current_heading = "Unknown"
    current_pid: str | None = None
    current_lines: list[str] = []
    current_raw: list[str] = []

    def flush():
        nonlocal current_pid, current_lines, current_raw, current_heading

        if not current_pid or not current_lines:
            current_pid = None
            current_lines = []
            current_raw = []
            return

        text = normalize_text("\n".join(current_lines))
        raw = "\n".join(current_raw).strip()

        # Skip very short fragments unless they are likely requirements.
        if len(text.split()) >= 4:
            core_area = infer_core_area(
                standard=standard,
                pid=current_pid,
                heading=current_heading,
                text=text,
            )
            paragraphs.append(
                IFRSParagraph(
                    standard=standard,
                    paragraph_id=current_pid,
                    core_area=core_area,
                    heading=current_heading,
                    text=text,
                    source_document=source_document,
                    source_markdown=source_markdown,
                    order_index=len(paragraphs),
                    is_appendix=bool(re.match(r"^[A-E]", current_pid, re.I)),
                    source_hash=hashlib.sha256(
                        f"{standard}:{current_pid}:{text}".encode("utf-8")
                    ).hexdigest()[:16],
                    raw_block=raw,
                )
            )

        current_pid = None
        current_lines = []
        current_raw = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current_pid:
                current_lines.append("")
                current_raw.append(line)
            continue

        # Detect headings, but do not treat numbered paragraphs as headings.
        para_match = PARA_START_PATTERN.match(stripped)

        if not para_match:
            h = HEADING_PATTERN.match(stripped)
            cleaned = clean_markdown_line(stripped)
            if h and len(cleaned.split()) <= 12 and not re.match(r"^\d", cleaned):
                # Avoid setting ordinary sentences as headings.
                lower = cleaned.lower()
                if any(
                    key in lower
                    for key in [
                        "governance",
                        "strategy",
                        "risk management",
                        "metrics",
                        "targets",
                        "appendix",
                        "objective",
                        "scope",
                        "definitions",
                        "materiality",
                        "judgements",
                        "uncertainty",
                    ]
                ):
                    current_heading = cleaned
                    if current_pid:
                        current_raw.append(line)
                    continue

        if para_match:
            flush()
            current_pid = para_match.group("pid")
            rest = para_match.group("rest").strip()
            current_lines = [rest]
            current_raw = [line]
        else:
            if current_pid:
                current_lines.append(stripped)
                current_raw.append(line)

    flush()

    # Deduplicate repeated paragraph IDs by keeping the longer text.
    by_key: dict[tuple[str, str], IFRSParagraph] = {}
    for p in paragraphs:
        key = (p.standard, p.paragraph_id)
        if key not in by_key or len(p.text) > len(by_key[key].text):
            by_key[key] = p

    deduped = list(by_key.values())
    deduped.sort(key=lambda p: p.order_index)

    # Re-index after dedupe.
    for i, p in enumerate(deduped):
        p.order_index = i

    return deduped


s1_paragraphs = parse_ifrs_markdown(
    s1_md,
    standard="IFRS_S1",
    source_document=str(IFRS_S1_PDF),
    source_markdown=str(S1_MD_PATH),
)
s2_paragraphs = parse_ifrs_markdown(
    s2_md,
    standard="IFRS_S2",
    source_document=str(IFRS_S2_PDF),
    source_markdown=str(S2_MD_PATH),
)

ifrs_paragraphs = s1_paragraphs + s2_paragraphs

with open(IFRS_PARAGRAPHS_JSON, "w", encoding="utf-8") as f:
    json.dump([asdict(p) for p in ifrs_paragraphs], f, indent=2, ensure_ascii=False)

print("Parsed IFRS paragraphs:", len(ifrs_paragraphs))
print("S1 paragraphs:", len(s1_paragraphs))
print("S2 paragraphs:", len(s2_paragraphs))
print("Saved:", IFRS_PARAGRAPHS_JSON)

# Quick inspection
pd.DataFrame([asdict(p) for p in ifrs_paragraphs]).head(10)

# ============================================================
# 4. PARAGRAPH EXTRACTION VALIDATION
# ============================================================

def paragraph_lookup(paragraphs: list[IFRSParagraph]) -> dict[tuple[str, str], IFRSParagraph]:
    return {(p.standard, p.paragraph_id): p for p in paragraphs}


lookup = paragraph_lookup(ifrs_paragraphs)

IMPORTANT_PARAGRAPHS = [
    ("IFRS_S1", "26"),
    ("IFRS_S1", "27"),
    ("IFRS_S1", "28"),
    ("IFRS_S1", "43"),
    ("IFRS_S1", "45"),
    ("IFRS_S2", "5"),
    ("IFRS_S2", "6"),
    ("IFRS_S2", "7"),
    ("IFRS_S2", "8"),
    ("IFRS_S2", "10"),
    ("IFRS_S2", "13"),
    ("IFRS_S2", "21"),
    ("IFRS_S2", "22"),
    ("IFRS_S2", "25"),
    ("IFRS_S2", "28"),
    ("IFRS_S2", "29"),
    ("IFRS_S2", "33"),
]

missing_important = [
    f"{std} §{pid}" for std, pid in IMPORTANT_PARAGRAPHS
    if (std, pid) not in lookup
]

duplicates = (
    pd.DataFrame([asdict(p) for p in ifrs_paragraphs])
    .groupby(["standard", "paragraph_id"])
    .size()
    .reset_index(name="count")
)
duplicates = duplicates[duplicates["count"] > 1]

print("Missing important paragraphs:", missing_important)
print("Duplicate paragraph IDs:", len(duplicates))
if len(duplicates):
    display(duplicates)

# ============================================================
# 5. DETECT CANDIDATE DISCLOSURE PARAGRAPHS
# ============================================================

DISCLOSURE_PATTERNS = [
    r"\bshall disclose\b",
    r"\bshall provide\b",
    r"\bis required to disclose\b",
    r"\ban entity shall disclose\b",
    r"\ban entity shall provide\b",
    r"\binformation that enables users\b",
    r"\bdisclose information\b",
    r"\bdisclose\b",
]

DISCLOSURE_REGEX = re.compile("|".join(DISCLOSURE_PATTERNS), flags=re.IGNORECASE)

RELEVANT_CORE_AREAS = {
    "Governance",
    "Strategy",
    "Risk Management",
    "Metrics and Targets",
    "General Requirements",
}


def is_candidate_disclosure(p: IFRSParagraph) -> bool:
    if p.core_area not in RELEVANT_CORE_AREAS:
        return False
    return bool(DISCLOSURE_REGEX.search(p.text))


candidate_paragraphs = [p for p in ifrs_paragraphs if is_candidate_disclosure(p)]

candidate_df = pd.DataFrame([asdict(p) for p in candidate_paragraphs])
candidate_path = OUTPUT_DIR / "candidate_disclosure_paragraphs.csv"
candidate_df.to_csv(candidate_path, index=False, encoding="utf-8")

print("Candidate disclosure paragraphs:", len(candidate_paragraphs))
print("Saved:", candidate_path)

candidate_df[["standard", "paragraph_id", "core_area", "heading", "text"]].head(20)

# ============================================================
# 6. OPTIONAL LLM STRUCTURING
# ============================================================

def azure_chat_completion_json(
    system_prompt: str,
    user_prompt: str,
    *,
    max_output_tokens: int = 1200,
    timeout: int = 180,
) -> dict[str, Any]:
    """
    Call Azure/OpenAI-compatible chat completions and return parsed JSON.

    This is optional and only used when USE_LLM = True.
    """
    if not DISCLOSURE_LLM_URL or not DISCLOSURE_LLM_KEY:
        raise ValueError(
            "Missing AZURE_OPENAI_DISCLOSURE_URL/AZURE_OPENAI_DISCLOSURE_API_KEY "
            "or fallback AZURE_OPENAI_JUDGE_URL/AZURE_OPENAI_API_KEY."
        )

    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_completion_tokens": max_output_tokens,
        "response_format": {"type": "json_object"},
    }

    req = urllib.request.Request(
        DISCLOSURE_LLM_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "api-key": DISCLOSURE_LLM_KEY,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise RuntimeError(
            f"LLM HTTP error {exc.code}\nResponse:\n{body[:2000]}"
        ) from exc

    content = data["choices"][0]["message"]["content"]
    return json.loads(content)


STRUCTURE_SYSTEM_PROMPT = """
You extract structured IFRS disclosure requirements from source text.

Rules:
- Use ONLY the provided paragraph text.
- Do not invent requirements.
- Do not use memory.
- Every row must be grounded in the paragraph.
- Return valid JSON only.
""".strip()


def make_disclosure_id(
    standard: str,
    core_area: str,
    paragraph_id: str,
    index: int,
) -> str:
    std = standard.replace("IFRS_", "")
    area = re.sub(r"[^A-Za-z0-9]+", "_", core_area.upper()).strip("_")
    pid = re.sub(r"[^A-Za-z0-9]+", "_", paragraph_id.upper()).strip("_")
    return f"{std}_{area}_{pid}_{index:02d}"


def deterministic_requirement_from_paragraph(p: IFRSParagraph, index: int = 1) -> DisclosureRequirement:
    """
    Fallback requirement row when USE_LLM=False.

    It does not summarize creatively; it creates a conservative source-backed row.
    """
    quote = p.text[:280].strip()
    if len(p.text) > 280:
        quote = quote.rsplit(" ", 1)[0] + "..."

    return DisclosureRequirement(
        disclosure_id=make_disclosure_id(p.standard, p.core_area, p.paragraph_id, index),
        standard=p.standard,
        core_area=p.core_area,
        subtopic=p.heading,
        paragraph_ref=f"{p.standard.replace('_', ' ')} §{p.paragraph_id}",
        requirement_summary=(
            f"Disclose the information required by {p.standard.replace('_', ' ')} "
            f"paragraph {p.paragraph_id} under {p.core_area}."
        ),
        required_evidence=[
            "Evidence required by the source paragraph",
            "Entity-specific facts supporting the disclosure",
            "Evidence boundaries where information is unavailable",
        ],
        source_paragraph_ids=[p.paragraph_id],
        source_quote=quote,
        is_climate_specific=(p.standard == "IFRS_S2"),
        priority="high" if p.core_area != "General Requirements" else "medium",
        notes="Deterministic row created from candidate paragraph; review recommended.",
    )


def llm_requirements_from_paragraph(p: IFRSParagraph) -> list[DisclosureRequirement]:
    """
    Use the LLM to split/structure a candidate paragraph into one or more requirements.
    """
    user_prompt = f"""
Extract disclosure requirements from the IFRS paragraph below.

Return JSON in this exact shape:
{{
  "requirements": [
    {{
      "subtopic": "short subtopic",
      "requirement_summary": "clear requirement summary",
      "required_evidence": ["evidence item 1", "evidence item 2"],
      "source_quote": "short exact quote from the paragraph",
      "priority": "high|medium|low",
      "notes": "optional"
    }}
  ]
}}

Source metadata:
standard: {p.standard}
core_area: {p.core_area}
paragraph_id: {p.paragraph_id}
heading: {p.heading}

Paragraph text:
{p.text}

Strict rules:
- Use only this paragraph text.
- source_quote must be an exact substring from the paragraph text.
- Do not add bank-specific facts.
- If the paragraph has no actual disclosure requirement, return {{"requirements": []}}.
""".strip()

    response = azure_chat_completion_json(
        STRUCTURE_SYSTEM_PROMPT,
        user_prompt,
        max_output_tokens=1200,
    )

    rows = []
    requirements = response.get("requirements", [])
    for idx, req in enumerate(requirements, start=1):
        rows.append(
            DisclosureRequirement(
                disclosure_id=make_disclosure_id(
                    p.standard,
                    p.core_area,
                    p.paragraph_id,
                    idx,
                ),
                standard=p.standard,
                core_area=p.core_area,
                subtopic=req.get("subtopic") or p.heading,
                paragraph_ref=f"{p.standard.replace('_', ' ')} §{p.paragraph_id}",
                requirement_summary=req.get("requirement_summary", "").strip(),
                required_evidence=req.get("required_evidence", []),
                source_paragraph_ids=[p.paragraph_id],
                source_quote=req.get("source_quote", "").strip(),
                is_climate_specific=(p.standard == "IFRS_S2"),
                priority=req.get("priority") or ("high" if p.core_area != "General Requirements" else "medium"),
                notes=req.get("notes", ""),
            )
        )

    return rows


# ============================================================
# 7. GENERATE DISCLOSURE CATALOG
# ============================================================

disclosures: list[DisclosureRequirement] = []

for i, paragraph in enumerate(candidate_paragraphs, start=1):
    if USE_LLM:
        try:
            rows = llm_requirements_from_paragraph(paragraph)
            disclosures.extend(rows)
            time.sleep(0.2)
        except Exception as exc:
            print(f"LLM failed for {paragraph.standard} §{paragraph.paragraph_id}: {exc}")
            disclosures.append(deterministic_requirement_from_paragraph(paragraph, index=1))
    else:
        disclosures.append(deterministic_requirement_from_paragraph(paragraph, index=1))

print("Generated disclosure rows before validation:", len(disclosures))

# ============================================================
# 8. VALIDATE DISCLOSURE CATALOG
# ============================================================

from collections import Counter
from difflib import SequenceMatcher

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


def _row_to_dict(row: DisclosureRequirement | dict) -> dict[str, Any]:
    """Support both dataclass rows and dict rows."""
    if isinstance(row, DisclosureRequirement):
        return asdict(row)
    if isinstance(row, dict):
        return row
    raise TypeError(f"Unsupported disclosure row type: {type(row)}")


def _get_row_value(row: DisclosureRequirement | dict, field: str, default=None):
    if isinstance(row, DisclosureRequirement):
        return getattr(row, field, default)
    return row.get(field, default)


def parse_json_list(value) -> list:
    """
    Convert CSV-style JSON string lists back to Python lists when needed.
    Works with JSON rows, dataclasses, and CSV-loaded values.
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


def quote_is_supported(source_quote: str, paragraph_text: str) -> bool:
    """
    Validate that the source quote is grounded in the referenced paragraph.

    Rules:
    - exact/whitespace-normalized substring match passes;
    - quote with trailing ellipsis is allowed;
    - minor whitespace/punctuation conversion is tolerated;
    - paraphrases should still fail.
    """
    if not source_quote or not paragraph_text:
        return False

    quote = normalize_text(str(source_quote)).replace("...", "").strip()
    paragraph = normalize_text(str(paragraph_text)).strip()

    if not quote:
        return False

    if quote in paragraph:
        return True

    # Looser normalized version: remove most punctuation while preserving words.
    quote_words = re.sub(r"[^A-Za-z0-9]+", " ", quote).lower().strip()
    para_words = re.sub(r"[^A-Za-z0-9]+", " ", paragraph).lower().strip()

    if quote_words and quote_words in para_words:
        return True

    # If the quote is long, allow a high similarity window.
    # This catches minor extraction differences but still rejects paraphrases.
    if len(quote_words) >= 80:
        q_len = len(quote_words)
        best_ratio = 0.0
        step = max(20, q_len // 8)
        for start in range(0, max(1, len(para_words) - q_len + 1), step):
            window = para_words[start:start + q_len + 40]
            best_ratio = max(best_ratio, SequenceMatcher(None, quote_words, window).ratio())
            if best_ratio >= 0.90:
                return True

    return False


def is_bank_specific_content(text: str) -> bool:
    """
    The disclosure catalog must not contain bank-specific facts.
    These belong in bank payloads / compact evidence, not in the IFRS requirements catalog.
    """
    if not text:
        return False

    text_l = str(text).lower()

    forbidden_patterns = [
        r"\bbank0\d\b",
        r"\beurolux\b",
        r"\bey\b",
        r"\b\d+(\.\d+)?%\b",
        r"\b€\s?\d+",
        r"\beur\s?\d+",
        r"\b\d+(\.\d+)?\s?(million|billion|m|bn)\b",
        r"\bboard comprises \d+",
        r"\b\d+\s+members\b",
        r"\bscope\s*[123].*?\d+",
    ]

    return any(re.search(pattern, text_l) for pattern in forbidden_patterns)


def requirement_summary_too_vague(summary: str) -> bool:
    """Detect requirement summaries that are too vague to help the Judge agent."""
    if not summary:
        return True

    s = str(summary).strip().lower()
    vague_exact = {
        "disclose information",
        "provide information",
        "disclose sustainability information",
        "disclose climate-related information",
        "disclose required information",
        "provide required information",
    }

    if s in vague_exact:
        return True

    return len(s.split()) < 6


def requirement_summary_too_long(summary: str) -> bool:
    """Very long summaries are difficult for the Judge to check."""
    return bool(summary) and len(str(summary).split()) > 60


def required_evidence_is_useful(required_evidence) -> bool:
    """
    Required evidence should be specific enough to guide the Judge.
    Generic fallback evidence is allowed but warned.
    """
    items = parse_json_list(required_evidence)
    if not items:
        return False

    generic_phrases = [
        "evidence required by the source paragraph",
        "entity-specific facts supporting the disclosure",
        "evidence boundaries where information is unavailable",
    ]

    normalized = [str(item).strip().lower() for item in items if str(item).strip()]
    if not normalized:
        return False

    # If all items are generic fallback strings, this is weak.
    if all(any(g in item for g in generic_phrases) for item in normalized):
        return False

    return True


def validate_disclosures(
    disclosure_rows: list[DisclosureRequirement],
    paragraph_map: dict[tuple[str, str], IFRSParagraph],
) -> tuple[list[DisclosureRequirement], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """
    Validate disclosure rows for:
    - required fields;
    - source paragraph existence;
    - source quote grounding;
    - coverage;
    - duplicate IDs;
    - no bank-specific facts;
    - Judge-readiness quality warnings.

    Returns:
    - valid rows kept for export;
    - errors;
    - warnings;
    - summary.
    """
    valid_rows: list[DisclosureRequirement] = []
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    row_dicts = [_row_to_dict(row) for row in disclosure_rows]
    id_counts = Counter(row.get("disclosure_id") for row in row_dicts)

    for idx, row in enumerate(disclosure_rows, start=1):
        rd = _row_to_dict(row)
        row_id = rd.get("disclosure_id") or f"ROW_{idx}"
        row_errors: list[str] = []
        row_warnings: list[str] = []

        # 1. Required fields
        for field in REQUIRED_DISCLOSURE_FIELDS:
            value = rd.get(field)
            if value is None or value == "" or value == []:
                row_errors.append(f"missing_required_field:{field}")

        # 2. Valid standards and core areas
        standard = rd.get("standard")
        core_area = rd.get("core_area")

        if standard not in VALID_STANDARDS:
            row_errors.append(f"invalid_standard:{standard}")

        if core_area not in VALID_CORE_AREAS:
            row_errors.append(f"invalid_core_area:{core_area}")

        # 3. Duplicate ID
        if rd.get("disclosure_id") and id_counts[rd.get("disclosure_id")] > 1:
            row_errors.append("duplicate_disclosure_id")

        # 4. Paragraph reference format
        paragraph_ref = str(rd.get("paragraph_ref", ""))
        if "IFRS" not in paragraph_ref or "§" not in paragraph_ref:
            row_warnings.append(f"weak_paragraph_ref_format:{paragraph_ref}")

        # 5. Source paragraph existence + source quote grounding
        source_ids = parse_json_list(rd.get("source_paragraph_ids"))
        if not source_ids:
            row_errors.append("missing_source_paragraph_ids")

        quote_supported_anywhere = False

        for pid in source_ids:
            pid = str(pid)
            key = (standard, pid)

            if key not in paragraph_map:
                row_errors.append(f"source_paragraph_not_found:{standard}§{pid}")
                continue

            paragraph_text = paragraph_map[key].text
            source_quote = rd.get("source_quote", "")

            if quote_is_supported(source_quote, paragraph_text):
                quote_supported_anywhere = True

        if source_ids and not quote_supported_anywhere:
            row_errors.append("source_quote_not_found_in_referenced_paragraphs")

        # 6. Summary quality
        summary = rd.get("requirement_summary", "")

        if requirement_summary_too_vague(summary):
            row_warnings.append("requirement_summary_too_vague")

        if requirement_summary_too_long(summary):
            row_warnings.append("requirement_summary_too_long")

        # 7. Required evidence usefulness
        if not required_evidence_is_useful(rd.get("required_evidence")):
            row_warnings.append("required_evidence_too_generic")

        # 8. No bank-specific facts
        combined_text = " ".join([
            str(rd.get("requirement_summary", "")),
            str(rd.get("source_quote", "")),
            " ".join(str(x) for x in parse_json_list(rd.get("required_evidence"))),
            str(rd.get("notes", "")),
        ])

        if is_bank_specific_content(combined_text):
            row_errors.append("bank_specific_content_detected")

        if row_errors:
            errors.append({
                "disclosure_id": row_id,
                "standard": standard,
                "paragraph_ref": paragraph_ref,
                "errors": row_errors,
            })
        else:
            valid_rows.append(row)

        if row_warnings:
            warnings.append({
                "disclosure_id": row_id,
                "standard": standard,
                "paragraph_ref": paragraph_ref,
                "warnings": row_warnings,
            })

    # 9. Coverage checks on rows that survived hard validation.
    valid_records = [_row_to_dict(row) for row in valid_rows]
    coverage_by_standard = dict(Counter(row.get("standard") for row in valid_records))
    coverage_by_core_area = dict(Counter(row.get("core_area") for row in valid_records))

    missing_core_areas = [
        area for area in sorted(IMPORTANT_CORE_AREAS)
        if coverage_by_core_area.get(area, 0) == 0
    ]

    for area in missing_core_areas:
        errors.append({
            "disclosure_id": "CATALOG",
            "standard": "ALL",
            "paragraph_ref": "",
            "errors": [f"missing_core_area_coverage:{area}"],
        })

    # 10. Scoring.
    source_grounding_error_count = sum(
        1 for e in errors
        for msg in e.get("errors", [])
        if (
            msg.startswith("source_paragraph_not_found")
            or msg == "source_quote_not_found_in_referenced_paragraphs"
            or msg == "missing_source_paragraph_ids"
            or msg.startswith("missing_required_field")
        )
    )
    bank_specific_error_count = sum(
        1 for e in errors
        for msg in e.get("errors", [])
        if msg == "bank_specific_content_detected"
    )
    coverage_error_count = len(missing_core_areas)

    score = 10.0
    score -= source_grounding_error_count * 1.0
    score -= bank_specific_error_count * 1.5
    score -= coverage_error_count * 1.0
    score -= max(0, len(errors) - source_grounding_error_count - bank_specific_error_count - coverage_error_count) * 0.5
    score -= len(warnings) * 0.10
    score = max(0.0, round(score, 1))

    if score >= 9 and not errors:
        status = "ready_for_judge"
    elif score >= 7:
        status = "usable_with_manual_review"
    elif score >= 5:
        status = "needs_cleanup"
    else:
        status = "not_reliable_yet"

    summary = {
        "total_candidate_rows": len(disclosure_rows),
        "valid_rows": len(valid_rows),
        "rejected_rows": len(errors),
        "warnings": len(warnings),
        "score": score,
        "status": status,
        "coverage_by_standard": coverage_by_standard,
        "coverage_by_core_area": coverage_by_core_area,
        "missing_core_areas": missing_core_areas,
        "source_grounding_errors": source_grounding_error_count,
        "bank_specific_errors": bank_specific_error_count,
        "coverage_errors": coverage_error_count,
    }

    return valid_rows, errors, warnings, summary


valid_disclosures, validation_errors, validation_warnings, validation_summary = validate_disclosures(
    disclosures,
    lookup,
)

validation_results = {
    "summary": validation_summary,
    "errors": validation_errors,
    "warnings": validation_warnings,
}

VALIDATION_RESULTS_JSON = OUTPUT_DIR / "disclosure_catalog_validation_results.json"
with open(VALIDATION_RESULTS_JSON, "w", encoding="utf-8") as f:
    json.dump(validation_results, f, indent=2, ensure_ascii=False)

print("Disclosure catalog validation summary:")
print(json.dumps(validation_summary, indent=2, ensure_ascii=False))

if validation_errors[:10]:
    print("\nFirst validation errors:")
    for err in validation_errors[:10]:
        print(err)

if validation_warnings[:10]:
    print("\nFirst validation warnings:")
    for warn in validation_warnings[:10]:
        print(warn)

# ============================================================
# 9. EXPORT DISCLOSURES
# ============================================================

disclosure_records = [asdict(d) for d in valid_disclosures]

with open(DISCLOSURES_JSON, "w", encoding="utf-8") as f:
    json.dump(disclosure_records, f, indent=2, ensure_ascii=False)

df = pd.DataFrame(disclosure_records)

# Store required_evidence/source_paragraph_ids as JSON strings for CSV readability.
if not df.empty:
    df["required_evidence"] = df["required_evidence"].apply(
        lambda x: json.dumps(x, ensure_ascii=False)
    )
    df["source_paragraph_ids"] = df["source_paragraph_ids"].apply(
        lambda x: json.dumps(x, ensure_ascii=False)
    )

df.to_csv(DISCLOSURES_CSV, index=False, encoding="utf-8")

print("Exported:")
print("-", DISCLOSURES_JSON)
print("-", DISCLOSURES_CSV)

display(df.head(20))

# ============================================================
# 10. VALIDATION REPORT
# ============================================================

def count_by(records: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts = {}
    for r in records:
        value = r.get(field, "Unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


report_lines = []
report_lines.append("# IFRS Disclosure Catalog Validation Report")
report_lines.append("")
report_lines.append("## Input documents")
report_lines.append(f"- IFRS S1 PDF: `{IFRS_S1_PDF}`")
report_lines.append(f"- IFRS S2 PDF: `{IFRS_S2_PDF}`")
report_lines.append("")
report_lines.append("## Extraction summary")
report_lines.append(f"- IFRS paragraphs parsed: **{len(ifrs_paragraphs)}**")
report_lines.append(f"- IFRS S1 paragraphs parsed: **{len(s1_paragraphs)}**")
report_lines.append(f"- IFRS S2 paragraphs parsed: **{len(s2_paragraphs)}**")
report_lines.append(f"- Candidate disclosure paragraphs: **{len(candidate_paragraphs)}**")
report_lines.append(f"- Candidate disclosure rows: **{validation_summary['total_candidate_rows']}**")
report_lines.append(f"- Valid disclosure rows: **{validation_summary['valid_rows']}**")
report_lines.append(f"- Rejected disclosure rows: **{validation_summary['rejected_rows']}**")
report_lines.append(f"- Validation warnings: **{validation_summary['warnings']}**")
report_lines.append(f"- Validation score: **{validation_summary['score']}/10**")
report_lines.append(f"- Status: **{validation_summary['status']}**")
report_lines.append("")
report_lines.append("## Missing important paragraphs")
if missing_important:
    for item in missing_important:
        report_lines.append(f"- {item}")
else:
    report_lines.append("- None")
report_lines.append("")
report_lines.append("## Disclosure rows by standard")
for key, value in validation_summary.get("coverage_by_standard", {}).items():
    report_lines.append(f"- {key}: {value}")
report_lines.append("")
report_lines.append("## Disclosure rows by core area")
for key, value in validation_summary.get("coverage_by_core_area", {}).items():
    report_lines.append(f"- {key}: {value}")
report_lines.append("")
report_lines.append("## Missing core-area coverage")
missing_areas = validation_summary.get("missing_core_areas", [])
if missing_areas:
    for area in missing_areas:
        report_lines.append(f"- {area}")
else:
    report_lines.append("- None")
report_lines.append("")
report_lines.append("## Validation errors")
if validation_errors:
    for err in validation_errors[:100]:
        report_lines.append(
            f"- `{err['disclosure_id']}` ({err.get('paragraph_ref', '')}): "
            f"{', '.join(err.get('errors', []))}"
        )
    if len(validation_errors) > 100:
        report_lines.append(f"- ... {len(validation_errors) - 100} more errors")
else:
    report_lines.append("- None")
report_lines.append("")
report_lines.append("## Validation warnings")
if validation_warnings:
    for warn in validation_warnings[:100]:
        report_lines.append(
            f"- `{warn['disclosure_id']}` ({warn.get('paragraph_ref', '')}): "
            f"{', '.join(warn.get('warnings', []))}"
        )
    if len(validation_warnings) > 100:
        report_lines.append(f"- ... {len(validation_warnings) - 100} more warnings")
else:
    report_lines.append("- None")
report_lines.append("")
report_lines.append("## Evaluation meaning")
report_lines.append("- `ready_for_judge`: catalog is source-grounded and usable directly by the Judge agent.")
report_lines.append("- `usable_with_manual_review`: catalog is usable, but warnings should be reviewed.")
report_lines.append("- `needs_cleanup`: fix rejected rows and coverage gaps before using in production.")
report_lines.append("- `not_reliable_yet`: do not use as the Judge checklist yet.")
report_lines.append("")
report_lines.append("## Output files")
report_lines.append(f"- `{IFRS_PARAGRAPHS_JSON}`")
report_lines.append(f"- `{DISCLOSURES_JSON}`")
report_lines.append(f"- `{DISCLOSURES_CSV}`")
report_lines.append(f"- `{VALIDATION_RESULTS_JSON}`")
report_lines.append(f"- `{VALIDATION_REPORT}`")

VALIDATION_REPORT.write_text("\n".join(report_lines), encoding="utf-8")

print("Validation report saved:", VALIDATION_REPORT)
print("Validation results JSON saved:", VALIDATION_RESULTS_JSON)
print("\n".join(report_lines[:50]))

# ============================================================
# 11. HOW TO USE THE CATALOG LATER
# ============================================================

def filter_disclosures_for_section(
    disclosures_json_path: Path,
    core_area: str,
) -> list[dict[str, Any]]:
    """
    Use this later in your Judge agent.

    Example:
        governance_requirements = filter_disclosures_for_section(
            DISCLOSURES_JSON,
            "Governance"
        )
    """
    rows = json.loads(disclosures_json_path.read_text(encoding="utf-8"))
    return [r for r in rows if r.get("core_area") == core_area]


governance_requirements = filter_disclosures_for_section(DISCLOSURES_JSON, "Governance")
strategy_requirements = filter_disclosures_for_section(DISCLOSURES_JSON, "Strategy")

print("Governance requirements:", len(governance_requirements))
print("Strategy requirements:", len(strategy_requirements))

# Preview Governance checklist for judge prompt.
for row in governance_requirements[:5]:
    print("-", row["paragraph_ref"], "|", row["requirement_summary"])