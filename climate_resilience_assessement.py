"""
generate_climate_resilience_assessment.py
=========================================

Purpose:
    Generate climate_resilience_assessment_raw.csv.

IFRS S2 alignment:
    §8      Strategy disclosure objective
    §15     Climate resilience of strategy and business model
    §22     Scenario analysis and climate-related assumptions
    §25     Risk management processes
    §29     Metrics used to assess climate-related risks and opportunities

Table grain:
    One row per entity_id × reporting_year × scenario_id × time_horizon_year.

Inputs:
    Data/entity_master_raw.csv
    Data/prepared_entity_scenario_analysis.csv
    Data/erm_system_raw.csv
    Data/loan_book_raw.csv
    Data/esg_kpi_tracker_raw.csv

Output:
    Data/climate_resilience_assessment_raw.csv
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

ENTITY_MASTER_PATH = DATA_DIR / "entity_master_raw.csv"
PREPARED_SCENARIO_PATH = DATA_DIR / "prepared_entity_scenario_analysis.csv"
ERM_PATH = DATA_DIR / "erm_system_raw.csv"
LOAN_BOOK_PATH = DATA_DIR / "loan_book_raw.csv"
KPI_PATH = DATA_DIR / "esg_kpi_tracker_raw.csv"

OUTPUT_CSV = DATA_DIR / "climate_resilience_assessment_raw.csv"
USAGE_CSV = DATA_DIR / "llm_usage_log.csv"
QUALITY_REPORT_CSV = DATA_DIR / "climate_resilience_assessment_quality_report.csv"

SCRIPT_NAME = "generate_climate_resilience_assessment.py"
TABLE_NAME = "climate_resilience_assessment_raw"

LLM_MODEL = "gpt-4o-mini"
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

PRICE_INPUT_PER_1K = 0.000150
PRICE_OUTPUT_PER_1K = 0.000600

MAX_TOKENS = 1600
SLEEP_BETWEEN_CALLS = 0.5

IFRS_S2_REFS = "§8, §15, §22, §25, §29"

NARRATIVE_KEYS = [
    "business_model_impact_description",
    "strategy_resilience_narrative",
    "physical_risk_explanation",
    "transition_risk_explanation",
    "mitigation_actions_narrative",
    "scenario_assumption_note",
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


def load_csv_required(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return normalize_columns(pd.read_csv(path))


def require_columns(df: pd.DataFrame, table_name: str, required_cols: list[str]) -> None:
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise KeyError(f"{table_name} is missing required columns: {missing}")


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


def safe_json_list(values) -> str:
    clean = [
        str(v)
        for v in values
        if pd.notna(v) and str(v).strip() != ""
    ]
    return json.dumps(sorted(set(clean)), ensure_ascii=False)


def parse_json_field(value, default=None):
    if default is None:
        default = []
    try:
        if pd.isna(value):
            return default
        return json.loads(value)
    except Exception:
        return default


def dumps_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


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


def entity_filter(df: pd.DataFrame, entity_id: str) -> pd.Series:
    if "entity_id" not in df.columns:
        return pd.Series([True] * len(df), index=df.index)
    return df["entity_id"].astype(str).eq(str(entity_id))


def year_filter(df: pd.DataFrame, year: int) -> pd.Series:
    return pd.to_numeric(df["reporting_year"], errors="coerce").astype("Int64").eq(year)


def json_safe_records(df: pd.DataFrame) -> list[dict]:
    if df is None or df.empty:
        return []

    df = df.replace({np.nan: None})
    records = df.to_dict(orient="records")

    clean_records = []
    for record in records:
        clean = {}
        for k, v in record.items():
            if isinstance(v, np.integer):
                clean[k] = int(v)
            elif isinstance(v, np.floating):
                clean[k] = float(v)
            elif isinstance(v, np.bool_):
                clean[k] = bool(v)
            elif pd.isna(v) if not isinstance(v, (dict, list)) else False:
                clean[k] = None
            else:
                clean[k] = v
        clean_records.append(clean)

    return clean_records


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

        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.successful_calls = 0
        self.failed_calls = 0

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
            self.prompt_tokens += prompt_tokens
            self.completion_tokens += completion_tokens
            self.total_tokens += total_tokens
            self.successful_calls += 1
        else:
            self.failed_calls += 1

    def save(self):
        if not self.records:
            return

        new_df = pd.DataFrame(self.records)

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
            self.prompt_tokens / 1000 * PRICE_INPUT_PER_1K
            + self.completion_tokens / 1000 * PRICE_OUTPUT_PER_1K
        )

        print("\nLLM usage summary")
        print("-" * 60)
        print(f"Model             : {self.model}")
        print(f"Successful calls  : {self.successful_calls}")
        print(f"Failed calls      : {self.failed_calls}")
        print(f"Prompt tokens     : {self.prompt_tokens:,}")
        print(f"Completion tokens : {self.completion_tokens:,}")
        print(f"Total tokens      : {self.total_tokens:,}")
        print(f"Estimated cost    : ${total_cost:.4f}")
        print(f"Usage log         : {self.csv_path}")


# =========================================================
# LOAD TABLES
# =========================================================

def load_tables():
    entity_master = load_csv_required(ENTITY_MASTER_PATH)
    prepared_scenario = load_csv_required(PREPARED_SCENARIO_PATH)
    erm = load_csv_required(ERM_PATH)
    loan_book = load_csv_required(LOAN_BOOK_PATH)
    kpi = load_csv_required(KPI_PATH)

    loan_book = add_reporting_year_from_date(loan_book, "loan_book_raw.csv")

    require_columns(
        entity_master,
        "entity_master_raw.csv",
        ["entity_id", "legal_name", "country_code", "in_scope_esg_flag"],
    )

    require_columns(
        prepared_scenario,
        "prepared_entity_scenario_analysis.csv",
        [
            "prepared_scenario_record_id",
            "entity_id",
            "reporting_year",
            "scenario_id",
            "scenario_family",
            "temperature_pathway_c",
            "time_horizon_year",
            "total_financial_impact_eur",
            "total_financial_impact_eur_m",
            "revenue_at_risk_pct",
            "capital_adequacy_impact_pct",
            "business_model_impact_score",
            "residual_risk_score",
        ],
    )

    require_columns(
        erm,
        "erm_system_raw.csv",
        [
            "entity_id",
            "reporting_year",
            "risk_category",
            "financial_impact_eur",
        ],
    )

    require_columns(
        loan_book,
        "loan_book_raw.csv",
        [
            "entity_id",
            "reporting_year",
            "outstanding_balance_eur",
        ],
    )

    require_columns(
        kpi,
        "esg_kpi_tracker_raw.csv",
        [
            "kpi_code",
            "kpi_name",
            "category",
            "reporting_year",
            "actual_value",
            "target_value",
        ],
    )

    return entity_master, prepared_scenario, erm, loan_book, kpi


# =========================================================
# BUILD STRUCTURED SKELETON
# =========================================================

def build_skeleton(
    entity_master: pd.DataFrame,
    prepared_scenario: pd.DataFrame,
    erm: pd.DataFrame,
    loan_book: pd.DataFrame,
    kpi: pd.DataFrame,
) -> pd.DataFrame:

    rows = []

    entity_cols = ["entity_id", "legal_name", "country_code"]
    if "regulatory_regime" in entity_master.columns:
        entity_cols.append("regulatory_regime")

    entity_lookup = entity_master[entity_cols].drop_duplicates("entity_id")

    scenario_df = prepared_scenario.merge(
        entity_lookup,
        on="entity_id",
        how="left",
        suffixes=("", "_entity"),
    )

    for _, row in scenario_df.iterrows():
        entity_id = str(row["entity_id"])
        reporting_year = int(row["reporting_year"])

        # -------------------------------------------------
        # Loan book context
        # -------------------------------------------------
        loans = loan_book[
            entity_filter(loan_book, entity_id)
            & year_filter(loan_book, reporting_year)
        ].copy()

        total_book_eur = safe_sum(loans["outstanding_balance_eur"])

        if "pcaf_asset_class" in loans.columns and total_book_eur > 0:
            asset_class_split = (
                loans.groupby("pcaf_asset_class")["outstanding_balance_eur"]
                .sum()
                .div(total_book_eur)
                .mul(100)
                .round(2)
                .to_dict()
            )
        else:
            asset_class_split = {}

        if "nace_code" in loans.columns:
            top_sector_exposures = (
                loans.groupby("nace_code")["outstanding_balance_eur"]
                .sum()
                .sort_values(ascending=False)
                .head(5)
                .reset_index()
            )
            top_sector_json = json_safe_records(top_sector_exposures)
        else:
            top_sector_json = []

        # -------------------------------------------------
        # ERM context
        # -------------------------------------------------
        erm_entity = erm[
            entity_filter(erm, entity_id)
            & year_filter(erm, reporting_year)
        ].copy()

        climate_erm = erm_entity[
            erm_entity["risk_category"].astype(str).str.lower().str.contains(
                "climate|physical|transition|policy|market|technology|reputation",
                na=False,
                regex=True,
            )
        ]

        erm_cols = [
            c for c in [
                "erm_record_id",
                "risk_id",
                "risk_name",
                "risk_category",
                "climate_risk_driver",
                "time_horizon",
                "financial_impact_eur",
                "mitigation_status",
                "residual_risk_rating",
            ]
            if c in climate_erm.columns
        ]

        climate_risks_json = json_safe_records(climate_erm[erm_cols].head(8))

        transition_risk_eur = safe_sum(
            climate_erm[
                climate_erm["risk_category"].astype(str).str.lower().str.contains(
                    "transition|policy|market|technology|reputation",
                    na=False,
                    regex=True,
                )
            ]["financial_impact_eur"]
        )

        physical_risk_eur = safe_sum(
            climate_erm[
                climate_erm["risk_category"].astype(str).str.lower().str.contains(
                    "physical|flood|heat|drought|wildfire",
                    na=False,
                    regex=True,
                )
            ]["financial_impact_eur"]
        )

        # -------------------------------------------------
        # KPI context
        # -------------------------------------------------
        kpi_entity = kpi[year_filter(kpi, reporting_year)].copy()

        if "entity_id" in kpi_entity.columns:
            kpi_entity = kpi_entity[kpi_entity["entity_id"].astype(str).eq(entity_id)]

        climate_kpis = kpi_entity[
            kpi_entity["category"].astype(str).str.lower().str.contains(
                "climate|emission|energy|carbon|financed",
                na=False,
                regex=True,
            )
        ]

        kpi_cols = [
            c for c in [
                "kpi_code",
                "kpi_name",
                "category",
                "actual_value",
                "target_value",
                "progress_to_target_pct",
                "on_track_flag",
            ]
            if c in climate_kpis.columns
        ]

        linked_kpis_json = json_safe_records(climate_kpis[kpi_cols].head(8))

        rows.append({
            "resilience_assessment_id": (
                f"CRA-{entity_id}-{reporting_year}-"
                f"{row['scenario_id']}-{row['time_horizon_year']}"
            ),
            "entity_id": entity_id,
            "entity_legal_name": row.get("legal_name", None),
            "country_code": row.get("country_code", None),
            "reporting_year": reporting_year,
            "regulatory_regime": row.get("regulatory_regime", None),
            "ifrs_s2_para_refs": IFRS_S2_REFS,

            "prepared_scenario_record_id": row["prepared_scenario_record_id"],
            "scenario_id": row["scenario_id"],
            "scenario_family": row["scenario_family"],
            "scenario_description": row.get("scenario_description", None),
            "temperature_pathway_c": row["temperature_pathway_c"],
            "time_horizon_year": row["time_horizon_year"],

            "total_entity_exposure_eur": row.get("total_entity_exposure_eur", None),
            "covered_sector_exposure_eur": row.get("covered_sector_exposure_eur", None),
            "coverage_pct_of_entity_book": row.get("coverage_pct_of_entity_book", None),
            "affected_nace_codes_json": row.get("affected_nace_codes", "[]"),
            "affected_metric_names_json": row.get("affected_metric_names", "[]"),

            "physical_risk_impact_eur": physical_risk_eur,
            "transition_risk_impact_eur": transition_risk_eur,
            "scenario_financial_impact_eur": row["total_financial_impact_eur"],
            "scenario_financial_impact_eur_m": row["total_financial_impact_eur_m"],
            "revenue_at_risk_pct": row["revenue_at_risk_pct"],
            "capital_adequacy_impact_pct": row["capital_adequacy_impact_pct"],
            "business_model_impact_score": row["business_model_impact_score"],
            "residual_risk_score": row["residual_risk_score"],

            "total_book_eur": total_book_eur,
            "asset_class_split_json": dumps_json(asset_class_split),
            "top_sector_exposures_json": dumps_json(top_sector_json),
            "climate_risks_json": dumps_json(climate_risks_json),
            "linked_kpis_json": dumps_json(linked_kpis_json),

            "business_model_impact_description": None,
            "strategy_resilience_narrative": None,
            "physical_risk_explanation": None,
            "transition_risk_explanation": None,
            "mitigation_actions_narrative": None,
            "scenario_assumption_note": None,

            "data_source": (
                "Derived: prepared_entity_scenario_analysis + erm_system + "
                "loan_book + esg_kpi_tracker + entity_master"
            ),
            "created_from": SCRIPT_NAME,
        })

    return pd.DataFrame(rows)


# =========================================================
# PROMPTS
# =========================================================

SYSTEM_PROMPT = """
You are a senior IFRS S2 climate scenario analysis and resilience disclosure specialist for a commercial bank.

