# Style Extraction Audit Summary

## Source

- Reference report: `C:\Users\BV426BP\Documents\IFRS Data\Reporting-Data-\notebooks\gen_data\style\emirates_nbd_group_2024_ifrs_s1_s2.pdf`
- Purpose: extract reusable style, structure, layout and formatting patterns only.
- The reference report must not be used as a factual source during report generation.
- The final report target is PDF, so a dedicated PDF layout style guide is created.

## Section ranges used

- General Requirements: pages 4–7
- Governance: pages 8–18
- Strategy: pages 19–46
- Risk Management: pages 47–54
- Metrics and Targets: pages 55–63

## Artifacts created

- `C:\Users\BV426BP\Documents\IFRS Data\Reporting-Data-\notebooks\gen_data\style\style_system\global_style_guide.json`
- `C:\Users\BV426BP\Documents\IFRS Data\Reporting-Data-\notebooks\gen_data\style\style_system\layout_style_guide.json`
- `C:\Users\BV426BP\Documents\IFRS Data\Reporting-Data-\notebooks\gen_data\style\style_system\table_patterns\table_patterns.json`
- `C:\Users\BV426BP\Documents\IFRS Data\Reporting-Data-\notebooks\gen_data\style\style_system\language_rules\no_copying_rules.md`
- `C:\Users\BV426BP\Documents\IFRS Data\Reporting-Data-\notebooks\gen_data\style\style_system\section_style_guides`
- `C:\Users\BV426BP\Documents\IFRS Data\Reporting-Data-\notebooks\gen_data\style\style_system\section_blueprints`
- `C:\Users\BV426BP\Documents\IFRS Data\Reporting-Data-\notebooks\gen_data\style\style_system\style_artifact_validation.csv`

## Validation

- Files checked: 15
- Files with possible copying/content leakage risk: 0

## Usage rule

Generation agents should receive only the extracted style artifacts, not the original reference report text.

## Required inputs for generation agents

Each section generation agent should receive:

1. Section-specific IFRS requirements.
2. Section-specific company payload.
3. `global_style_guide.json`.
4. `layout_style_guide.json`.
5. Relevant `section_style_guides/<section>_style.json`.
6. Relevant `section_blueprints/<section>_blueprint.json`.
7. `table_patterns/table_patterns.json`.
8. `language_rules/no_copying_rules.md`.
