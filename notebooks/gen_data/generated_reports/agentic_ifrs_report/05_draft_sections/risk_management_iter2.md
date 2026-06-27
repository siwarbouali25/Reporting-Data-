## 3. Risk Management

Climate-related risks and opportunities are managed within the entity’s overall enterprise risk management (ERM) framework. Climate-related items are captured and maintained in a climate risk register and, where applicable, are integrated into ERM.

### 3.1 Risk identification and assessment

Climate-related risks are identified and assessed through the climate risk register.

Key elements of the process include:

- **Register-based identification**: climate-related risks are recorded in the climate risk register.
- **Inputs and data sources**: physical risk exposure inputs use external climate indicators sourced from **ECB_climate_indicators**.
- **Use of scenario analysis**: scenario analysis is used to inform the identification and assessment of climate-related risks. Individual risks in the climate risk register are linked to internal scenario references, including **SCN0005**, **SCN0007**, **SCN0009** and **SCN0011**.
- **Risk description and rating**: the register includes risk descriptions and a risk rating. For example, the register includes a risk describing: “Chronic heat and shifting precipitation reduce yields for agricultural counterparties, weakening repayment capacity over the medium term.” This risk is rated **medium**.

**Risk rating methodology**

climate_risk_register.risk_rating is derived from a 5x5 risk matrix: scores 1-2 = low, 3-6 = medium, 8-12 = high, 15-25 = critical. Specifically: likelihood_score * severity_score; critical >= 15, high >= 8, medium >= 3, low < 3.

Connectivity: the outputs of this identification and assessment process inform the entity’s climate-related disclosures across Strategy and Metrics and Targets.

### 3.2 Prioritisation within ERM

Climate-related risks are prioritised using the climate risk register risk rating methodology and are considered alongside other risk types within ERM.

- **Comparative prioritisation**: climate-related risks are prioritised relative to other risks through their risk ratings, enabling comparative ranking and escalation within the ERM process.
- **ERM integration indicator**: the climate risk register includes an ERM integration flag (erm_integrated_flag). Multiple registered climate-related risks have erm_integrated_flag set to **True**.

Connectivity: prioritised climate-related risks are used to support risk-focused decision-making and related disclosures.

### 3.3 Monitoring

Climate-related risks recorded in the climate risk register are monitored at defined frequencies.

- **Monitoring frequencies used**: **monthly**, **quarterly** and **semi_annual**.
- **Register maintenance**: monitoring outcomes are reflected through updates to the climate risk register.

Connectivity: monitoring results support updates to risk-related metrics and management actions.

### 3.4 Integration with overall risk management

Climate-related risks are integrated into the entity’s overall ERM process where the climate risk register indicates integration.

- Multiple registered risks have an ERM integration flag set to **True**.

Connectivity: integration into ERM supports consistency between risk management disclosures and governance and strategy disclosures.

### 3.5 Changes compared with the prior reporting period

The climate risk register indicates that some risks have changed since the prior reporting period (changed_since_prior_period = **True** for selected risks), while others have not changed (changed_since_prior_period = **False** for selected risks).

Connectivity: changes in the climate risk register inform updates to related narrative disclosures.

### 3.6 Value chain considerations

Climate-related risk considerations are documented for value chain segments, including:

- **Operational sites and travel**: “Operational sites and travel generate Scope 1-2 emissions and face physical disruption.”
- **Lending to Other mining and quarrying**: “Lending to Other mining and quarrying carries elevated transition risk from carbon pricing and demand shifts.”

Connectivity: value chain considerations support the identification of climate-related risks and opportunities.

### 3.7 Climate-related opportunities

Climate-related opportunities are identified, assessed, prioritised and monitored through the same register-based approach used for climate-related risks.

- Opportunities are captured and maintained through the climate risk register processes described in sections 3.1–3.4, including the use of scenario analysis references (for example, **SCN0005**, **SCN0007**, **SCN0009** and **SCN0011**) and defined monitoring frequencies (**monthly**, **quarterly** and **semi_annual**).

Connectivity: prioritised climate-related opportunities inform related disclosures across Strategy and Metrics and Targets.