Return ONLY valid JSON with exactly these six keys:

{
  "business_model_impact_description": "...",
  "strategy_resilience_narrative": "...",
  "physical_risk_explanation": "...",
  "transition_risk_explanation": "...",
  "mitigation_actions_narrative": "...",
  "scenario_assumption_note": "..."
}

Rules:
- This is qualitative evidence, not the final report section.
- Use third-person, audit-friendly language.
- Each JSON value must be maximum 2 sentences.
- Use only the structured evidence provided.
- Do not invent scenarios, financial impacts, sectors, policies, or mitigation actions.
- Clearly distinguish physical risk from transition risk.
- If physical risk impact is 0 or unavailable, say that physical risk is not quantified in the linked evidence.
- If transition risk impact is 0 or unavailable, say that transition risk is not quantified in the linked evidence.
- Do not claim the bank is resilient, compliant, aligned, or Paris-aligned unless directly evidenced.
- Prefer wording such as "the source data records", "the evidence indicates", and "can support resilience assessment evidence".
- Avoid marketing language.
- No markdown fences.
""".strip()


def build_user_prompt(row: dict) -> str:
    affected_nace = parse_json_field(row.get("affected_nace_codes_json"), [])
    affected_metrics = parse_json_field(row.get("affected_metric_names_json"), [])
    asset_split = parse_json_field(row.get("asset_class_split_json"), {})
    top_sectors = parse_json_field(row.get("top_sector_exposures_json"), [])
    risks = parse_json_field(row.get("climate_risks_json"), [])
    kpis = parse_json_field(row.get("linked_kpis_json"), [])

    physical_impact = float(row.get("physical_risk_impact_eur") or 0)
    transition_impact = float(row.get("transition_risk_impact_eur") or 0)

    if physical_impact <= 0:
        physical_instruction = (
            "Physical risk is not quantified in the linked ERM evidence. "
            "Do not invent physical damage or collateral impairment figures."
        )
    else:
        physical_instruction = (
            "Physical risk is quantified in the linked ERM evidence. "
            "Use the exact amount provided."
        )

    if transition_impact <= 0:
        transition_instruction = (
            "Transition risk is not quantified in the linked ERM evidence. "
            "Do not invent policy cost or stranded asset figures."
        )
    else:
        transition_instruction = (
            "Transition risk is quantified in the linked ERM evidence. "
            "Use the exact amount provided."
        )

    return f"""
