# IFRS S1/S2 Automated Requirements KB Audit Summary — Hybrid Azure Version — Deterministic Baseline

## Extraction design
- Section paragraph ranges are not hardcoded. They are derived from each PDF’s official contents page.
- Paragraph text is reconstructed from layout-aware sorted PDF lines, with headers, footers, footnotes and body headings removed before paragraph assembly.
- Appendix guidance is mapped automatically using referenced body paragraphs and strong heading evidence.
- Definition and transition appendices are excluded from the report-generation KB.
- Requirement rows include leaf/container flags so generation agents can prefer actionable leaf requirements.
- Final polish removes trailing PDF footnote markers and adds clean_requirement_text plus generation_bucket.
- A smaller generation-ready export keeps mandatory leaf rows only.
- The notebook includes verification cells for PDF inputs, TOC detection, paragraph reconstruction, section mapping, quality scoring, splitting, generation filtering, validation and export.

## Output counts
- Extracted paragraphs: 309
- Selected paragraphs: 278
- Requirement rows: 570
- Leaf requirement rows: 532
- Generation-ready mandatory leaf rows: 361

## Requirements by section

| standard   | report_section       |   requirements |
|:-----------|:---------------------|---------------:|
| IFRS S1    | General Requirements |            197 |
| IFRS S1    | Governance           |             11 |
| IFRS S1    | Metrics and Targets  |             34 |
| IFRS S1    | Risk Management      |             12 |
| IFRS S1    | Strategy             |             35 |
| IFRS S2    | General Requirements |              7 |
| IFRS S2    | Governance           |             11 |
| IFRS S2    | Metrics and Targets  |            169 |
| IFRS S2    | Risk Management      |             11 |
| IFRS S2    | Strategy             |             83 |

## Leaf requirements by section

| standard   | report_section       |   leaf_requirements |
|:-----------|:---------------------|--------------------:|
| IFRS S1    | General Requirements |                 192 |
| IFRS S1    | Governance           |                   9 |
| IFRS S1    | Metrics and Targets  |                  33 |
| IFRS S1    | Risk Management      |                  11 |
| IFRS S1    | Strategy             |                  34 |
| IFRS S2    | General Requirements |                   6 |
| IFRS S2    | Governance           |                   9 |
| IFRS S2    | Metrics and Targets  |                 152 |
| IFRS S2    | Risk Management      |                  10 |
| IFRS S2    | Strategy             |                  76 |

## Generation buckets

| generation_bucket        |   rows |
|:-------------------------|-------:|
| container_context        |     38 |
| must_disclose_leaf       |    361 |
| optional_relief_leaf     |     56 |
| supporting_guidance_leaf |    104 |
| supporting_objective     |     11 |

## Generation-ready mandatory leaf rows by section

| standard   | report_section       |   generation_rows |
|:-----------|:---------------------|------------------:|
| IFRS S1    | General Requirements |               107 |
| IFRS S1    | Governance           |                 7 |
| IFRS S1    | Metrics and Targets  |                28 |
| IFRS S1    | Risk Management      |                 8 |
| IFRS S1    | Strategy             |                23 |
| IFRS S2    | General Requirements |                 1 |
| IFRS S2    | Governance           |                 8 |
| IFRS S2    | Metrics and Targets  |               123 |
| IFRS S2    | Risk Management      |                 9 |
| IFRS S2    | Strategy             |                47 |

## Validation checks

| check                                                    | passed   | details                                                                                                                         |
|:---------------------------------------------------------|:---------|:--------------------------------------------------------------------------------------------------------------------------------|
| Only target report sections are present                  | True     | actual=['General Requirements', 'Governance', 'Metrics and Targets', 'Risk Management', 'Strategy']                             |
| Every requirement has paragraph traceability             | True     | {'standard': 0, 'paragraph_id': 0, 'page': 0, 'source_paragraph_text': 0}                                                       |
| Requirement IDs are unique                               | True     | duplicate_ids=0                                                                                                                 |
| No very short requirement rows                           | True     | rows=0                                                                                                                          |
| Paragraph reconstruction quality passed                  | True     | low_quality_rows=0                                                                                                              |
| Required anchor paragraphs are captured                  | True     | missing=[]                                                                                                                      |
| Semantic spot checks passed                              | True     | failed=[]                                                                                                                       |
| Banking / financed-emissions requirements are tagged     | True     | rows=42                                                                                                                         |
| Definition and transition appendices are excluded        | True     | rows=0                                                                                                                          |
| Leaf requirement rows are identified                     | True     | leaf_rows=532                                                                                                                   |
| No trailing footnote markers remain in requirement text  | True     | rows=0                                                                                                                          |
| Clean generation text is available for every requirement | True     | column_present=True                                                                                                             |
| Rows are separated into generation/context buckets       | True     | buckets=['container_context', 'must_disclose_leaf', 'optional_relief_leaf', 'supporting_guidance_leaf', 'supporting_objective'] |

## Text quality summary

- min_paragraph_quality_score: 0.8
- low_quality_paragraphs: 0
- min_requirement_quality_score: 1.0
- low_quality_leaf_requirements: 0
