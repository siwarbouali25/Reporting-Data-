# IFRS S1/S2 Requirements KB Audit Summary

Total KB rows: 308


## Section counts

| standard   | report_section       | mandatory_status                                | banking_relevance     |   count |
|:-----------|:---------------------|:------------------------------------------------|:----------------------|--------:|
| IFRS S1    | General Requirements | conditional_or_relief_with_mandatory_conditions | general               |      14 |
| IFRS S1    | General Requirements | context_or_guidance                             | banking_relevant      |       1 |
| IFRS S1    | General Requirements | context_or_guidance                             | general               |      47 |
| IFRS S1    | General Requirements | mandatory                                       | banking_relevant      |       1 |
| IFRS S1    | General Requirements | mandatory                                       | general               |      70 |
| IFRS S1    | General Requirements | objective                                       | general               |       4 |
| IFRS S1    | General Requirements | optional_or_relief                              | general               |      16 |
| IFRS S1    | Governance           | mandatory                                       | general               |       1 |
| IFRS S1    | Governance           | objective                                       | general               |       1 |
| IFRS S1    | Metrics and Targets  | mandatory                                       | general               |      14 |
| IFRS S1    | Metrics and Targets  | optional_or_relief                              | general               |       1 |
| IFRS S1    | Risk Management      | mandatory                                       | general               |       1 |
| IFRS S1    | Risk Management      | objective                                       | general               |       1 |
| IFRS S1    | Strategy             | conditional_or_relief_with_mandatory_conditions | general               |       3 |
| IFRS S1    | Strategy             | context_or_guidance                             | general               |       1 |
| IFRS S1    | Strategy             | mandatory                                       | general               |       7 |
| IFRS S1    | Strategy             | objective                                       | general               |       1 |
| IFRS S1    | Strategy             | optional_or_relief                              | general               |       3 |
| IFRS S2    | General Requirements | conditional_or_relief_with_mandatory_conditions | high_banking_specific |       1 |
| IFRS S2    | General Requirements | context_or_guidance                             | general               |       5 |
| IFRS S2    | General Requirements | mandatory                                       | general               |       3 |
| IFRS S2    | General Requirements | objective                                       | general               |       1 |
| IFRS S2    | General Requirements | optional_or_relief                              | general               |       1 |
| IFRS S2    | General Requirements | optional_or_relief                              | high_banking_specific |       1 |
| IFRS S2    | Governance           | mandatory                                       | general               |       2 |
| IFRS S2    | Governance           | objective                                       | general               |       1 |
| IFRS S2    | Metrics and Targets  | conditional_or_relief_with_mandatory_conditions | general               |       4 |
| IFRS S2    | Metrics and Targets  | conditional_or_relief_with_mandatory_conditions | high_banking_specific |       2 |
| IFRS S2    | Metrics and Targets  | context_or_guidance                             | general               |       8 |
| IFRS S2    | Metrics and Targets  | context_or_guidance                             | high_banking_specific |       1 |
| IFRS S2    | Metrics and Targets  | mandatory                                       | banking_relevant      |       1 |
| IFRS S2    | Metrics and Targets  | mandatory                                       | general               |      42 |
| IFRS S2    | Metrics and Targets  | mandatory                                       | high_banking_specific |       9 |
| IFRS S2    | Metrics and Targets  | optional_or_relief                              | general               |       1 |
| IFRS S2    | Metrics and Targets  | optional_or_relief                              | high_banking_specific |       1 |
| IFRS S2    | Risk Management      | mandatory                                       | general               |       2 |
| IFRS S2    | Risk Management      | objective                                       | general               |       1 |
| IFRS S2    | Strategy             | conditional_or_relief_with_mandatory_conditions | general               |       3 |
| IFRS S2    | Strategy             | context_or_guidance                             | general               |       4 |
| IFRS S2    | Strategy             | mandatory                                       | general               |      23 |
| IFRS S2    | Strategy             | objective                                       | general               |       1 |
| IFRS S2    | Strategy             | optional_or_relief                              | general               |       3 |


## Validation checks

| check                                                    | passed   | details                                                                                               |
|:---------------------------------------------------------|:---------|:------------------------------------------------------------------------------------------------------|
| No empty paragraph text                                  | True     | empty_count=0                                                                                         |
| Unique requirement_id                                    | True     | duplicate_count=0                                                                                     |
| Only target report sections                              | True     | sections=['General Requirements', 'Governance', 'Metrics and Targets', 'Risk Management', 'Strategy'] |
| All rows have source pages                               | True     |                                                                                                       |
| Expected anchor paragraphs extracted                     | True     | all expected anchors present                                                                          |
| Expected anchor paragraphs included in KB                | True     | all expected anchors included                                                                         |
| Banking-specific financed-emissions requirements present | True     | high_banking_specific_count=15                                                                        |
| Mandatory requirements detected                          | True     | mandatory_or_conditional_count=203                                                                    |


## Banking-specific paragraphs

