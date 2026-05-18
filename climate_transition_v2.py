"""
climate_transition_plan_raw.csv — Generation Script
===================================================

IFRS S2 alignment:
  §8                    Strategy disclosure objective
  §14(a)(i)-(v)          Transition plan actions, assumptions, mitigation/adaptation,
                         target achievement pathway
  §14(b)                 Resources allocated to transition plan activities
  §14(c)                 Quantitative and qualitative progress from prior periods
  §29(f)                 Internal carbon price
  §33-36                 Climate-related targets and carbon credits

Table purpose:
  One row per entity × reporting_year.

  This table is structured qualitative evidence, not the final IFRS S2 report section.
  Numeric and structured fields come from existing source tables.
  GPT-4o-mini is used only to generate the narrative evidence fields.

Dependencies:
  - entity_master_raw.csv
  - esg_kpi_tracker_raw.csv
  - erm_system_raw.csv
  - scenario_model_out_raw.csv
  - internal_carbon_price_raw.csv
  - carbon_credits_raw.csv
  - board_minutes_raw.csv
  - hr_system_raw.csv
  - loan_book_raw.csv
"""

import os
import csv
import json
import time
import datetime
import urllib.request
import urllib.error
from pathlib import Path

import numpy as np
import pandas as pd


# =========================================================
# CONFIG
# =========================================================

DATA_DIR = Path("Data")

OUTPUT_CSV = DATA_DIR / "climate_transition_plan_raw.csv"
USAGE_CSV = DATA_DIR / "llm_usage_log.csv"

SCRIPT_NAME = "generate_climate_transition_plan.py"
TABLE_NAME = "climate_transition_plan_raw"

LLM_MODEL = "gpt-4o-mini"
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

PRICE_INPUT_PER_1K = 0.000150
PRICE_OUTPUT_PER_1K = 0.000600

MAX_TOKENS = 2200
SLEEP_BETWEEN_CALLS = 0.6

IFRS_S2_REFS = "§8, §14(a)(i)-(v), §14(b), §14(c), §29(f), §33-36"

NARRATIVE_KEYS = [
    "plan_summary_narrative",
    "key_assumptions_narrative",
    "dependencies_narrative",
    "direct_mitigation_narrative",
    "indirect_mitigation_narrative",
    "resource_allocation_narrative",
    "target_achievement_pathway_narrative",
    "prior_period_progress_narrative",
]


# =========================================================
# HELPERS
# =========================================================

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


def bool_count(series: pd.Series, value: bool = True) -> int:
    if series is None or len(series) == 0:
        return 0
    parsed = normalize_bool_series(series)
    return int(parsed.eq(value).sum())


def safe_sum(series: pd.Series) -> float:
    if series is None or len(series) == 0:
        return 0.0
    return float(pd.to_numeric(series, errors="coerce").fillna(0).sum())


def safe_mean(series: pd.Series):
    if series is None or len(series) == 0:
        return None
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return None
    return float(numeric.mean())


def safe_float(value):
    if pd.isna(value):
        return None
    try:
        return float(value)
    except Exception:
        return None


def to_jsonable(value):
    if value is None:
        return None

    if isinstance(value, float) and np.isnan(value):
        return None

    if pd.isna(value) and not isinstance(value, (list, dict, tuple)):
        return None

    if isinstance(value, np.integer):
        return int(value)

    if isinstance(value, np.floating):
        return float(value)

    if isinstance(value, np.bool_):
        return bool(value)

    if isinstance(value, pd.Timestamp):
        return value.isoformat()

    return value


def json_safe_records(df: pd.DataFrame) -> list[dict]:
    if df is None or df.empty:
        return []

    records = df.replace({np.nan: None}).to_dict(orient="records")

    safe_records = []
    for record in records:
        safe_records.append({
            str(k): to_jsonable(v)
            for k, v in record.items()
        })

    return safe_records


def dumps_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def parse_json_field(value, default=None):
    if default is None:
        default = []

    try:
        if pd.isna(value):
            return default
        return json.loads(value)
    except Exception:
        return default


def require_columns(df: pd.DataFrame, table_name: str, required_cols: list[str]) -> None:
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise KeyError(f"{table_name} is missing required columns: {missing}")


def year_filter(df: pd.DataFrame, year: int) -> pd.Series:
    return pd.to_numeric(df["reporting_year"], errors="coerce").astype("Int64").eq(year)


def entity_filter(df: pd.DataFrame, entity_id: str) -> pd.Series:
    if "entity_id" not in df.columns:
        return pd.Series([True] * len(df), index=df.index)
    return df["entity_id"].astype(str).eq(str(entity_id))


def load_csv_required(filename: str) -> pd.DataFrame:
    path = DATA_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return normalize_columns(pd.read_csv(path))


# =========================================================
# USAGE TRACKER
# =========================================================

