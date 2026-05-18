"""
climate_policy_reference_raw.csv — Generation Script
====================================================

IFRS S2 alignment:
  - §14(a): Strategy and transition-related responses to climate-related risks and opportunities
  - §22(a): Climate resilience and scenario analysis information
  - §22(b): Key assumptions used in climate-related scenario analysis
  - §33-34: Climate-related targets and how they are informed by climate-related requirements

Table purpose:
  Structured qualitative evidence table that maps each reporting entity × year to
  the climate policies, international agreements, and jurisdictional commitments
  that shape the entity's climate-related disclosure context.

Important:
  This table is NOT the final IFRS S2 report text.
  It is a qualitative evidence input consumed later by report-generation agents.

Dependencies:
  - entity_master_raw.csv
  - scenario_model_out_raw.csv
  - esg_kpi_tracker_raw.csv
  - internal_carbon_price_raw.csv

LLM narrative fields:
  - policy_context_narrative
  - intl_agreement_alignment_note
  - jurisdictional_commitment_summary
  - scenario_policy_assumption_note
  - target_informed_by_agreement_note

All numerical values must come from existing tables.
The LLM must not invent metrics, policies, entities, dates, or amounts.
"""

import os
import json
import time
import datetime
import urllib.request
import urllib.error
import pandas as pd
import numpy as np
from pathlib import Path


# =========================================================
# CONFIG
# =========================================================

DATA_DIR = Path("Data")

OUTPUT_CSV = DATA_DIR / "climate_policy_reference_raw.csv"
USAGE_CSV = DATA_DIR / "llm_usage_log.csv"

SCRIPT_NAME = "generate_climate_policy_reference.py"
TABLE_NAME = "climate_policy_reference_raw"

LLM_MODEL = "gpt-4o-mini"
OPENAI_API_URL = "https://eyq-incubator.europe.fabric.ey.com/eyq/eu/api/openai/deployments/gpt-4o-mini/chat/completions"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# GPT-4o-mini prices used by your cost tracker
PRICE_INPUT_PER_1K = 0.000150
PRICE_OUTPUT_PER_1K = 0.000600

MAX_TOKENS = 900
SLEEP_BETWEEN_CALLS = 0.5


# =========================================================
# CONSTANTS
# =========================================================

PARIS_15 = "Paris Agreement 1.5°C"
PARIS_20 = "Paris Agreement 2°C"
GLASGOW = "Glasgow Climate Pact"
KYOTO = "Kyoto Protocol"
UAE_COP28 = "UAE Consensus COP28"

INTL_AGREEMENTS = {
    PARIS_15: {
        "temp_c": 1.5,
        "year": 2015,
        "body": "UNFCCC",
    },
    PARIS_20: {
        "temp_c": 2.0,
        "year": 2015,
        "body": "UNFCCC",
    },
    KYOTO: {
        "temp_c": None,
        "year": 1997,
        "body": "UNFCCC",
    },
    GLASGOW: {
        "temp_c": 1.5,
        "year": 2021,
        "body": "COP26",
    },
    UAE_COP28: {
        "temp_c": 1.5,
        "year": 2023,
        "body": "COP28",
    },
}

COUNTRY_POLICY_MAP = {
    "GB": {
        "regime": "UK Climate Change Act / FCA TCFD mandatory",
        "ndc_ambition": "68% by 2030 vs 1990",
        "net_zero_yr": 2050,
    },
    "DE": {
        "regime": "EU CSRD / EU ETS / German Climate Action Programme",
        "ndc_ambition": "EU: 55% by 2030 vs 1990",
        "net_zero_yr": 2045,
    },
    "FR": {
        "regime": "EU CSRD / EU ETS / Loi Energie-Climat",
        "ndc_ambition": "EU: 55% by 2030 vs 1990",
        "net_zero_yr": 2050,
    },
    "NL": {
        "regime": "EU CSRD / EU ETS / Dutch Climate Agreement",
        "ndc_ambition": "EU: 55% by 2030 vs 1990",
        "net_zero_yr": 2050,
    },
    "US": {
        "regime": "SEC Climate Disclosure Rule / US IRA",
        "ndc_ambition": "50-52% by 2030 vs 2005",
        "net_zero_yr": 2050,
    },
    "SG": {
        "regime": "MAS Guidelines / Singapore Carbon Tax",
        "ndc_ambition": "60 MtCO2e by 2030",
        "net_zero_yr": 2050,
    },
    "AU": {
        "regime": "ASRS (AASB S2 aligned) / Australian Safeguard Mechanism",
        "ndc_ambition": "43% by 2030 vs 2005",
        "net_zero_yr": 2050,
    },
    "JP": {
        "regime": "Japan GX Promotion Act / TCFD-aligned SSBJ",
        "ndc_ambition": "46% by 2030 vs 2013",
        "net_zero_yr": 2050,
    },
    "CA": {
        "regime": "Canadian ISSB-aligned draft / Carbon Pricing Act",
        "ndc_ambition": "40-45% by 2030 vs 2005",
        "net_zero_yr": 2050,
    },
    "ZA": {
        "regime": "JSE Sustainability Disclosure Guidance / SA Carbon Tax",
        "ndc_ambition": "350-420 MtCO2e by 2030",
        "net_zero_yr": 2050,
    },
}

