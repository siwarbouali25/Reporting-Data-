# ESG Synthetic Database — Remediated (IFRS S1/S2 Gap-Closed)

This dataset applies all 12 patches and 6 new tables from the gap-remediation
spec to the medium-scale dataset. Every patch is mapped to specific IFRS S1/S2
paragraphs, and all 35 validation checks (PART D) pass.

## Banks (5 archetypes)
| Bank | Archetype | Behavior | Country |
|------|-----------|----------|---------|
| BANK01 | Large universal | Average | DE |
| BANK02 | Large universal | Average | FR |
| BANK03 | Mid-size commercial | Average | IT |
| BANK04 | Specialized green | Leader | NL |
| BANK05 | Corporate | Laggard | ES |

## Tables (26 total)

### Patched existing tables (12)
| File | Key additions | IFRS paras |
|------|---------------|------------|
| banks.csv | LEI, capital metrics (Tier1, CET1), total_loans, boundary, regime | S1 §20, §B38 |
| counterparties.csv | sovereign GDP/national emissions, SBTi flag, data_source_type, transition score; +5 sovereigns | S2 B62A |
| governance.csv | exec climate remuneration, board agenda %, mgmt committee, ERM flag; +2022/2023 rows | S2 §6, §29(g) |
| exposures.csv | pcaf_asset_class, undrawn, green_taxonomy, origination property/project value, control | S2 §29, B62 |
| investments.csv | issuer revenue/EVIC, sovereign GDP, PCAF DQS, reporting_year | S2 B61, B62 |
| collateral.csv | market_value_at_origination, building_emissions, postcode, flood_zone_class, exposure_amount | PCAF §4.4-4.5, §29(b) |
| physical_risk_exposures.csv | hazard_category, exposure_amount, high_risk_flag, financial_impact, portfolio_pct, nace | S2 §29(b) |
| utility_invoices.csv | rec_volume, grid EF, scope2 location/market, scope1_gas | S2 §29(a) |
| vehicles.csv | annual_km 2022/2023, scope1_tco2e_2024, emission_factor_source | S2 §29(a), S1 §70 |
| targets.csv | gross/net, GHG coverage, validation, SDA flag, interim milestones, planned credits | S2 §33-36 |
| carbon_credits.csv | credit_type, mechanism, permanence, additionality, retirement, target link; +2022/23 | S2 §36(e), B70 |
| climate_scenarios.csv | Paris flag, revenue-at-risk, carbon price/GDP/renewable/tech assumptions | S2 §22(b) |

### New tables (6)
| File | Grain | Rows | IFRS paras |
|------|-------|------|------------|
| internal_carbon_price.csv | bank × year | 15 | S2 §29(f) |
| rec_registry.csv | REC batch / PPA | 48 | S2 §29(a)(v), B30-31 |
| board_minutes_extract.csv | meeting | 154 | S2 §6(a) |
| climate_risk_register.csv | risk × bank × year | 80 | S2 §25(a) |
| financial_summary.csv | bank × year | 15 | S1 §21-24, S2 §15-21 |
| value_chain_map.csv | value-chain node × bank | 80 | S2 §13, S1 §32 |

### Passthrough (unchanged)
counterparty_emissions, facilities, travel_records, employees + Phase 1-2 catalog
(disclosures, data_requirements, source_systems, disclosure_data_map)

## Notes on synthetic-data adaptations
- **Sovereigns injected**: the medium dataset had no sovereign counterparties, so one
  per bank's home country was added (NACE O84) with IMF PPP-GDP and IEA national
  emissions, enabling the PCAF sovereign-bond attribution path.
- **Physical risk scores** are on a 1-5 scale here; flood-zone thresholds and the
  high-risk (≥7 on 0-10) test were mapped by doubling the stored score.
- **LEI codes** use the ISO 17442 mod-97-10 check-digit algorithm and are unique.
- **carbon_intensity_tco2e_per_meur_lending** in financial_summary is intentionally
  left blank — it is computed in Stage 5 once financed emissions are aggregated.

## Validation
All 35 checks pass across: referential integrity, PCAF routing, accounting
identities, §29 cross-industry metric computability, §70 comparatives, target/
scenario consistency, risk-rating derivation, and weekday board meetings.
