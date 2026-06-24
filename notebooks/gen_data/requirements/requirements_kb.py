"""
Auto-generated IFRS S1/S2 + Commercial Banks requirements knowledge base.
Do not edit manually. Regenerate from the extraction notebook.

This module loads its data from requirements_kb_data.json.

Important:
- source_authority="core_standard" = IFRS S1/S2 core requirements
- source_authority="industry_guidance" = Commercial Banks industry-based guidance
"""

from __future__ import annotations

import json
from pathlib import Path


_DATA_PATH = Path(__file__).with_name("requirements_kb_data.json")

with open(_DATA_PATH, "r", encoding="utf-8") as f:
    _DATA = json.load(f)

REQUIREMENTS_BY_PRIMARY_SECTION = _DATA["by_primary_section"]
REQUIREMENTS_BY_REPORT_SECTION = _DATA["by_report_section"]

# Backward-compatible alias
REQUIREMENTS = REQUIREMENTS_BY_PRIMARY_SECTION


def _sort(reqs: list[dict]) -> list[dict]:
    section_order = {
        "general_requirements": 0,
        "governance": 1,
        "strategy": 2,
        "risk_management": 3,
        "metrics_targets": 4,
        "industry_metrics": 5,
        "other": 6,
    }

    authority_order = {
        "core_standard": 0,
        "industry_guidance": 1,
    }

    obligation_order = {
        "shall": 0,
        "should": 1,
        "may": 2,
    }

    return sorted(
        reqs,
        key=lambda r: (
            authority_order.get(r.get("source_authority", "core_standard"), 99),
            obligation_order.get(r.get("obligation_type", "shall"), 99),
            r.get("standard", ""),
            section_order.get(r.get("section", "other"), 99),
            r.get("page_start", 999999),
            str(r.get("paragraph", "")),
        )
    )


def _filter(
    reqs: list[dict],
    standard: str | None = None,
    source_authority: str | None = None,
    mandatory_only: bool = False,
    banks_only: bool = False,
    applicability: str | None = None,
) -> list[dict]:
    if standard:
        reqs = [r for r in reqs if r.get("standard") == standard]

    if source_authority:
        reqs = [r for r in reqs if r.get("source_authority") == source_authority]

    if mandatory_only:
        reqs = [r for r in reqs if r.get("obligation_type") == "shall"]

    if banks_only:
        reqs = [r for r in reqs if r.get("applies_to_banks") is True]

    if applicability:
        reqs = [r for r in reqs if r.get("applicability") == applicability]

    return _sort(reqs)


def get_requirements(
    section: str,
    standard: str | None = None,
    source_authority: str | None = None,
    mandatory_only: bool = False,
    banks_only: bool = False,
    applicability: str | None = None,
) -> list[dict]:
    """Return requirements by primary extracted section."""
    reqs = REQUIREMENTS_BY_PRIMARY_SECTION.get(section, [])
    return _filter(reqs, standard, source_authority, mandatory_only, banks_only, applicability)


def get_requirements_for_report_section(
    report_section: str,
    standard: str | None = None,
    source_authority: str | None = None,
    mandatory_only: bool = False,
    banks_only: bool = False,
    applicability: str | None = None,
    include_guidance: bool = True,
) -> list[dict]:
    """Return requirements/guidance that support a generated report section."""
    reqs = REQUIREMENTS_BY_REPORT_SECTION.get(report_section, [])

    if not include_guidance:
        reqs = [r for r in reqs if r.get("source_authority") == "core_standard"]

    return _filter(reqs, standard, source_authority, mandatory_only, banks_only, applicability)


def get_core_requirements(report_section: str, mandatory_only: bool = True) -> list[dict]:
    """Return IFRS S1/S2 core standard requirements for a generated report section."""
    return get_requirements_for_report_section(
        report_section=report_section,
        source_authority="core_standard",
        mandatory_only=mandatory_only,
        include_guidance=False,
    )


def get_bank_guidance(report_section: str | None = None) -> list[dict]:
    """Return Commercial Banks industry guidance. If report_section is None, return all bank guidance."""
    if report_section is None:
        all_reqs = []
        for reqs in REQUIREMENTS_BY_REPORT_SECTION.values():
            all_reqs.extend(reqs)

        seen = set()
        out = []
        for r in all_reqs:
            key = (r.get("standard"), r.get("paragraph"), r.get("requirement_text", "")[:200])
            if key not in seen and r.get("standard") == "S2_IBG_CB":
                seen.add(key)
                out.append(r)

        return _sort(out)

    return get_requirements_for_report_section(
        report_section=report_section,
        standard="S2_IBG_CB",
        banks_only=True,
        include_guidance=True,
    )


def list_primary_sections() -> list[str]:
    return sorted(REQUIREMENTS_BY_PRIMARY_SECTION.keys())


def list_report_sections() -> list[str]:
    return sorted(REQUIREMENTS_BY_REPORT_SECTION.keys())


def count_requirements() -> int:
    all_reqs = []
    for reqs in REQUIREMENTS_BY_PRIMARY_SECTION.values():
        all_reqs.extend(reqs)
    return len(all_reqs)
