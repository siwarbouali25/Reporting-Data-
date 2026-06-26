# ============================================================
# FINAL STYLE SYSTEM ORGANIZATION FOR GENERATION PIPELINE
# Creates:
# - authoring/  -> used by section generation and restyle agents
# - judging/    -> used by style judge
# - rendering/  -> used only by PDF assembly stage
# ============================================================

import json
import shutil
from pathlib import Path


# ------------------------------------------------------------
# 1. Final organized folders
# ------------------------------------------------------------

AUTHORING_DIR = STYLE_OUTPUT_DIR / "authoring"
JUDGING_DIR = STYLE_OUTPUT_DIR / "judging"
RENDERING_DIR = STYLE_OUTPUT_DIR / "rendering"

AUTHORING_SECTION_STYLE_DIR = AUTHORING_DIR / "section_style_guides"
AUTHORING_SECTION_BLUEPRINT_DIR = AUTHORING_DIR / "section_blueprints"
AUTHORING_LANGUAGE_RULES_DIR = AUTHORING_DIR / "language_rules"
AUTHORING_TABLE_PATTERNS_DIR = AUTHORING_DIR / "table_patterns"

for folder in [
    AUTHORING_DIR,
    JUDGING_DIR,
    RENDERING_DIR,
    AUTHORING_SECTION_STYLE_DIR,
    AUTHORING_SECTION_BLUEPRINT_DIR,
    AUTHORING_LANGUAGE_RULES_DIR,
    AUTHORING_TABLE_PATTERNS_DIR,
]:
    folder.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------
# 2. Copy authoring artifacts
# ------------------------------------------------------------

def copy_if_exists(src: Path, dst: Path):
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print("Copied:", src, "->", dst)
    else:
        print("Missing, skipped:", src)


copy_if_exists(
    STYLE_OUTPUT_DIR / "global_style_guide.json",
    AUTHORING_DIR / "global_style_guide.json"
)

copy_if_exists(
    TABLE_PATTERN_DIR / "table_patterns.json",
    AUTHORING_TABLE_PATTERNS_DIR / "table_patterns.json"
)

copy_if_exists(
    LANGUAGE_RULES_DIR / "no_copying_rules.md",
    AUTHORING_LANGUAGE_RULES_DIR / "no_copying_rules.md"
)

for path in SECTION_STYLE_DIR.glob("*.json"):
    copy_if_exists(path, AUTHORING_SECTION_STYLE_DIR / path.name)

for path in SECTION_BLUEPRINT_DIR.glob("*.json"):
    copy_if_exists(path, AUTHORING_SECTION_BLUEPRINT_DIR / path.name)


# ------------------------------------------------------------
# 3. Copy rendering artifact
# layout_style_guide.json must NOT be injected into drafting prompts.
# ------------------------------------------------------------

copy_if_exists(
    STYLE_OUTPUT_DIR / "layout_style_guide.json",
    RENDERING_DIR / "layout_style_guide.json"
)


# ------------------------------------------------------------
# 4. Create numeric style compliance rubric for stable judging
# ------------------------------------------------------------