class UsageTracker:
    def __init__(self, csv_path: Path, model: str, script: str, table: str):
        self.csv_path = Path(csv_path)
        self.model = model
        self.script = script
        self.table = table
        self.run_id = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        self.records = []

        self._prompt_tok = 0
        self._compl_tok = 0
        self._total_tok = 0
        self._calls_ok = 0
        self._calls_err = 0

    def log(
        self,
        row_id,
        entity_id,
        reporting_year,
        prompt_tokens,
        completion_tokens,
        total_tokens,
        status,
        latency_s,
        error_msg="",
    ):
        cost_usd = (
            prompt_tokens / 1000 * PRICE_INPUT_PER_1K
            + completion_tokens / 1000 * PRICE_OUTPUT_PER_1K
        )

        self.records.append({
            "run_id": self.run_id,
            "script": self.script,
            "table": self.table,
            "model": self.model,
            "timestamp_utc": datetime.datetime.utcnow().isoformat(timespec="seconds"),
            "row_id": row_id,
            "entity_id": entity_id,
            "reporting_year": reporting_year,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cost_usd": round(cost_usd, 6),
            "latency_s": round(latency_s, 3),
            "status": status,
            "error_msg": error_msg,
        })

        if "error" not in status:
            self._prompt_tok += prompt_tokens
            self._compl_tok += completion_tokens
            self._total_tok += total_tokens
            self._calls_ok += 1
        else:
            self._calls_err += 1

    def save(self):
        if not self.records:
            return

        new_df = pd.DataFrame(self.records)
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)

        if self.csv_path.exists():
            old_df = pd.read_csv(self.csv_path)
            out = pd.concat([old_df, new_df], ignore_index=True)
        else:
            out = new_df

        out.to_csv(
            self.csv_path,
            index=False,
            encoding="utf-8-sig",
            quoting=csv.QUOTE_ALL,
            lineterminator="\n",
        )

    def summary(self):
        total_cost = (
            self._prompt_tok / 1000 * PRICE_INPUT_PER_1K
            + self._compl_tok / 1000 * PRICE_OUTPUT_PER_1K
        )

        print("\n" + "-" * 60)
        print(f"LLM Usage Summary — run {self.run_id}")
        print("-" * 60)
        print(f"Model             : {self.model}")
        print(f"Table             : {self.table}")
        print(f"Successful calls  : {self._calls_ok}")
        print(f"Failed calls      : {self._calls_err}")
        print(f"Prompt tokens     : {self._prompt_tok:,}")
        print(f"Completion tokens : {self._compl_tok:,}")
        print(f"Total tokens      : {self._total_tok:,}")
        print(f"Estimated cost    : ${total_cost:.4f} USD")
        print(f"Usage log         : {self.csv_path}")
        print("-" * 60)


# =========================================================
# LOAD TABLES
# =========================================================

def load_tables():
    em = load_csv_required("entity_master_raw.csv")
    kpi = load_csv_required("esg_kpi_tracker_raw.csv")
    erm = load_csv_required("erm_system_raw.csv")
    sc = load_csv_required("scenario_model_out_raw.csv")
    icp = load_csv_required("internal_carbon_price_raw.csv")
    cc = load_csv_required("carbon_credits_raw.csv")
    bm = load_csv_required("board_minutes_raw.csv")
    hr = load_csv_required("hr_system_raw.csv")
    lb = load_csv_required("loan_book_raw.csv")

    # Loan book may have reporting_date instead of reporting_year
    if "reporting_year" not in lb.columns and "reporting_date" in lb.columns:
        lb["reporting_date"] = pd.to_datetime(lb["reporting_date"], errors="coerce")
        lb["reporting_year"] = lb["reporting_date"].dt.year

    require_columns(
        em,
        "entity_master_raw.csv",
        ["entity_id", "legal_name", "country_code", "in_scope_esg_flag"],
    )

    require_columns(
        kpi,
        "esg_kpi_tracker_raw.csv",
        [
            "kpi_code", "kpi_name", "category", "reporting_year",
            "baseline_year", "baseline_value", "actual_value",
            "target_year", "target_value",
        ],
    )

    require_columns(
        erm,
        "erm_system_raw.csv",
        [
            "entity_id", "reporting_year", "risk_category",
            "financial_impact_eur",
        ],
    )

    require_columns(
        sc,
        "scenario_model_out_raw.csv",
        ["scenario_id", "temperature_pathway_c", "reporting_year"],
    )

    require_columns(
        icp,
        "internal_carbon_price_raw.csv",
        [
            "entity_id", "reporting_year", "carbon_price_eur_per_tco2e",
            "applies_to_financed_emissions",
        ],
    )

    require_columns(
        cc,
        "carbon_credits_raw.csv",
        ["entity_id", "reporting_year", "volume_tco2e", "total_cost_eur", "status"],
    )

    require_columns(
        bm,
        "board_minutes_raw.csv",
        ["entity_id", "reporting_year"],
    )

    require_columns(
        hr,
        "hr_system_raw.csv",
        ["entity_id", "reporting_year"],
    )

    require_columns(
        lb,
        "loan_book_raw.csv",
        ["entity_id", "reporting_year", "outstanding_balance_eur"],
    )

    return em, kpi, erm, sc, icp, cc, bm, hr, lb


# =========================================================
# BUILD SKELETON
# =========================================================

def get_reporting_years(*dfs: pd.DataFrame) -> list[int]:
    years = set()

    for df in dfs:
        if "reporting_year" in df.columns:
            vals = (
                pd.to_numeric(df["reporting_year"], errors="coerce")
                .dropna()
                .astype(int)
                .tolist()
            )
            years |= set(vals)

    if not years:
        years = set(range(2019, 2025))

    return sorted(years)


