"""
prepare_entity_scenario_analysis.py
===================================

Purpose:
    Convert sector-level scenario_model_out_raw into entity-level scenario evidence.

Why:
    scenario_model_out_raw may not have entity_id.
    This script links entities to scenario outputs through loan_book sector exposure.

Inputs:
    Data/entity_master_raw.csv
    Data/loan_book_raw.csv
    Data/scenario_model_out_raw.csv

Output:
    Data/prepared_entity_scenario_analysis.csv
"""

import csv
import json
from pathlib import Path

import numpy as np
import pandas as pd


DATA_DIR = Path("Data")

ENTITY_MASTER_PATH = DATA_DIR / "entity_master_raw.csv"
LOAN_BOOK_PATH = DATA_DIR / "loan_book_raw.csv"
SCENARIO_PATH = DATA_DIR / "scenario_model_out_raw.csv"

OUTPUT_PATH = DATA_DIR / "prepared_entity_scenario_analysis.csv"


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
        .str.replace(" ", "_", regex=False)
    )
    return df


def normalize_bool_series(s: pd.Series) -> pd.Series:
    return (
        s.astype(str)
        .str.strip()
        .str.lower()
        .map({
            "true": True,
            "false": False,
            "1": True,
            "0": False,
            "yes": True,
            "no": False,
            "y": True,
            "n": False,
        })
    )


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    return normalize_columns(pd.read_csv(path))


def require_columns(df: pd.DataFrame, table_name: str, required_cols: list[str]) -> None:
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise KeyError(f"{table_name} is missing required columns: {missing}")


def add_reporting_year_from_date(df: pd.DataFrame, table_name: str) -> pd.DataFrame:
    df = df.copy()

    if "reporting_year" not in df.columns:
        if "reporting_date" in df.columns:
            df["reporting_date"] = pd.to_datetime(df["reporting_date"], errors="coerce")
            df["reporting_year"] = df["reporting_date"].dt.year
        else:
            raise KeyError(
                f"{table_name} must contain either reporting_year or reporting_date"
            )

    return df


def safe_json_list(values) -> str:
    clean = [
        str(v)
        for v in values
        if pd.notna(v) and str(v).strip() != ""
    ]
    return json.dumps(sorted(set(clean)), ensure_ascii=False)