DEFAULT_POLICY = {
    "regime": "National climate legislation / UNFCCC signatory context",
    "ndc_ambition": "NDC committed",
    "net_zero_yr": 2050,
}

IFRS_S2_REFS = "§14(a), §22(a), §22(b), §33-34"

NARRATIVE_KEYS = [
    "policy_context_narrative",
    "intl_agreement_alignment_note",
    "jurisdictional_commitment_summary",
    "scenario_policy_assumption_note",
    "target_informed_by_agreement_note",
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


def require_columns(df: pd.DataFrame, table_name: str, required_cols: list[str]) -> None:
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise KeyError(f"{table_name} is missing required columns: {missing}")


def safe_json_loads(value, default=None):
    if default is None:
        default = []
    try:
        if pd.isna(value):
            return default
        return json.loads(value)
    except Exception:
        return default


def resolve_international_agreement(scenario_temps: list[float]) -> str:
    """
    Selects an agreement reference based on scenario temperature pathways.

    If scenario temps are available:
      - <= 1.5°C -> Paris Agreement 1.5°C
      - <= 2.0°C -> Paris Agreement 2°C
      - > 2.0°C  -> Glasgow Climate Pact

    If no scenario temps are linked:
      - default to Paris Agreement 2°C as policy reference context only
    """
    if scenario_temps:
        min_temp = min(scenario_temps)

        if min_temp <= 1.5:
            return PARIS_15
        if min_temp <= 2.0:
            return PARIS_20
        return GLASGOW

    return PARIS_20


def get_years(sc: pd.DataFrame, kpi: pd.DataFrame, icp: pd.DataFrame) -> list[int]:
    years = set()

    for df in [sc, kpi, icp]:
        if "reporting_year" in df.columns:
            years |= set(
                pd.to_numeric(df["reporting_year"], errors="coerce")
                .dropna()
                .astype(int)
                .tolist()
            )

    if not years:
        years = set(range(2019, 2025))

    return sorted(years)


# =========================================================
# USAGE TRACKER
# =========================================================

class UsageTracker:
    def __init__(self, csv_path, model, script, table):
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

        out.to_csv(self.csv_path, index=False)

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
# LOAD SOURCE TABLES
# =========================================================

def load_tables():
    em = normalize_columns(pd.read_csv(DATA_DIR / "entity_master_raw.csv"))
    sc = normalize_columns(pd.read_csv(DATA_DIR / "scenario_model_out_raw.csv"))
    kpi = normalize_columns(pd.read_csv(DATA_DIR / "esg_kpi_tracker_raw.csv"))
    icp = normalize_columns(pd.read_csv(DATA_DIR / "internal_carbon_price_raw.csv"))

    require_columns(
        em,
        "entity_master_raw.csv",
        ["entity_id", "legal_name", "country_code", "in_scope_esg_flag"],
    )

    require_columns(
        sc,
        "scenario_model_out_raw.csv",
        ["scenario_id", "temperature_pathway_c", "reporting_year"],
    )

    require_columns(
        kpi,
        "esg_kpi_tracker_raw.csv",
        ["kpi_code", "kpi_name", "category", "reporting_year", "target_value", "target_year", "baseline_year"],
    )

    require_columns(
        icp,
        "internal_carbon_price_raw.csv",
        ["entity_id", "reporting_year", "carbon_price_eur_per_tco2e", "applies_to_financed_emissions"],
    )

    return em, sc, kpi, icp


# =========================================================
# BUILD SKELETON
# =========================================================

def build_skeleton(em: pd.DataFrame, sc: pd.DataFrame, kpi: pd.DataFrame, icp: pd.DataFrame) -> pd.DataFrame:
    years = get_years(sc, kpi, icp)

    in_scope_flags = normalize_bool_series(em["in_scope_esg_flag"])
    entities = em[in_scope_flags.fillna(False)].copy()

    if entities.empty:
        raise ValueError("No in-scope entities found in entity_master_raw.csv")

    rows = []

    for _, ent in entities.iterrows():
        entity_id = ent["entity_id"]
        country_code = str(ent["country_code"]).strip().upper()
        policy = COUNTRY_POLICY_MAP.get(country_code, DEFAULT_POLICY)

        for year in years:
            # Scenario linkage
            if "entity_id" in sc.columns:
                sc_year = sc[
                    (sc["entity_id"].astype(str) == str(entity_id))
                    & (pd.to_numeric(sc["reporting_year"], errors="coerce").astype("Int64") == year)
                ].copy()
            else:
                # group-level fallback if scenario_model_out is not entity-level
                sc_year = sc[
                    pd.to_numeric(sc["reporting_year"], errors="coerce").astype("Int64") == year
                ].copy()

            scenario_ids = (
                sc_year["scenario_id"]
                .dropna()
                .astype(str)
                .drop_duplicates()
                .head(10)
                .tolist()
            )

            scenario_temps = (
                pd.to_numeric(sc_year["temperature_pathway_c"], errors="coerce")
                .dropna()
                .drop_duplicates()
                .sort_values()
                .tolist()
            )

            agreement_key = resolve_international_agreement(scenario_temps)
            agreement = INTL_AGREEMENTS[agreement_key]

            # KPI linkage
            kpi_mask = (
                (pd.to_numeric(kpi["reporting_year"], errors="coerce").astype("Int64") == year)
                & kpi["category"].astype(str).str.lower().str.contains(
                    "climate|emission|ghg|carbon|energy",
                    na=False,
                    regex=True,
                )
            )

            if "entity_id" in kpi.columns:
                kpi_mask &= kpi["entity_id"].astype(str).eq(str(entity_id))

            kpi_year = (
                kpi.loc[kpi_mask, [
                    "kpi_code",
                    "kpi_name",
                    "target_value",
                    "target_year",
                    "baseline_year",
                ]]
                .drop_duplicates(subset=["kpi_code"])
                .head(5)
            )

            kpi_summary = kpi_year.to_dict(orient="records") if not kpi_year.empty else []

            # Internal carbon price
            icp_row = icp[
                (icp["entity_id"].astype(str) == str(entity_id))
                & (pd.to_numeric(icp["reporting_year"], errors="coerce").astype("Int64") == year)
            ]

            carbon_price_eur = (
                float(icp_row["carbon_price_eur_per_tco2e"].iloc[0])
                if not icp_row.empty and pd.notna(icp_row["carbon_price_eur_per_tco2e"].iloc[0])
                else None
            )

            applies_to_financed = (
                bool(normalize_bool_series(icp_row["applies_to_financed_emissions"]).iloc[0])
                if not icp_row.empty
                else None
            )

            rows.append({
                "policy_ref_id": f"POLREF-{entity_id}-{year}",
                "entity_id": entity_id,
                "entity_legal_name": ent["legal_name"],
                "country_code": country_code,
                "reporting_year": year,

                "regulatory_regime": ent.get("regulatory_regime", policy["regime"]),

                "intl_agreement_name": agreement_key,
                "intl_agreement_year": agreement["year"],
                "intl_agreement_body": agreement["body"],
                "temperature_pathway_c": agreement["temp_c"],

                "jurisdiction_policy_regime": policy["regime"],
                "ndc_ambition_summary": policy["ndc_ambition"],
                "national_net_zero_year": policy["net_zero_yr"],

                "linked_scenario_ids": json.dumps(scenario_ids),
                "scenario_temp_pathways": json.dumps(scenario_temps),
                "scenario_includes_1_5c": int(any(t <= 1.5 for t in scenario_temps)),

                "linked_kpi_targets_json": json.dumps(kpi_summary),
                "carbon_price_eur_per_tco2e": carbon_price_eur,
                "carbon_price_applies_to_financed_emissions": applies_to_financed,

                "ifrs_s2_para_refs": IFRS_S2_REFS,

                "policy_context_narrative": None,
                "intl_agreement_alignment_note": None,
                "jurisdictional_commitment_summary": None,
                "scenario_policy_assumption_note": None,
                "target_informed_by_agreement_note": None,

                "data_source": (
                    "Derived: entity_master + scenario_model_out + "
                    "esg_kpi_tracker + internal_carbon_price"
                ),
                "created_from": SCRIPT_NAME,
            })

    return pd.DataFrame(rows)


# =========================================================
# PROMPTS
# =========================================================

SYSTEM_PROMPT = """
You are a climate disclosure specialist preparing structured qualitative evidence for IFRS S2 climate-related disclosures.

You will receive structured context for one entity-year.
Return ONLY a valid JSON object with exactly these five keys:

{
  "policy_context_narrative": "...",
  "intl_agreement_alignment_note": "...",
  "jurisdictional_commitment_summary": "...",
  "scenario_policy_assumption_note": "...",
  "target_informed_by_agreement_note": "..."
}

Rules:
- These are qualitative evidence notes, not final annual report paragraphs.
- Write in third-person, audit-friendly disclosure style.
- Do not invent numbers, risks, entities, dates, policy names, targets, scenarios, or commitments.
- Do not claim legal compliance unless the context explicitly proves compliance.
- Avoid phrases like "the entity complies with", "the entity is committed to", "we are committed to", or "we strive to".
- Prefer evidence-based wording such as "operates in a jurisdiction where", "provides policy context for", and "supports interpretation of".
- If no linked scenario IDs are provided, clearly state that no scenario model output is linked for this entity-year.
- If no linked KPI targets are provided, clearly state that no KPI target evidence is linked for this entity-year.
- Do not add markdown fences, commentary, or extra keys.
""".strip()


def build_user_prompt(row: dict) -> str:
    kpis = safe_json_loads(row.get("linked_kpi_targets_json"), [])
    scenarios = safe_json_loads(row.get("linked_scenario_ids"), [])
    temps = safe_json_loads(row.get("scenario_temp_pathways"), [])

    if kpis:
        kpi_block = "\n".join(
            f"- {k.get('kpi_code')}: {k.get('kpi_name')} | "
            f"target={k.get('target_value')} by {k.get('target_year')} "
            f"(baseline year {k.get('baseline_year')})"
            for k in kpis
        )
    else:
        kpi_block = "(none linked)"

    if scenarios:
        scenario_block = ", ".join(scenarios)
    else:
        scenario_block = "(none linked)"

    if temps:
        temp_block = ", ".join(f"{t}°C" for t in temps)
    else:
        temp_block = "(none linked)"

    if pd.notna(row.get("carbon_price_eur_per_tco2e")):
        carbon_price_block = (
            f"EUR {float(row['carbon_price_eur_per_tco2e']):.2f}/tCO2e; "
            f"applies to financed emissions: "
            f"{row.get('carbon_price_applies_to_financed_emissions')}"
        )
    else:
        carbon_price_block = "not set for this entity-year"

    scenario_instruction = (
        "Scenario instruction: linked scenario outputs exist. The narrative may discuss "
        "the linked scenario temperature pathways only."
        if scenarios
        else
        "Scenario instruction: no linked scenario outputs exist for this entity-year. "
        "The scenario note must explicitly say that no scenario model output is linked; "
        "do not imply that an entity-specific scenario analysis was performed."
    )

    kpi_instruction = (
        "Target instruction: linked KPI target evidence exists. The narrative may reference "
        "only the listed KPI targets."
        if kpis
        else
        "Target instruction: no linked KPI target evidence exists for this entity-year. "
        "The target note must state that no KPI target evidence is linked."
    )

    return f"""
Entity:
- entity_id: {row["entity_id"]}
- legal_name: {row["entity_legal_name"]}
- country_code: {row["country_code"]}
- reporting_year: {row["reporting_year"]}
- regulatory_regime: {row["regulatory_regime"]}

International agreement:
- name: {row["intl_agreement_name"]}
- year: {row["intl_agreement_year"]}
- body: {row["intl_agreement_body"]}
- temperature_pathway_c: {row["temperature_pathway_c"]}

Jurisdictional climate policy:
- policy_regime: {row["jurisdiction_policy_regime"]}
- ndc_ambition_summary: {row["ndc_ambition_summary"]}
- national_net_zero_year: {row["national_net_zero_year"]}

Scenario linkage:
- linked_scenario_ids: {scenario_block}
- scenario_temp_pathways: {temp_block}
- scenario_includes_1_5c: {row["scenario_includes_1_5c"]}
- {scenario_instruction}

Linked climate KPI targets:
{kpi_block}
- {kpi_instruction}

Internal carbon price:
- {carbon_price_block}

IFRS S2 references:
- {row["ifrs_s2_para_refs"]}

Generate the five JSON fields.
""".strip()


# =========================================================
# OPENAI API CALL
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
            "OPENAI_API_KEY is not set. In PowerShell, run:\n"
            '$env:OPENAI_API_KEY="your_key_here"\n'
            "Then run the script in the same terminal."
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
                    "api-key": OPENAI_API_KEY,
                },
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            latency = time.perf_counter() - start

            usage = data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", 0)

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

            tracker.log(row_id, entity_id, reporting_year, 0, 0, 0, f"error_attempt_{attempt+1}", latency, msg)
            time.sleep(2 ** attempt)

        except urllib.error.URLError as e:
            latency = time.perf_counter() - start
            msg = str(e)
            print(f"Network error attempt {attempt + 1}: {msg}")

            tracker.log(row_id, entity_id, reporting_year, 0, 0, 0, f"error_attempt_{attempt+1}", latency, msg)
            time.sleep(2 ** attempt)

        except json.JSONDecodeError as e:
            latency = time.perf_counter() - start
            msg = f"JSON parse error: {e}"
            print(f"Parse error attempt {attempt + 1}: {msg}")

            tracker.log(row_id, entity_id, reporting_year, 0, 0, 0, f"error_attempt_{attempt+1}", latency, msg)
            time.sleep(1)

        except Exception as e:
            latency = time.perf_counter() - start
            msg = str(e)
            print(f"Unexpected error attempt {attempt + 1}: {msg}")

            tracker.log(row_id, entity_id, reporting_year, 0, 0, 0, f"error_attempt_{attempt+1}", latency, msg)
            time.sleep(2 ** attempt)

    tracker.log(row_id, entity_id, reporting_year, 0, 0, 0, "error_exhausted", 0.0, "All retries failed")
    return {}