def build_skeleton(
    em: pd.DataFrame,
    kpi: pd.DataFrame,
    erm: pd.DataFrame,
    sc: pd.DataFrame,
    icp: pd.DataFrame,
    cc: pd.DataFrame,
    bm: pd.DataFrame,
    hr: pd.DataFrame,
    lb: pd.DataFrame,
) -> pd.DataFrame:

    years = get_reporting_years(kpi, erm, sc, icp, cc, bm, hr, lb)

    in_scope_flags = normalize_bool_series(em["in_scope_esg_flag"])
    entities = em[in_scope_flags.fillna(False)].copy()

    if entities.empty:
        raise ValueError("No in-scope entities found in entity_master_raw.csv")

    rows = []

    for _, ent in entities.iterrows():
        eid = str(ent["entity_id"])
        legal_name = ent["legal_name"]
        country_code = str(ent["country_code"]).strip().upper()
        regulatory_regime = ent.get("regulatory_regime", None)

        for yr in years:

            # -------------------------------------------------
            # KPI block
            # -------------------------------------------------
            kpi_mask = (
                year_filter(kpi, yr)
                & kpi["category"].astype(str).str.lower().str.contains(
                    "climate|emission|ghg|carbon|energy",
                    na=False,
                    regex=True,
                )
            )

            if "entity_id" in kpi.columns:
                kpi_mask &= kpi["entity_id"].astype(str).eq(eid)

            kpi_cl = kpi[kpi_mask].copy()

            on_track_count = (
                bool_count(kpi_cl["on_track_flag"], True)
                if "on_track_flag" in kpi_cl.columns else 0
            )
            off_track_count = (
                bool_count(kpi_cl["on_track_flag"], False)
                if "on_track_flag" in kpi_cl.columns else 0
            )

            kpi_cols = [
                c for c in [
                    "kpi_code", "kpi_name", "baseline_year", "baseline_value",
                    "actual_value", "target_year", "target_value",
                    "target_reduction_pct", "progress_to_target_pct",
                    "on_track_flag", "source_logic",
                ]
                if c in kpi_cl.columns
            ]

            kpi_targets_json = json_safe_records(
                kpi_cl[kpi_cols].drop_duplicates(subset=["kpi_code"]).head(8)
            )

            # Prior-year KPI progress
            prior_yr = yr - 1
            prior_mask = (
                year_filter(kpi, prior_yr)
                & kpi["category"].astype(str).str.lower().str.contains(
                    "climate|emission|ghg|carbon|energy",
                    na=False,
                    regex=True,
                )
            )

            if "entity_id" in kpi.columns:
                prior_mask &= kpi["entity_id"].astype(str).eq(eid)

            kpi_prior = kpi[prior_mask].copy()

            prior_cols = [
                c for c in [
                    "kpi_code", "kpi_name", "actual_value",
                    "progress_to_target_pct", "on_track_flag",
                ]
                if c in kpi_prior.columns
            ]

            prior_kpi_progress_json = json_safe_records(
                kpi_prior[prior_cols].drop_duplicates(subset=["kpi_code"]).head(8)
            )

            # -------------------------------------------------
            # ERM block
            # -------------------------------------------------
            erm_e = erm[
                entity_filter(erm, eid)
                & year_filter(erm, yr)
                & erm["risk_category"].astype(str).str.lower().str.contains(
                    "transition|policy|technology|market|reputation",
                    na=False,
                    regex=True,
                )
            ].copy()

            erm_cols = [
                c for c in [
                    "erm_record_id", "risk_id", "risk_name",
                    "climate_risk_driver", "time_horizon",
                    "financial_impact_eur", "mitigation_status",
                    "residual_risk_rating",
                ]
                if c in erm_e.columns
            ]

            erm_summary = json_safe_records(erm_e[erm_cols].head(6))
            total_transition_risk_eur = safe_sum(erm_e["financial_impact_eur"])

            # -------------------------------------------------
            # Scenario block
            # -------------------------------------------------
            sc_yr = sc[
                entity_filter(sc, eid)
                & year_filter(sc, yr)
            ].copy()

            if "metric_category" in sc_yr.columns:
                sc_transition = sc_yr[
                    sc_yr["metric_category"].astype(str).str.lower().str.contains(
                        "transition",
                        na=False,
                    )
                ].copy()
            else:
                sc_transition = sc_yr.copy()

            if "impact_eur_m" in sc_transition.columns and not sc_transition.empty:
                max_transition_impact_eur_m = safe_float(
                    pd.to_numeric(sc_transition["impact_eur_m"], errors="coerce").max()
                )
            elif "impact_eur" in sc_transition.columns and not sc_transition.empty:
                max_transition_impact_eur_m = safe_float(
                    pd.to_numeric(sc_transition["impact_eur"], errors="coerce").max() / 1_000_000
                )
            else:
                max_transition_impact_eur_m = None

            scenario_ids_used = (
                sc_yr["scenario_id"]
                .dropna()
                .astype(str)
                .drop_duplicates()
                .head(8)
                .tolist()
            )

            temp_pathways = (
                pd.to_numeric(sc_yr["temperature_pathway_c"], errors="coerce")
                .dropna()
                .drop_duplicates()
                .sort_values()
                .tolist()
            )

            # -------------------------------------------------
            # Internal carbon price
            # -------------------------------------------------
            icp_e = icp[
                entity_filter(icp, eid)
                & year_filter(icp, yr)
            ].copy()

            if not icp_e.empty:
                carbon_price_eur = safe_float(icp_e["carbon_price_eur_per_tco2e"].iloc[0])
                icp_application = (
                    str(icp_e["application_scope"].iloc[0])
                    if "application_scope" in icp_e.columns and pd.notna(icp_e["application_scope"].iloc[0])
                    else None
                )
                icp_price_type = (
                    str(icp_e["price_type"].iloc[0])
                    if "price_type" in icp_e.columns and pd.notna(icp_e["price_type"].iloc[0])
                    else None
                )
                icp_to_financed = (
                    bool(normalize_bool_series(icp_e["applies_to_financed_emissions"]).iloc[0])
                    if "applies_to_financed_emissions" in icp_e.columns
                    else None
                )
            else:
                carbon_price_eur = None
                icp_application = None
                icp_price_type = None
                icp_to_financed = None

            # -------------------------------------------------
            # Carbon credits
            # -------------------------------------------------
            cc_e = cc[
                entity_filter(cc, eid)
                & year_filter(cc, yr)
            ].copy()

            total_credit_volume_tco2e = safe_sum(cc_e["volume_tco2e"])
            total_credit_cost_eur = safe_sum(cc_e["total_cost_eur"])

            retired_cc = cc_e[
                cc_e["status"].astype(str).str.lower().eq("retired")
            ].copy()

            retired_credit_volume_tco2e = safe_sum(retired_cc["volume_tco2e"])

            cc_standards = (
                cc_e["standard"].dropna().astype(str).drop_duplicates().head(8).tolist()
                if "standard" in cc_e.columns else []
            )
            cc_project_types = (
                cc_e["project_type"].dropna().astype(str).drop_duplicates().head(8).tolist()
                if "project_type" in cc_e.columns else []
            )
            cc_use_cases = (
                cc_e["use_case"].dropna().astype(str).drop_duplicates().head(8).tolist()
                if "use_case" in cc_e.columns else []
            )

            # -------------------------------------------------
            # Board governance
            # -------------------------------------------------
            bm_e = bm[
                entity_filter(bm, eid)
                & year_filter(bm, yr)
            ].copy()

            board_esg_meetings = (
                bool_count(bm_e["esg_agenda_flag"], True)
                if "esg_agenda_flag" in bm_e.columns else 0
            )
            board_decisions_made = (
                bool_count(bm_e["decision_made_flag"], True)
                if "decision_made_flag" in bm_e.columns else 0
            )
            board_topics = (
                bm_e["esg_topics_discussed"].dropna().astype(str).drop_duplicates().head(8).tolist()
                if "esg_topics_discussed" in bm_e.columns else []
            )
            board_action_owners = (
                bm_e["action_owner_function"].dropna().astype(str).drop_duplicates().head(8).tolist()
                if "action_owner_function" in bm_e.columns else []
            )

            # -------------------------------------------------
            # HR / resourcing
            # -------------------------------------------------
            hr_e = hr[
                entity_filter(hr, eid)
                & year_filter(hr, yr)
            ].copy()

            staff_esg_bonus_pct_avg = (
                safe_mean(hr_e["esg_bonus_weight_pct"])
                if "esg_bonus_weight_pct" in hr_e.columns else None
            )
            staff_climate_train_hrs_total = (
                safe_sum(hr_e["climate_training_hours_yr"])
                if "climate_training_hours_yr" in hr_e.columns else 0.0
            )
            staff_train_completed_count = (
                bool_count(hr_e["esg_training_completed_flag"], True)
                if "esg_training_completed_flag" in hr_e.columns else 0
            )
            staff_train_required_count = len(hr_e)

            roles_in_scope = (
                hr_e["role"].dropna().astype(str).drop_duplicates().head(10).tolist()
                if "role" in hr_e.columns else []
            )

            # -------------------------------------------------
            # Green portfolio / loan book
            # -------------------------------------------------
            lb_e = lb[
                entity_filter(lb, eid)
                & year_filter(lb, yr)
            ].copy()

            total_book_eur = safe_sum(lb_e["outstanding_balance_eur"])
            loan_book_evidence_available = total_book_eur > 0

            if "green_label_flag" in lb_e.columns:
                green_flags = normalize_bool_series(lb_e["green_label_flag"]).fillna(False)
                green_balance_eur = safe_sum(lb_e.loc[green_flags, "outstanding_balance_eur"])
            else:
                green_balance_eur = 0.0

            green_lending_share_pct = (
                green_balance_eur / total_book_eur * 100
                if total_book_eur > 0 else 0.0
            )

            green_taxonomies = (
                lb_e["green_taxonomy"].dropna().astype(str).drop_duplicates().head(10).tolist()
                if "green_taxonomy" in lb_e.columns else []
            )

            asset_class_split = {}
            if "pcaf_asset_class" in lb_e.columns and total_book_eur > 0:
                asset_class_split = (
                    lb_e.groupby("pcaf_asset_class")["outstanding_balance_eur"]
                    .sum()
                    .div(total_book_eur)
                    .mul(100)
                    .round(2)
                    .to_dict()
                )

            rows.append({
                "transition_plan_id": f"TP-{eid}-{yr}",
                "entity_id": eid,
                "entity_legal_name": legal_name,
                "country_code": country_code,
                "reporting_year": yr,
                "regulatory_regime": regulatory_regime,
                "ifrs_s2_para_refs": IFRS_S2_REFS,

                "linked_kpi_targets_json": dumps_json(kpi_targets_json),
                "kpi_on_track_count": on_track_count,
                "kpi_off_track_count": off_track_count,
                "prior_year_kpi_progress_json": dumps_json(prior_kpi_progress_json),

                "transition_risks_json": dumps_json(erm_summary),
                "total_transition_risk_eur": round(total_transition_risk_eur, 2),

                "linked_scenario_ids": dumps_json(scenario_ids_used),
                "scenario_temp_pathways": dumps_json(temp_pathways),
                "max_transition_impact_eur_m": max_transition_impact_eur_m,

                "carbon_price_eur_per_tco2e": carbon_price_eur,
                "carbon_price_type": icp_price_type,
                "carbon_price_application_scope": icp_application,
                "carbon_price_applies_to_financed_emissions": icp_to_financed,

                "carbon_credit_volume_tco2e": round(total_credit_volume_tco2e, 2),
                "retired_credit_volume_tco2e": round(retired_credit_volume_tco2e, 2),
                "carbon_credit_cost_eur": round(total_credit_cost_eur, 2),
                "carbon_credit_standards_json": dumps_json(cc_standards),
                "carbon_credit_project_types_json": dumps_json(cc_project_types),
                "carbon_credit_use_cases_json": dumps_json(cc_use_cases),

                "board_esg_meetings_count": board_esg_meetings,
                "board_decisions_made_count": board_decisions_made,
                "board_topics_json": dumps_json(board_topics),
                "board_action_owners_json": dumps_json(board_action_owners),

                "staff_esg_bonus_pct_avg": (
                    round(staff_esg_bonus_pct_avg, 2)
                    if staff_esg_bonus_pct_avg is not None else None
                ),
                "staff_climate_train_hrs_total": round(staff_climate_train_hrs_total, 2),
                "staff_train_completed_count": staff_train_completed_count,
                "staff_train_required_count": staff_train_required_count,
                "roles_in_scope_json": dumps_json(roles_in_scope),

                "total_book_eur": round(total_book_eur, 2),
                "loan_book_evidence_available": loan_book_evidence_available,
                "green_lending_balance_eur": round(green_balance_eur, 2),
                "green_lending_share_pct": round(green_lending_share_pct, 4),
                "green_taxonomies_json": dumps_json(green_taxonomies),
                "asset_class_split_json": dumps_json(asset_class_split),

                "plan_summary_narrative": None,
                "key_assumptions_narrative": None,
                "dependencies_narrative": None,
                "direct_mitigation_narrative": None,
                "indirect_mitigation_narrative": None,
                "resource_allocation_narrative": None,
                "target_achievement_pathway_narrative": None,
                "prior_period_progress_narrative": None,

                "data_source": (
                    "Derived: entity_master + esg_kpi_tracker + erm_system + "
                    "scenario_model_out + internal_carbon_price + carbon_credits + "
                    "board_minutes + hr_system + loan_book"
                ),
                "created_from": SCRIPT_NAME,
            })

    return pd.DataFrame(rows)