def main():
    print("=" * 75)
    print("Preparing entity-level scenario analysis")
    print("=" * 75)

    entity_master = load_csv(ENTITY_MASTER_PATH)
    loan_book = load_csv(LOAN_BOOK_PATH)
    scenario = load_csv(SCENARIO_PATH)

    loan_book = add_reporting_year_from_date(loan_book, "loan_book_raw.csv")
    scenario = add_reporting_year_from_date(scenario, "scenario_model_out_raw.csv")

    require_columns(
        entity_master,
        "entity_master_raw.csv",
        ["entity_id", "legal_name", "country_code", "in_scope_esg_flag"],
    )

    require_columns(
        loan_book,
        "loan_book_raw.csv",
        [
            "entity_id",
            "reporting_year",
            "nace_code",
            "outstanding_balance_eur",
        ],
    )

    require_columns(
        scenario,
        "scenario_model_out_raw.csv",
        [
            "scenario_id",
            "scenario_family",
            "temperature_pathway_c",
            "time_horizon_year",
            "nace_code",
            "reporting_year",
        ],
    )

    if "impact_eur" not in scenario.columns and "impact_eur_m" not in scenario.columns:
        raise KeyError(
            "scenario_model_out_raw.csv must contain impact_eur or impact_eur_m"
        )

    # -------------------------------------------------
    # Filter in-scope entities
    # -------------------------------------------------
    in_scope = normalize_bool_series(entity_master["in_scope_esg_flag"]).fillna(False)
    entities = entity_master[in_scope].copy()

    print(f"In-scope entities: {len(entities)}")

    loan_book = loan_book[
        loan_book["entity_id"].astype(str).isin(entities["entity_id"].astype(str))
    ].copy()

    loan_book["outstanding_balance_eur"] = pd.to_numeric(
        loan_book["outstanding_balance_eur"], errors="coerce"
    ).fillna(0)

    # -------------------------------------------------
    # Aggregate loan book exposure by entity/year/NACE
    # -------------------------------------------------
    exposure_by_sector = (
        loan_book
        .groupby(["entity_id", "reporting_year", "nace_code"], dropna=False)
        .agg(
            sector_exposure_eur=("outstanding_balance_eur", "sum"),
            loan_count=("outstanding_balance_eur", "size"),
        )
        .reset_index()
    )

    total_exposure = (
        loan_book
        .groupby(["entity_id", "reporting_year"])
        .agg(total_entity_exposure_eur=("outstanding_balance_eur", "sum"))
        .reset_index()
    )

    exposure_by_sector = exposure_by_sector.merge(
        total_exposure,
        on=["entity_id", "reporting_year"],
        how="left",
    )

    exposure_by_sector["sector_exposure_share_pct"] = np.where(
        exposure_by_sector["total_entity_exposure_eur"] > 0,
        exposure_by_sector["sector_exposure_eur"]
        / exposure_by_sector["total_entity_exposure_eur"]
        * 100,
        0,
    )

    # -------------------------------------------------
    # Prepare scenario impact
    # -------------------------------------------------
    scenario = scenario.copy()

    if "impact_eur" not in scenario.columns and "impact_eur_m" in scenario.columns:
        scenario["impact_eur"] = pd.to_numeric(
            scenario["impact_eur_m"], errors="coerce"
        ).fillna(0) * 1_000_000

    if "impact_eur_m" not in scenario.columns and "impact_eur" in scenario.columns:
        scenario["impact_eur_m"] = pd.to_numeric(
            scenario["impact_eur"], errors="coerce"
        ).fillna(0) / 1_000_000

    scenario["impact_eur"] = pd.to_numeric(
        scenario["impact_eur"], errors="coerce"
    ).fillna(0)

    scenario["sector_exposure_eur"] = pd.to_numeric(
        scenario.get("sector_exposure_eur", np.nan),
        errors="coerce",
    )

    # If scenario already has sector exposure, use it to convert impact into impact rate.
    # If not, fallback to a small synthetic impact rate derived from impact magnitude.
    scenario["scenario_sector_impact_rate"] = np.where(
        scenario["sector_exposure_eur"].notna() & (scenario["sector_exposure_eur"] > 0),
        scenario["impact_eur"] / scenario["sector_exposure_eur"],
        np.nan,
    )

    if scenario["scenario_sector_impact_rate"].isna().all():
        scenario["scenario_sector_impact_rate"] = 0.0
    else:
        median_rate = scenario["scenario_sector_impact_rate"].median(skipna=True)
        scenario["scenario_sector_impact_rate"] = scenario[
            "scenario_sector_impact_rate"
        ].fillna(median_rate)

    scenario["scenario_sector_impact_rate"] = scenario[
        "scenario_sector_impact_rate"
    ].clip(lower=0, upper=1)

    scenario_cols = [
        c for c in [
            "scenario_id",
            "scenario_family",
            "scenario_description",
            "temperature_pathway_c",
            "time_horizon_year",
            "metric_name",
            "metric_category",
            "metric_description",
            "nace_code",
            "nace_description",
            "base_transition_risk_factor",
            "base_physical_risk_factor",
            "scenario_transition_multiplier",
            "scenario_physical_multiplier",
            "metric_multiplier",
            "scenario_sector_impact_rate",
            "reporting_year",
            "data_source",
        ]
        if c in scenario.columns
    ]

    scenario_small = scenario[scenario_cols].copy()

    # -------------------------------------------------
    # Link entity exposures with scenario outputs
    # -------------------------------------------------
    joined = exposure_by_sector.merge(
        scenario_small,
        on=["nace_code", "reporting_year"],
        how="inner",
    )

    entity_info = entities[
        ["entity_id", "legal_name", "country_code"]
        + (["regulatory_regime"] if "regulatory_regime" in entities.columns else [])
    ].copy()

    joined = joined.merge(
        entity_info,
        on="entity_id",
        how="left",
    )

    joined["entity_scenario_impact_eur"] = (
        joined["sector_exposure_eur"] * joined["scenario_sector_impact_rate"]
    )

    joined["entity_scenario_impact_eur_m"] = (
        joined["entity_scenario_impact_eur"] / 1_000_000
    )

    joined["impact_pct_of_entity_exposure"] = np.where(
        joined["total_entity_exposure_eur"] > 0,
        joined["entity_scenario_impact_eur"]
        / joined["total_entity_exposure_eur"]
        * 100,
        0,
    )

    # -------------------------------------------------
    # Aggregate by entity/year/scenario/horizon
    # -------------------------------------------------
    group_cols = [
        "entity_id",
        "legal_name",
        "country_code",
        "reporting_year",
        "scenario_id",
        "scenario_family",
        "temperature_pathway_c",
        "time_horizon_year",
    ]

    if "scenario_description" in joined.columns:
        group_cols.append("scenario_description")

    if "regulatory_regime" in joined.columns:
        group_cols.append("regulatory_regime")

    prepared = (
        joined
        .groupby(group_cols, dropna=False)
        .agg(
            total_entity_exposure_eur=("total_entity_exposure_eur", "max"),
            covered_sector_exposure_eur=("sector_exposure_eur", "sum"),
            total_financial_impact_eur=("entity_scenario_impact_eur", "sum"),
            total_financial_impact_eur_m=("entity_scenario_impact_eur_m", "sum"),
            max_sector_impact_pct=("impact_pct_of_entity_exposure", "max"),
            average_sector_impact_pct=("impact_pct_of_entity_exposure", "mean"),
            sector_count=("nace_code", "nunique"),
            affected_nace_codes=("nace_code", safe_json_list),
            affected_metric_names=("metric_name", safe_json_list)
            if "metric_name" in joined.columns
            else ("nace_code", safe_json_list),
        )
        .reset_index()
    )

    prepared["coverage_pct_of_entity_book"] = np.where(
        prepared["total_entity_exposure_eur"] > 0,
        prepared["covered_sector_exposure_eur"]
        / prepared["total_entity_exposure_eur"]
        * 100,
        0,
    )

    # Simple score, not final regulatory calculation
    prepared["business_model_impact_score"] = (
        prepared["total_financial_impact_eur_m"]
        .rank(pct=True)
        .mul(10)
        .round(2)
        .clip(1, 10)
    )

    prepared["residual_risk_score"] = (
        prepared["business_model_impact_score"] * 0.65
    ).round(2).clip(1, 10)

    prepared["revenue_at_risk_pct"] = (
        prepared["total_financial_impact_eur"]
        / prepared["total_entity_exposure_eur"].replace(0, np.nan)
        * 100
    ).fillna(0).round(4)

    prepared["capital_adequacy_impact_pct"] = (
        prepared["revenue_at_risk_pct"] * 0.25
    ).round(4)

    prepared["prepared_scenario_record_id"] = (
        "PESA-"
        + prepared["entity_id"].astype(str)
        + "-"
        + prepared["reporting_year"].astype(str)
        + "-"
        + prepared["scenario_id"].astype(str)
        + "-"
        + prepared["time_horizon_year"].astype(str)
    )

    prepared["data_source"] = (
        "Derived: loan_book_raw + scenario_model_out_raw + entity_master_raw"
    )
    prepared["created_from"] = "prepare_entity_scenario_analysis.py"

    first_cols = [
        "prepared_scenario_record_id",
        "entity_id",
        "legal_name",
        "country_code",
        "reporting_year",
        "scenario_id",
        "scenario_family",
        "temperature_pathway_c",
        "time_horizon_year",
    ]

    remaining_cols = [c for c in prepared.columns if c not in first_cols]
    prepared = prepared[first_cols + remaining_cols]

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    prepared.to_csv(
        OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
        quoting=csv.QUOTE_ALL,
        lineterminator="\n",
    )

    print(f"Generated: {OUTPUT_PATH}")
    print(f"Shape: {prepared.shape}")
    print(f"Entities covered: {prepared['entity_id'].nunique()}")
    print(f"Scenarios covered: {prepared['scenario_id'].nunique()}")
    print(f"Years covered: {sorted(prepared['reporting_year'].dropna().unique().tolist())}")

    print("\nValidation:")
    print(f"Unique record id: {prepared['prepared_scenario_record_id'].is_unique}")
    print(f"Missing entity_id: {prepared['entity_id'].isna().sum()}")
    print(f"Missing scenario_id: {prepared['scenario_id'].isna().sum()}")
    print(f"Negative impacts: {(prepared['total_financial_impact_eur'] < 0).sum()}")

    return prepared


if __name__ == "__main__":
    main()