| paragraph_ref   | source_pages   | topic                                                                                                       | mandatory_status                                | requirement_label                                                                                                                                                                                                                                                                           |
|:----------------|:---------------|:------------------------------------------------------------------------------------------------------------|:------------------------------------------------|:--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| IFRS S1 86      | 23-25          | Sources of guidance, location, timing, comparative information, compliance, judgements, uncertainty, errors | mandatory                                       | If an entity identifies a material error in its prior period sustainability-related financial disclosures, it shall apply paragraphs B55–B59.                                                                                                                                               |
| IFRS S1 B14     | 29             | Materiality, aggregation, law/regulation, commercially sensitive information                                | context_or_guidance                             | The decisions of primary users relate to providing resources to the entity and involve decisions about:                                                                                                                                                                                     |
| IFRS S2 29      | 15-17          | Climate-related metrics and targets                                                                         | mandatory                                       | An entity shall disclose information relevant to the cross-industry metric categories of:                                                                                                                                                                                                   |
| IFRS S2 29A     | 17             | Climate-related metrics and targets                                                                         | optional_or_relief                              | In preparing disclosures to meet the requirement in paragraph 29(a)(i)(3), an entity is permitted to limit what it includes in its measure of Scope 3 Category 15 greenhouse gas emissions to only its financed emissions.                                                                  |
| IFRS S2 29C     | 17             | Climate-related metrics and targets                                                                         | mandatory                                       | If an entity has included Category 15 greenhouse gas emissions in its measure of Scope 3 greenhouse gas emissions disclosed in accordance with paragraph 29(a)(i)(3), the entity shall disclose the total Category 15 greenhouse gas emissions and the subtotal of financed emissions in... |
| IFRS S2 37      | 19-24          | Climate-related metrics and targets                                                                         | mandatory                                       | In identifying and disclosing the metrics used to set and monitor progress towards reaching a target described in paragraphs 33–34, an entity shall refer to and consider the applicability of cross-industry metrics (see paragraph 29) and industry-based metrics (see paragraph 32),...  |
| IFRS S2 B37     | 34             | Greenhouse gas emissions and Scope 3 measurement guidance                                                   | mandatory                                       | An entity that participates in one or more financial activities associated with asset management, commercial banking and insurance shall disclose additional information about the financed emissions associated with those activities as part of the entity’s disclosure of its Scope 3... |
| IFRS S2 B57     | 38             | Greenhouse gas emissions and Scope 3 measurement guidance                                                   | mandatory                                       | This Standard includes the presumption that Scope 3 greenhouse gas emissions can be estimated reliably using secondary data and industry averages.                                                                                                                                          |
| IFRS S2 B58     | 38             | Financed emissions for financial activities                                                                 | context_or_guidance                             | Entities participating in financial activities face risks and opportunities related to the greenhouse gas emissions associated with those activities.                                                                                                                                       |
| IFRS S2 B59     | 38-39          | Financed emissions for financial activities                                                                 | mandatory                                       | Paragraph 29(a)(i)(3) requires an entity to disclose its absolute gross Scope 3 greenhouse gas emissions generated during the reporting period, including upstream and downstream emissions.                                                                                                |
| IFRS S2 B60     | 39             | Financed emissions for financial activities                                                                 | mandatory                                       | An entity shall apply the requirements for disclosing greenhouse gas emissions in accordance with paragraph 29(a) when disclosing information about its financed emissions. Asset management                                                                                                |
| IFRS S2 B61     | 39             | Financed emissions for financial activities                                                                 | mandatory                                       | An entity that participates in asset management activities shall disclose: (a) its absolute gross financed emissions, disaggregated by Scope 1, Scope 2 and Scope 3 greenhouse gas emissions.                                                                                               |
| IFRS S2 B62     | 39-40          | Financed emissions for financial activities                                                                 | mandatory                                       | An entity that participates in commercial banking activities shall disclose: (a) its absolute gross financed emissions, disaggregated by Scope 1, Scope 2 and Scope 3 greenhouse gas emissions for each industry by asset class.                                                            |
| IFRS S2 B62A    | 40-41          | Financed emissions for financial activities                                                                 | conditional_or_relief_with_mandatory_conditions | When disaggregating information disclosed in accordance with paragraph B62(a)–(b) by:                                                                                                                                                                                                       |
| IFRS S2 B63     | 41             | Financed emissions for financial activities                                                                 | mandatory                                       | An entity that participates in financial activities associated with the insurance industry shall disclose:                                                                                                                                                                                  |
| IFRS S2 B63A    | 41-42          | Financed emissions for financial activities                                                                 | conditional_or_relief_with_mandatory_conditions | When disaggregating information disclosed in accordance with paragraph B63(a)–(b) by:                                                                                                                                                                                                       |
| IFRS S2 C4      | 45             | Effective date and transition                                                                               | optional_or_relief                              | In the first annual reporting period in which an entity applies this Standard, the entity is permitted to use one or both of these reliefs:                                                                                                                                                 |
| IFRS S2 C6      | 46             | Effective date and transition                                                                               | conditional_or_relief_with_mandatory_conditions | If an entity previously applied IFRS S2, in the first annual reporting period in which the entity applies Amendments to Greenhouse Gas Emissions Disclosures, the entity shall—unless it is impracticable to do so—adjust comparative information for the preceding period as follows:      |