# =========================================================
# PROMPTS
# =========================================================

SYSTEM_PROMPT = """
You are a senior IFRS S2 climate disclosure specialist writing structured qualitative evidence for a bank's climate transition plan.

Return ONLY a valid JSON object with exactly these eight keys:

{
  "plan_summary_narrative": "...",
  "key_assumptions_narrative": "...",
  "dependencies_narrative": "...",
  "direct_mitigation_narrative": "...",
  "indirect_mitigation_narrative": "...",
  "resource_allocation_narrative": "...",
  "target_achievement_pathway_narrative": "...",
  "prior_period_progress_narrative": "..."
}

Rules:
- This is qualitative evidence, not final annual report prose.
- Use third-person, audit-friendly language.
- Each JSON value must be maximum 2 sentences.
- Keep the total JSON response concise.
- Use evidence-based wording. Do not write as if the plan is already board-approved unless the source evidence proves it.
- Prefer "the source data records", "the evidence indicates", and "can support transition-plan evidence".
- Avoid strong claims such as "the plan incorporates", "the bank utilizes", "successful implementation depends on", or "the entity is aligned with".
- Do not invent numbers, dates, targets, risks, policies, scenarios, standards, or commitments.
- Use only the evidence provided in the user prompt.
- Do not claim legal compliance unless explicitly evidenced.
- If no linked scenarios are provided, state that no scenario model output is linked for that entity-year.
- If no prior-year KPI evidence is provided, state that prior-period progress evidence is not available for that entity-year.
- If no loan book evidence is available, do not make portfolio allocation, green lending, or asset-class split claims.
- Do not use markdown fences.
- Do not add extra keys.
""".strip()