# =========================================================
# POST-PROCESSING CONSISTENCY
# =========================================================

def apply_consistency_rules(df: pd.DataFrame) -> pd.DataFrame:
    """
    Makes sure narratives do not contradict structured fields.
    """
    df = df.copy()

    for idx, row in df.iterrows():
        scenarios = safe_json_loads(row.get("linked_scenario_ids"), [])
        kpis = safe_json_loads(row.get("linked_kpi_targets_json"), [])

        if not scenarios:
            df.at[idx, "scenario_policy_assumption_note"] = (
                "No scenario model outputs are linked to this entity-year in the source table. "
                f"The {row['temperature_pathway_c']}°C pathway is used as policy reference context "
                "rather than as evidence of an entity-specific scenario analysis result."
            )

        if not kpis:
            df.at[idx, "target_informed_by_agreement_note"] = (
                "No climate KPI target evidence is linked to this entity-year in the source table. "
                "The international agreement reference is therefore retained as policy context only, "
                "not as evidence of a quantified target pathway."
            )

    return df


# =========================================================
# FILL NARRATIVES
# =========================================================

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
            row_id=r["policy_ref_id"],
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
    import re

    errors = []
    warnings = []

    if df["policy_ref_id"].duplicated().sum() > 0:
        errors.append(f"Duplicate policy_ref_id: {df['policy_ref_id'].duplicated().sum()}")
    else:
        print("PASS policy_ref_id is unique")

    if df["entity_id"].isna().sum() > 0:
        errors.append(f"Blank entity_id rows: {df['entity_id'].isna().sum()}")
    else:
        print("PASS no blank entity_id")

    duplicate_entity_year = df.duplicated(subset=["entity_id", "reporting_year"]).sum()
    if duplicate_entity_year > 0:
        errors.append(f"Duplicate entity_id + reporting_year rows: {duplicate_entity_year}")
    else:
        print("PASS unique entity_id + reporting_year")

    for key in NARRATIVE_KEYS:
        blank_count = df[key].isna().sum() + df[key].astype(str).str.strip().eq("").sum()
        if blank_count > 0:
            warnings.append(f"Blank narrative field {key}: {blank_count}")
        else:
            print(f"PASS {key} populated")

    invalid_temp = df[
        df["temperature_pathway_c"].notna()
        & pd.to_numeric(df["temperature_pathway_c"], errors="coerce").isna()
    ]
    if not invalid_temp.empty:
        errors.append(f"Non-numeric temperature_pathway_c rows: {len(invalid_temp)}")
    else:
        print("PASS temperature_pathway_c numeric where present")

    missing_refs = df["ifrs_s2_para_refs"].fillna("").astype(str).str.strip().eq("").sum()
    if missing_refs:
        warnings.append(f"Missing IFRS S2 paragraph refs: {missing_refs}")
    else:
        print("PASS IFRS S2 paragraph refs populated")

    # Scenario contradiction guard
    no_scenario = df["linked_scenario_ids"].astype(str).eq("[]")
    bad_scenario_text = (
        no_scenario
        & df["scenario_policy_assumption_note"].astype(str).str.lower().str.contains(
            "scenario analysis was performed|scenario analysis shows|scenario analysis identifies",
            regex=True,
            na=False,
        )
    ).sum()

    if bad_scenario_text:
        warnings.append(f"Potential scenario contradiction rows: {bad_scenario_text}")
    else:
        print("PASS no obvious scenario contradiction when scenario list is empty")

    # Promotional / unsupported compliance wording guard
    risky_terms = [
        "complies with",
        "compliant with",
        "is committed to",
        "we are committed",
        "we strive",
        "leading sustainability",
        "green future",
    ]

    for key in NARRATIVE_KEYS:
        lowered = df[key].fillna("").astype(str).str.lower()
        for term in risky_terms:
            hits = lowered.str.contains(term, regex=False).sum()
            if hits:
                warnings.append(f"Risky wording '{term}' found in {key}: {hits} rows")

    # Currency invention guard
    currency_pattern = re.compile(r"(?<!\w)(EUR|USD|\$|euro)\s*[\d,]+", re.IGNORECASE)

    for key in NARRATIVE_KEYS:
        hits = df[key].dropna().apply(lambda x: bool(currency_pattern.search(str(x)))).sum()
        if hits:
            warnings.append(f"Possible invented currency figure in {key}: {hits} rows")

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
    print("=" * 70)
    print("climate_policy_reference_raw.csv — Generation Pipeline")
    print(f"Model  : {LLM_MODEL}")
    print(f"Output : {OUTPUT_CSV}")
    print(f"Usage  : {USAGE_CSV}")
    print("=" * 70)

    tracker = UsageTracker(
        csv_path=USAGE_CSV,
        model=LLM_MODEL,
        script=SCRIPT_NAME,
        table=TABLE_NAME,
    )

    print("\n[1/5] Loading source tables...")
    em, sc, kpi, icp = load_tables()

    print(f"entity_master_raw          : {len(em)} rows")
    print(f"scenario_model_out_raw     : {len(sc)} rows")
    print(f"esg_kpi_tracker_raw        : {len(kpi)} rows")
    print(f"internal_carbon_price_raw  : {len(icp)} rows")

    print("\n[2/5] Building skeleton...")
    df = build_skeleton(em, sc, kpi, icp)
    print(f"Skeleton rows: {len(df)}")

    print("\n[3/5] Generating LLM narratives...")
    df = fill_narratives(df, tracker)

    print("\n[4/5] Validating...")
    ok = validate(df)

    print("\n[5/5] Saving...")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_CSV, index=False)

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