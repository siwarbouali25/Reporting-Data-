## 3. Risk Management

This section describes how climate-related risks are identified, assessed and monitored, and how these processes are integrated into the entity’s overall enterprise risk management process.

### 3.1 Risk identification and assessment

**Purpose:** To explain how climate-related risks are identified and assessed, including key inputs and the risk-rating approach.

Climate-related risks are identified, assessed and monitored through a climate risk register.

Inputs used in the assessment process include relevant external climate indicators. For physical risk exposure inputs, the data source used is **ECB_climate_indicators**.

Scenario analysis is used to inform the identification and assessment of climate-related risks. Individual risks in the climate risk register are linked to internally defined climate scenario references, including **SCN0005**, **SCN0007**, **SCN0009** and **SCN0011**.

The climate risk register includes risk descriptions and a risk rating. For example, the register includes a risk describing chronic heat and shifting precipitation reducing yields for agricultural counterparties and weakening repayment capacity over the medium term; this risk is rated **medium**.

The climate risk register risk rating methodology is as follows: **climate_risk_register.risk_rating is derived from a 5x5 risk matrix: scores 1-2 = low, 3-6 = medium, 8-12 = high, 15-25 = critical. Specifically: likelihood_score * severity_score; critical >= 15, high >= 8, medium >= 3, low < 3.**

### 3.2 Monitoring

**Purpose:** To describe how climate-related risks are monitored and updated in the climate risk register.

Climate-related risks in the register are monitored at defined frequencies, including **monthly**, **quarterly** and **semi_annual**.

### 3.3 Integration with overall risk management

**Purpose:** To describe the extent to which climate-related risks are integrated into the entity’s overall enterprise risk management process.

Climate-related risks in the register are, in most cases, integrated into the entity’s overall enterprise risk management process (as indicated by an ERM integration flag set to **True** for multiple registered risks).

### 3.4 Changes compared with the prior reporting period

**Purpose:** To describe whether climate-related risks recorded in the climate risk register have changed compared with the prior reporting period.

The climate risk register indicates that some risks have **changed since the prior period** (changed_since_prior_period = **True** for selected risks), while others have **not changed** (changed_since_prior_period = **False** for selected risks).

### 3.5 Value chain considerations

**Purpose:** To describe how value chain segments are considered in climate-related risk identification.

Climate-related risk identification considers value chain segments, including:

- **Operational sites and travel**: Operational sites and travel generate Scope 1-2 emissions and face physical disruption.
- **Lending to Other mining and quarrying**: Lending to Other mining and quarrying carries elevated transition risk from carbon pricing and demand shifts.

### 3.6 Risk management processes and controls

**Purpose:** To summarise how climate-related risk information is organised to support integrated risk management disclosures.

Climate-related risk identification, assessment and monitoring are presented through the climate risk register, including links to scenario analysis references and the use of external climate indicator inputs such as **ECB_climate_indicators**.