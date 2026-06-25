# IFRS S1/S2 Hybrid Azure OpenAI Review Summary


## Design

- Deterministic extraction remains the auditable baseline.

- Appendix A / defined terms remains excluded from the report-generation KB.

- Azure GPT-5.2 is a required semantic review layer; missing config or failed calls stop the notebook by default.

- Original rule-based columns are preserved as `rule_*`; hybrid-applied decisions are stored as `final_*`.

- Body paragraph section mapping from official TOC is preserved conservatively; section overrides are allowed only for appendix rows above the confidence threshold.


## Comparison summary

| azure_hybrid_required   | azure_hybrid_config_ok   | hybrid_review_mode   |   hybrid_candidate_rows |   hybrid_reviewed_rows |   deterministic_requirement_rows |   hybrid_requirement_rows |   deterministic_generation_rows |   hybrid_generation_rows |   section_changes_applied |   obligation_changes_applied |   bucket_changes_applied |   split_issues_flagged |   manual_review_rows |
|:------------------------|:-------------------------|:---------------------|------------------------:|-----------------------:|---------------------------------:|--------------------------:|--------------------------------:|-------------------------:|--------------------------:|-----------------------------:|-------------------------:|-----------------------:|---------------------:|
| True                    | True                     | smart                |                     160 |                    160 |                              570 |                       570 |                             361 |                      355 |                         0 |                            5 |                        6 |                      2 |                   26 |


## Hybrid requirements by final section

| standard   | final_report_section   |   requirements |
|:-----------|:-----------------------|---------------:|
| IFRS S1    | General Requirements   |            197 |
| IFRS S1    | Governance             |             11 |
| IFRS S1    | Metrics and Targets    |             34 |
| IFRS S1    | Risk Management        |             12 |
| IFRS S1    | Strategy               |             35 |
| IFRS S2    | General Requirements   |              7 |
| IFRS S2    | Governance             |             11 |
| IFRS S2    | Metrics and Targets    |            169 |
| IFRS S2    | Risk Management        |             11 |
| IFRS S2    | Strategy               |             83 |


## Hybrid generation-ready rows by section

| standard   | report_section       |   generation_rows |
|:-----------|:---------------------|------------------:|
| IFRS S1    | General Requirements |               104 |
| IFRS S1    | Governance           |                 7 |
| IFRS S1    | Metrics and Targets  |                28 |
| IFRS S1    | Risk Management      |                 8 |
| IFRS S1    | Strategy             |                23 |
| IFRS S2    | General Requirements |                 1 |
| IFRS S2    | Governance           |                 8 |
| IFRS S2    | Metrics and Targets  |               123 |
| IFRS S2    | Risk Management      |                 9 |
| IFRS S2    | Strategy             |                44 |


## Manual review queue

Rows flagged for manual review: 26