ENTITY
- Entity: {row["entity_legal_name"]} ({row["entity_id"]})
- Country: {row["country_code"]}
- Reporting year: {row["reporting_year"]}
- Regulatory regime: {row["regulatory_regime"]}
- IFRS S2 references: {row["ifrs_s2_para_refs"]}

SCENARIO
- Scenario ID: {row["scenario_id"]}
- Scenario family: {row["scenario_family"]}
- Scenario description: {row["scenario_description"]}
- Temperature pathway: {row["temperature_pathway_c"]}°C
- Time horizon year: {row["time_horizon_year"]}

SCENARIO FINANCIAL EFFECTS
- Scenario financial impact: EUR {float(row["scenario_financial_impact_eur"]):,.2f}
- Scenario financial impact: EUR {float(row["scenario_financial_impact_eur_m"]):,.2f} million
- Revenue at risk: {row["revenue_at_risk_pct"]}%
- Capital adequacy impact: {row["capital_adequacy_impact_pct"]}%
- Business model impact score: {row["business_model_impact_score"]}/10
- Residual risk score: {row["residual_risk_score"]}/10
- Scenario exposure coverage: {row["coverage_pct_of_entity_book"]}%

AFFECTED SECTORS / METRICS
- Affected NACE codes: {affected_nace}
- Affected scenario metrics: {affected_metrics}
- Top lending sectors: {top_sectors}
- Asset class split: {asset_split}