def format_json_list(value, empty_text="none linked") -> str:
    parsed = parse_json_field(value, [])
    if not parsed:
        return empty_text
    return json.dumps(parsed, ensure_ascii=False, indent=2)


def build_user_prompt(row: dict) -> str:
    linked_kpis = parse_json_field(row.get("linked_kpi_targets_json"), [])
    kpi_block = format_json_list(row.get("linked_kpi_targets_json"), "no linked climate KPI targets")
    erm_block = format_json_list(row.get("transition_risks_json"), "no linked transition risks")
    prior_block = format_json_list(row.get("prior_year_kpi_progress_json"), "no prior-year KPI evidence")

    scenario_ids = parse_json_field(row.get("linked_scenario_ids"), [])
    scenario_temps = parse_json_field(row.get("scenario_temp_pathways"), [])

    taxonomies = parse_json_field(row.get("green_taxonomies_json"), [])
    asset_split = parse_json_field(row.get("asset_class_split_json"), {})

    standards = parse_json_field(row.get("carbon_credit_standards_json"), [])
    project_types = parse_json_field(row.get("carbon_credit_project_types_json"), [])
    use_cases = parse_json_field(row.get("carbon_credit_use_cases_json"), [])

    board_topics = parse_json_field(row.get("board_topics_json"), [])
    board_owners = parse_json_field(row.get("board_action_owners_json"), [])
    roles = parse_json_field(row.get("roles_in_scope_json"), [])

    loan_book_available = bool(row.get("loan_book_evidence_available"))

    # Scenario instruction
    if scenario_ids:
        scenario_instruction = (
            "Linked scenario model outputs exist. Narrative may reference only "
            "the listed scenario IDs and temperature pathways."
        )
    else:
        scenario_instruction = (
            "No linked scenario model outputs exist for this entity-year. "
            "Narrative must not imply that entity-specific scenario analysis was performed."
        )

    # Prior-year instruction
    if prior_block == "no prior-year KPI evidence":
        prior_instruction = (
            "No prior-year KPI progress evidence is linked. Narrative must state this clearly."
        )
    else:
        prior_instruction = (
            "Prior-year KPI progress evidence is linked. Narrative may compare current-year "
            "progress with the prior-year evidence provided."
        )

    # Loan book instruction
    if loan_book_available:
        loan_book_instruction = (
            "Loan book exposure evidence is available. Narrative may reference green lending, "
            "total book, and asset-class split using only the figures provided."
        )
    else:
        loan_book_instruction = (
            "No loan book exposure is linked to this entity-year. Narrative must not make "
            "portfolio allocation, green lending, or asset-class split claims for this year."
        )

    # Baseline-year instruction
    is_baseline_year = False
    if linked_kpis:
        baseline_years = []
        for k in linked_kpis:
            try:
                if k.get("baseline_year") is not None:
                    baseline_years.append(int(k.get("baseline_year")))
            except Exception:
                pass

        is_baseline_year = int(row["reporting_year"]) in baseline_years

    if is_baseline_year:
        kpi_progress_instruction = (
            "This reporting year is a baseline year for one or more linked KPIs. "
            "If progress is 0.0%, explain that this reflects the baseline position, "
            "not necessarily poor performance."
        )
    else:
        kpi_progress_instruction = (
            "This reporting year is not identified as the baseline year for the linked KPIs. "
            "Narrative may discuss progress values if provided."
        )

    # Carbon price
    if pd.notna(row.get("carbon_price_eur_per_tco2e")):
        carbon_price_str = (
            f"EUR {float(row['carbon_price_eur_per_tco2e']):.2f}/tCO2e; "
            f"type={row['carbon_price_type']}; "
            f"application_scope={row['carbon_price_application_scope']}; "
            f"applies_to_financed_emissions={row['carbon_price_applies_to_financed_emissions']}"
        )
    else:
        carbon_price_str = "not set for this entity-year"

    return f"""
ENTITY CONTEXT
- Entity: {row["entity_legal_name"]} ({row["entity_id"]})
- Country: {row["country_code"]}
- Reporting year: {row["reporting_year"]}
- Regulatory regime: {row["regulatory_regime"]}
- IFRS S2 references: {row["ifrs_s2_para_refs"]}

CLIMATE KPI TARGETS
- On-track KPI count: {row["kpi_on_track_count"]}
- Off-track KPI count: {row["kpi_off_track_count"]}
- Baseline-year instruction: {kpi_progress_instruction}
- Linked KPI targets:
{kpi_block}

TRANSITION RISKS FROM ERM
- Total transition risk financial impact: EUR {row["total_transition_risk_eur"]:,.2f}
- Linked transition risks:
{erm_block}

SCENARIO ANALYSIS
- Linked scenario IDs: {scenario_ids}
- Temperature pathways: {scenario_temps}
- Max transition impact: EUR {row["max_transition_impact_eur_m"]} million
- Instruction: {scenario_instruction}

INTERNAL CARBON PRICE
- {carbon_price_str}

CARBON CREDITS
- Total credit volume: {row["carbon_credit_volume_tco2e"]} tCO2e
- Retired credit volume: {row["retired_credit_volume_tco2e"]} tCO2e
- Total credit cost: EUR {row["carbon_credit_cost_eur"]:,.2f}
- Standards: {standards}
- Project types: {project_types}
- Use cases: {use_cases}

BOARD GOVERNANCE
- ESG agenda meetings count: {row["board_esg_meetings_count"]}
- ESG/climate decisions made count: {row["board_decisions_made_count"]}
- Topics discussed: {board_topics}
- Action owner functions: {board_owners}

HR / RESOURCING
- Average ESG bonus weight: {row["staff_esg_bonus_pct_avg"]}%
- Total climate training hours: {row["staff_climate_train_hrs_total"]}
- Training completed / required: {row["staff_train_completed_count"]}/{row["staff_train_required_count"]}
- Roles in scope: {roles}

GREEN PORTFOLIO / RESOURCE ALLOCATION
- Loan book evidence available: {loan_book_available}
- Instruction: {loan_book_instruction}
- Total book: EUR {row["total_book_eur"]:,.2f}
- Green lending balance: EUR {row["green_lending_balance_eur"]:,.2f}
- Green lending share: {row["green_lending_share_pct"]}%
- Green taxonomies: {taxonomies}
- Asset class split: {asset_split}

PRIOR-PERIOD PROGRESS
- Prior-year KPI evidence:
{prior_block}
- Instruction: {prior_instruction}

Generate the eight JSON fields.
""".strip()