style_compliance_rubric = {
    "purpose": "Stable numeric rubric for judging whether generated IFRS S1/S2 report sections follow the approved authoring style.",
    "scoring_scale": {
        "5": "Excellent / fully aligned",
        "4": "Good / minor issues",
        "3": "Acceptable but needs revision",
        "2": "Weak / major revision required",
        "1": "Fail / not suitable for report generation"
    },
    "checks": {
        "voice_consistency": {
            "score_5": "Consistent report voice throughout. First-person plural used only for target-company actions; passive or third-person used for externally defined IFRS requirements.",
            "score_3": "Mostly consistent voice with occasional shifts between 'we', 'the Group', and passive constructions.",
            "score_1": "Frequent uncontrolled switching of voice that makes the section inconsistent."
        },
        "paragraph_length": {
            "ideal": "2-5 sentences per paragraph",
            "warning": "6-7 sentences",
            "fail": "8 or more sentences",
            "score_5": "Most paragraphs are 2-5 sentences and single-idea.",
            "score_3": "Several paragraphs are long or multi-topic.",
            "score_1": "Paragraphs are dense, long, and difficult to scan."
        },
        "sentence_length": {
            "ideal": "18-34 words",
            "warning": "35-45 words",
            "fail": "46 or more words",
            "score_5": "Sentences are mostly short-to-medium and clear.",
            "score_3": "Several sentences are long but still understandable.",
            "score_1": "Many sentences are overloaded or unclear."
        },
        "bullet_and_list_usage": {
            "score_5": "Bullets are used for lists of three or more items, process steps, principles, criteria, and controls.",
            "score_3": "Some lists are placed inside long paragraphs.",
            "score_1": "Lists are hard to read or inconsistently formatted."
        },
        "table_and_figure_captioning": {
            "score_5": "Every table and figure has a number, clear caption, and is referenced in nearby narrative.",
            "score_3": "Most tables/figures have captions, but some are weak or not referenced.",
            "score_1": "Tables/figures are uncaptained or disconnected from the text."
        },
        "ifrs_style_alignment": {
            "score_5": "Uses standards-oriented verbs and distinguishes current facts, estimates, judgements, and forward-looking intentions.",
            "score_3": "Mostly IFRS-aligned but some vague or generic language remains.",
            "score_1": "Reads like a generic ESG marketing text rather than IFRS S1/S2 disclosure."
        },
        "missing_data_protocol": {
            "score_5": "Missing data is clearly labelled with what is missing, why, interim approach, limitation, and improvement direction.",
            "score_3": "Missing data is mentioned but lacks one or more required elements.",
            "score_1": "Missing data is hidden, ignored, or replaced by unsupported assumptions."
        },
        "no_reference_content": {
            "score_5": "No reference-company names, facts, claims, numbers, committees, images, tools, vendors, or copied phrasing.",
            "score_3": "No obvious copying, but some phrasing or structure feels too close.",
            "score_1": "Reference-company content or near-copying is present."
        },
        "evidence_discipline": {
            "score_5": "Every material claim is supported by target payload data, IFRS requirement, or an explicit data-gap statement.",
            "score_3": "Most claims are supported, but some broad claims need evidence.",
            "score_1": "Unsupported claims or invented maturity statements are present."
        }
    },
    "approval_thresholds": {
        "approve": {
            "minimum_average_score": 4.2,
            "required": [
                "no_reference_content score must be 5",
                "evidence_discipline score must be at least 4",
                "missing_data_protocol score must be at least 4"
            ]
        },
        "revise": {
            "average_score_range": "3.0-4.19"
        },
        "reject": {
            "average_score_below": 3.0
        }
    }
}

style_rubric_path = JUDGING_DIR / "style_compliance_rubric.json"

with open(style_rubric_path, "w", encoding="utf-8") as f:
    json.dump(style_compliance_rubric, f, ensure_ascii=False, indent=2)

print("Saved style compliance rubric:", style_rubric_path)


# ------------------------------------------------------------
# 5. Final usage manifest
# ------------------------------------------------------------

style_usage_manifest = {
    "authoring_stage": {
        "used_by": [
            "section generation agents",
            "restyle agents"
        ],
        "files": [
            "authoring/global_style_guide.json",
            "authoring/section_style_guides/<section>_style.json",
            "authoring/section_blueprints/<section>_blueprint.json",
            "authoring/table_patterns/table_patterns.json",
            "authoring/language_rules/no_copying_rules.md"
        ],
        "do_not_include": [
            "rendering/layout_style_guide.json",
            "reference report text",
            "raw style_chunk_notes.json"
        ]
    },
    "judging_stage": {
        "used_by": [
            "style compliance judge"
        ],
        "files": [
            "judging/style_compliance_rubric.json",
            "authoring/global_style_guide.json",
            "authoring/section_style_guides/<section>_style.json",
            "authoring/language_rules/no_copying_rules.md"
        ]
    },
    "rendering_stage": {
        "used_by": [
            "PDF assembly script",
            "report formatter"
        ],
        "files": [
            "rendering/layout_style_guide.json",
            "approved section markdown",
            "approved tables and figures",
            "brand/theme settings"
        ],
        "important_rule": "layout_style_guide.json is not passed to drafting agents."
    }
}

manifest_path = STYLE_OUTPUT_DIR / "style_usage_manifest.json"

with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump(style_usage_manifest, f, ensure_ascii=False, indent=2)

print("Saved style usage manifest:", manifest_path)