PHYSICAL RISK
- Physical risk impact from ERM: EUR {physical_impact:,.2f}
- Instruction: {physical_instruction}

TRANSITION RISK
- Transition risk impact from ERM: EUR {transition_impact:,.2f}
- Instruction: {transition_instruction}

RISK / KPI EVIDENCE
- Climate risks from ERM: {json.dumps(risks, ensure_ascii=False)}
- Linked climate KPIs: {json.dumps(kpis, ensure_ascii=False)}

Generate the six JSON fields.
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
                    "Model output cut off because max_tokens was too low",
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
# FILL NARRATIVES
# =========================================================

def fill_narratives(df: pd.DataFrame, tracker: UsageTracker) -> pd.DataFrame:
    df = df.copy()
    total = len(df)

    for idx, row in df.iterrows():
        row_dict = row.to_dict()

        print(
            f"[{idx + 1}/{total}] "
            f"{row_dict['entity_id']} | "
            f"{row_dict['scenario_id']} | "
            f"{row_dict['time_horizon_year']}",
            end=" ",
        )

        prompt = build_user_prompt(row_dict)

        response = call_openai(
            user_content=prompt,
            tracker=tracker,
            row_id=row_dict["resilience_assessment_id"],
            entity_id=str(row_dict["entity_id"]),
            reporting_year=int(row_dict["reporting_year"]),
        )

        for key in NARRATIVE_KEYS:
            df.at[idx, key] = response.get(key, "")

        last = tracker.records[-1] if tracker.records else {}
        print(
            f"-> {last.get('total_tokens', '?')} tokens | "
            f"${last.get('cost_usd', 0):.5f}"
        )

        time.sleep(SLEEP_BETWEEN_CALLS)

    return df