# =========================================================
# OPENAI CALL
# =========================================================

def call_openai(
    user_content: str,
    tracker: UsageTracker,
    row_id: str,
    entity_id: str,
    reporting_year: int,
    retries: int = 3,
) -> dict:

    if not OPENAI_API_KEY:
        raise EnvironmentError(
            "OPENAI_API_KEY is not set.\n"
            "PowerShell: $env:OPENAI_API_KEY=\"your_key_here\"\n"
            "Mac/Linux: export OPENAI_API_KEY=\"your_key_here\""
        )

    payload = {
        "model": LLM_MODEL,
        "max_tokens": MAX_TOKENS,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    }

    for attempt in range(retries):
        start = time.perf_counter()

        try:
            req = urllib.request.Request(
                OPENAI_API_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                },
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            latency = time.perf_counter() - start

            usage = data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", 0)

            finish_reason = data["choices"][0].get("finish_reason")

            if finish_reason == "length":
                raise json.JSONDecodeError(
                    "Model output was cut off because max_tokens was too low",
                    doc="",
                    pos=0,
                )

            content = data["choices"][0]["message"]["content"].strip()

            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            result = json.loads(content)

            status = "ok" if attempt == 0 else f"retry_{attempt}_ok"

            tracker.log(
                row_id=row_id,
                entity_id=entity_id,
                reporting_year=reporting_year,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                status=status,
                latency_s=latency,
            )

            return result

        except urllib.error.HTTPError as e:
            latency = time.perf_counter() - start
            msg = f"HTTP {e.code}: {e.read().decode(errors='replace')[:500]}"
            print(f"API error attempt {attempt + 1}: {msg}")

            tracker.log(row_id, entity_id, reporting_year, 0, 0, 0, f"error_attempt_{attempt + 1}", latency, msg)
            time.sleep(2 ** attempt)

        except urllib.error.URLError as e:
            latency = time.perf_counter() - start
            msg = str(e)
            print(f"Network error attempt {attempt + 1}: {msg}")

            tracker.log(row_id, entity_id, reporting_year, 0, 0, 0, f"error_attempt_{attempt + 1}", latency, msg)
            time.sleep(2 ** attempt)

        except json.JSONDecodeError as e:
            latency = time.perf_counter() - start
            msg = f"JSON parse error: {e}"
            print(f"Parse error attempt {attempt + 1}: {msg}")

            tracker.log(row_id, entity_id, reporting_year, 0, 0, 0, f"error_attempt_{attempt + 1}", latency, msg)
            time.sleep(1)

        except Exception as e:
            latency = time.perf_counter() - start
            msg = str(e)
            print(f"Unexpected error attempt {attempt + 1}: {msg}")

            tracker.log(row_id, entity_id, reporting_year, 0, 0, 0, f"error_attempt_{attempt + 1}", latency, msg)
            time.sleep(2 ** attempt)

    tracker.log(
        row_id,
        entity_id,
        reporting_year,
        0,
        0,
        0,
        "error_exhausted",
        0.0,
        "All retries failed",
    )
    return {}