# =========================================================
# VALIDATION
# =========================================================

def build_quality_report(df: pd.DataFrame) -> pd.DataFrame:
    issues = []

    risky_terms = [
        "complies with",
        "compliant with",
        "is resilient",
        "fully resilient",
        "paris-aligned",
        "is aligned with",
        "guarantees",
        "ensures",
        "leading sustainability",
    ]

    contradiction_terms = {
        "physical": [
            "flood damage",
            "heat damage",
            "collateral impairment",
            "property damage",
            "physical damage",
        ],
        "transition": [
            "policy cost",
            "stranded asset",
            "carbon tax impact",
            "technology substitution cost",
        ],
    }

    for _, row in df.iterrows():
        row_id = row.get("resilience_assessment_id")
        combined_text = " ".join(
            str(row.get(col, "") or "")
            for col in NARRATIVE_KEYS
        ).lower()

        for col in NARRATIVE_KEYS:
            value = str(row.get(col, "") or "").strip()

            if not value:
                issues.append({
                    "resilience_assessment_id": row_id,
                    "entity_id": row.get("entity_id"),
                    "reporting_year": row.get("reporting_year"),
                    "scenario_id": row.get("scenario_id"),
                    "issue_type": "missing_narrative",
                    "severity": "critical",
                    "column_name": col,
                    "issue_description": f"{col} is blank.",
                    "suggested_fix": "Regenerate the row or add fallback text.",
                })

            if len(value) > 900:
                issues.append({
                    "resilience_assessment_id": row_id,
                    "entity_id": row.get("entity_id"),
                    "reporting_year": row.get("reporting_year"),
                    "scenario_id": row.get("scenario_id"),
                    "issue_type": "narrative_too_long",
                    "severity": "low",
                    "column_name": col,
                    "issue_description": f"{col} is longer than 900 characters.",
                    "suggested_fix": "Shorten the narrative.",
                })

            lowered = value.lower()
            for term in risky_terms:
                if term in lowered:
                    issues.append({
                        "resilience_assessment_id": row_id,
                        "entity_id": row.get("entity_id"),
                        "reporting_year": row.get("reporting_year"),
                        "scenario_id": row.get("scenario_id"),
                        "issue_type": "risky_wording",
                        "severity": "medium",
                        "column_name": col,
                        "issue_description": f"Contains risky wording: '{term}'.",
                        "suggested_fix": "Use evidence-based wording.",
                    })

        physical_impact = float(row.get("physical_risk_impact_eur") or 0)
        transition_impact = float(row.get("transition_risk_impact_eur") or 0)

        if physical_impact <= 0:
            for term in contradiction_terms["physical"]:
                if term in combined_text and "not quantified" not in combined_text:
                    issues.append({
                        "resilience_assessment_id": row_id,
                        "entity_id": row.get("entity_id"),
                        "reporting_year": row.get("reporting_year"),
                        "scenario_id": row.get("scenario_id"),
                        "issue_type": "physical_risk_contradiction",
                        "severity": "high",
                        "column_name": "physical_risk_explanation",
                        "issue_description": (
                            f"Physical risk impact is 0 but narrative contains: '{term}'."
                        ),
                        "suggested_fix": (
                            "State that physical risk is not quantified in the linked evidence."
                        ),
                    })

        if transition_impact <= 0:
            for term in contradiction_terms["transition"]:
                if term in combined_text and "not quantified" not in combined_text:
                    issues.append({
                        "resilience_assessment_id": row_id,
                        "entity_id": row.get("entity_id"),
                        "reporting_year": row.get("reporting_year"),
                        "scenario_id": row.get("scenario_id"),
                        "issue_type": "transition_risk_contradiction",
                        "severity": "high",
                        "column_name": "transition_risk_explanation",
                        "issue_description": (
                            f"Transition risk impact is 0 but narrative contains: '{term}'."
                        ),
                        "suggested_fix": (
                            "State that transition risk is not quantified in the linked evidence."
                        ),
                    })

    return pd.DataFrame(issues)


def validate(df: pd.DataFrame) -> bool:
    errors = []
    warnings = []

    print("\nRunning validation...")

    if df["resilience_assessment_id"].duplicated().sum() > 0:
        errors.append(
            f"Duplicate resilience_assessment_id: "
            f"{df['resilience_assessment_id'].duplicated().sum()}"
        )
    else:
        print("PASS resilience_assessment_id is unique")

    duplicate_keys = df.duplicated(
        subset=["entity_id", "reporting_year", "scenario_id", "time_horizon_year"]
    ).sum()

    if duplicate_keys:
        errors.append(
            f"Duplicate entity/year/scenario/horizon rows: {duplicate_keys}"
        )
    else:
        print("PASS unique entity/year/scenario/horizon")

    for col in NARRATIVE_KEYS:
        blank = df[col].isna().sum() + df[col].astype(str).str.strip().eq("").sum()
        if blank:
            errors.append(f"Blank narrative column {col}: {blank}")
        else:
            print(f"PASS {col} populated")

    numeric_cols = [
        "scenario_financial_impact_eur",
        "scenario_financial_impact_eur_m",
        "revenue_at_risk_pct",
        "capital_adequacy_impact_pct",
        "business_model_impact_score",
        "residual_risk_score",
    ]

    for col in numeric_cols:
        if col in df.columns:
            invalid = pd.to_numeric(df[col], errors="coerce").isna().sum()
            if invalid:
                errors.append(f"Invalid numeric values in {col}: {invalid}")
            else:
                print(f"PASS numeric column valid: {col}")

    quality_report = build_quality_report(df)

    quality_report.to_csv(
        QUALITY_REPORT_CSV,
        index=False,
        encoding="utf-8-sig",
        quoting=csv.QUOTE_ALL,
        lineterminator="\n",
    )

    print(f"Quality report saved: {QUALITY_REPORT_CSV}")
    print(f"Quality issues found: {len(quality_report)}")

    if not quality_report.empty:
        print("\nQuality issues by severity:")
        print(quality_report["severity"].value_counts().to_string())

        high_critical = quality_report[
            quality_report["severity"].isin(["high", "critical"])
        ].shape[0]

        if high_critical:
            warnings.append(
                f"High/critical quality issues found: {high_critical}. "
                f"Review {QUALITY_REPORT_CSV}"
            )
    else:
        print("PASS no narrative quality issues")

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
    print("climate_resilience_assessment_raw.csv generation")
    print(f"Output : {OUTPUT_CSV}")
    print(f"Usage  : {USAGE_CSV}")
    print(f"Quality: {QUALITY_REPORT_CSV}")
    print("=" * 75)

    tracker = UsageTracker(
        csv_path=USAGE_CSV,
        model=LLM_MODEL,
        script=SCRIPT_NAME,
        table=TABLE_NAME,
    )

    print("\n[1/5] Loading source tables...")
    entity_master, prepared_scenario, erm, loan_book, kpi = load_tables()

    print(f"entity_master_raw                  : {len(entity_master)} rows")
    print(f"prepared_entity_scenario_analysis  : {len(prepared_scenario)} rows")
    print(f"erm_system_raw                     : {len(erm)} rows")
    print(f"loan_book_raw                      : {len(loan_book)} rows")
    print(f"esg_kpi_tracker_raw                : {len(kpi)} rows")

    print("\n[2/5] Building resilience assessment skeleton...")
    df = build_skeleton(
        entity_master=entity_master,
        prepared_scenario=prepared_scenario,
        erm=erm,
        loan_book=loan_book,
        kpi=kpi,
    )

    print(f"Skeleton shape: {df.shape}")

    print("\n[3/5] Generating LLM narrative evidence...")
    df = fill_narratives(df, tracker)

    print("\n[4/5] Validating...")
    ok = validate(df)

    print("\n[5/5] Saving...")
    df.to_csv(
        OUTPUT_CSV,
        index=False,
        encoding="utf-8-sig",
        quoting=csv.QUOTE_ALL,
        lineterminator="\n",
    )

    print(f"Saved: {OUTPUT_CSV}")
    print(f"Shape: {df.shape}")

    tracker.save()
    tracker.summary()

    if not ok:
        raise SystemExit("Validation errors found. Review output before use.")

    print("\nDone.")
    return df


if __name__ == "__main__":
    main()