# =========================================================
# POST-PROCESSING CONSISTENCY
# =========================================================

def apply_consistency_rules(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    for idx, row in df.iterrows():
        scenarios = parse_json_field(row.get("linked_scenario_ids"), [])
        prior = parse_json_field(row.get("prior_year_kpi_progress_json"), [])
        loan_book_available = bool(row.get("loan_book_evidence_available"))

        if not scenarios:
            current_text = str(df.at[idx, "key_assumptions_narrative"] or "")
            if "No scenario model outputs are linked" not in current_text:
                df.at[idx, "key_assumptions_narrative"] = (
                    "No scenario model outputs are linked to this entity-year in the source table. "
                    + current_text
                ).strip()

        if not prior:
            df.at[idx, "prior_period_progress_narrative"] = (
                "No prior-year KPI progress evidence is linked to this entity-year in the source table. "
                "Therefore, prior-period progress cannot be assessed from this transition plan evidence row."
            )

        if not loan_book_available:
            current_text = str(df.at[idx, "resource_allocation_narrative"] or "")
            if "No loan book exposure is linked" not in current_text:
                df.at[idx, "resource_allocation_narrative"] = (
                    "No loan book exposure is linked to this entity-year in the source table; "
                    "therefore, green lending allocation and asset-class split evidence are not available "
                    "for this transition plan row. "
                    + current_text
                ).strip()

    return df


def fill_narratives(df: pd.DataFrame, tracker: UsageTracker) -> pd.DataFrame:
    df = df.copy()
    total = len(df)

    for idx, row in df.iterrows():
        r = row.to_dict()

        print(
            f"[{idx + 1}/{total}] {r['entity_legal_name']} — {r['reporting_year']}",
            end=" ",
        )

        prompt = build_user_prompt(r)

        response = call_openai(
            user_content=prompt,
            tracker=tracker,
            row_id=r["transition_plan_id"],
            entity_id=str(r["entity_id"]),
            reporting_year=int(r["reporting_year"]),
        )

        for key in NARRATIVE_KEYS:
            df.at[idx, key] = response.get(key, "")

        last = tracker.records[-1] if tracker.records else {}
        print(
            f"-> {last.get('total_tokens', '?')} tokens | "
            f"${last.get('cost_usd', 0):.5f}"
        )

        time.sleep(SLEEP_BETWEEN_CALLS)

    df = apply_consistency_rules(df)

    return df


# =========================================================
# VALIDATION
# =========================================================

def validate(df: pd.DataFrame) -> bool:
    errors = []
    warnings = []

    if df["transition_plan_id"].duplicated().sum() > 0:
        errors.append(
            f"Duplicate transition_plan_id: {df['transition_plan_id'].duplicated().sum()}"
        )
    else:
        print("PASS transition_plan_id is unique")

    dup_entity_year = df.duplicated(subset=["entity_id", "reporting_year"]).sum()
    if dup_entity_year > 0:
        errors.append(f"Duplicate entity_id + reporting_year rows: {dup_entity_year}")
    else:
        print("PASS unique entity_id + reporting_year")

    missing_entity = df["entity_id"].isna().sum()
    if missing_entity:
        errors.append(f"Missing entity_id rows: {missing_entity}")
    else:
        print("PASS no missing entity_id")

    missing_refs = df["ifrs_s2_para_refs"].fillna("").astype(str).str.strip().eq("").sum()
    if missing_refs:
        warnings.append(f"Missing IFRS S2 refs: {missing_refs}")
    else:
        print("PASS IFRS S2 refs populated")

    for key in NARRATIVE_KEYS:
        blank_count = (
            df[key].isna().sum()
            + df[key].astype(str).str.strip().eq("").sum()
        )
        if blank_count:
            warnings.append(f"Blank narrative field {key}: {blank_count}")
        else:
            print(f"PASS {key} populated")

    no_scenario = df["linked_scenario_ids"].astype(str).eq("[]")
    bad_scenario_text = (
        no_scenario
        & df["key_assumptions_narrative"].astype(str).str.lower().str.contains(
            "scenario analysis shows|scenario analysis demonstrates|scenario analysis identifies",
            regex=True,
            na=False,
        )
    ).sum()

    if bad_scenario_text:
        warnings.append(f"Possible scenario contradiction rows: {bad_scenario_text}")
    else:
        print("PASS no obvious scenario contradiction when scenarios are empty")

    missing_loan_book_rows = (
        df["loan_book_evidence_available"]
        .astype(str)
        .str.lower()
        .isin(["false", "0"])
    ).sum()

    if missing_loan_book_rows:
        warnings.append(
            f"Rows with no linked loan book evidence: {missing_loan_book_rows}"
        )
    else:
        print("PASS all rows have linked loan book evidence")

    risky_terms = [
        "complies with",
        "compliant with",
        "is committed to",
        "we are committed",
        "we strive",
        "leading sustainability",
        "green future",
        "successful implementation depends on",
        "the plan incorporates",
        "the bank utilizes",
        "the entity is aligned with",
    ]

    for key in NARRATIVE_KEYS:
        lowered = df[key].fillna("").astype(str).str.lower()
        for term in risky_terms:
            hits = lowered.str.contains(term, regex=False).sum()
            if hits:
                warnings.append(f"Risky wording '{term}' found in {key}: {hits} rows")

    negative_amounts = {
        "total_transition_risk_eur": df["total_transition_risk_eur"].lt(0).sum(),
        "carbon_credit_volume_tco2e": df["carbon_credit_volume_tco2e"].lt(0).sum(),
        "carbon_credit_cost_eur": df["carbon_credit_cost_eur"].lt(0).sum(),
        "total_book_eur": df["total_book_eur"].lt(0).sum(),
        "green_lending_balance_eur": df["green_lending_balance_eur"].lt(0).sum(),
    }

    for col, count in negative_amounts.items():
        if count:
            errors.append(f"Negative values in {col}: {count}")
        else:
            print(f"PASS no negative values in {col}")

    green_over_book = (
        df["green_lending_balance_eur"] > df["total_book_eur"]
    ).sum()

    if green_over_book:
        errors.append(f"Rows where green lending exceeds total book: {green_over_book}")
    else:
        print("PASS green lending does not exceed total book")

    print(
        f"\nValidation result: {len(df)} rows | "
        f"{len(errors)} errors | {len(warnings)} warnings"
    )

    for error in errors:
        print(f"ERROR: {error}")

    for warning in warnings:
        print(f"WARNING: {warning}")

    return len(errors) == 0


# =========================================================
# MAIN
# =========================================================

def main():
    print("=" * 75)
    print("climate_transition_plan_raw.csv — Generation Pipeline")
    print(f"Model  : {LLM_MODEL}")
    print(f"Output : {OUTPUT_CSV}")
    print(f"Usage  : {USAGE_CSV}")
    print("=" * 75)

    tracker = UsageTracker(
        csv_path=USAGE_CSV,
        model=LLM_MODEL,
        script=SCRIPT_NAME,
        table=TABLE_NAME,
    )

    print("\n[1/5] Loading source tables...")
    em, kpi, erm, sc, icp, cc, bm, hr, lb = load_tables()

    print(f"entity_master_raw          : {len(em)} rows")
    print(f"esg_kpi_tracker_raw        : {len(kpi)} rows")
    print(f"erm_system_raw             : {len(erm)} rows")
    print(f"scenario_model_out_raw     : {len(sc)} rows")
    print(f"internal_carbon_price_raw  : {len(icp)} rows")
    print(f"carbon_credits_raw         : {len(cc)} rows")
    print(f"board_minutes_raw          : {len(bm)} rows")
    print(f"hr_system_raw              : {len(hr)} rows")
    print(f"loan_book_raw              : {len(lb)} rows")

    print("\n[2/5] Building structured transition plan skeleton...")
    df = build_skeleton(em, kpi, erm, sc, icp, cc, bm, hr, lb)
    print(f"Skeleton rows: {len(df)}")

    print("\n[3/5] Generating LLM narrative evidence...")
    df = fill_narratives(df, tracker)

    print("\n[4/5] Validating...")
    ok = validate(df)

    print("\n[5/5] Saving...")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    df.to_csv(
        OUTPUT_CSV,
        index=False,
        encoding="utf-8-sig",
        quoting=csv.QUOTE_ALL,
        lineterminator="\n",
    )

    print(f"Saved: {OUTPUT_CSV}")
    print(f"Shape: {len(df)} rows × {len(df.columns)} columns")

    tracker.save()
    tracker.summary()

    if not ok:
        raise SystemExit("Validation errors found. Review output before use.")

    print("\nDone.")
    return df


if __name__ == "__main__":
    main()