"""
climate_policy_reference.csv — Generation Script
=================================================
IFRS S2 alignment  : paragraphs 14(a), 22(ii)(1), 33(h), 34(a)
                     (strategy / transition plan / resilience / targets)
Primary driver     : IFRS S2 §22(ii)(1) — entities must disclose key assumptions
                     about "climate-related policies in the jurisdictions in which
                     the entity operates", and §33(h) — how "the latest international
                     agreement on climate change, including jurisdictional commitments
                     that arise from that agreement, has informed the [emissions] target".
                     §22 also requires entities to state whether their scenario analysis
                     used a scenario "aligned with the latest international agreement on
                     climate change" (para 22(i)(4)).

Table purpose      : Structured reference table that maps each reporting entity × year
                     to the climate policies and international agreements that materially
                     shape its transition-risk exposure, scenario assumptions, and
                     emissions-target-setting rationale.  This table is a qualitative
                     evidence input consumed by the report-generation layer; it does NOT
                     contain final report paragraphs.

Dependencies (all columns verified against csv_tables_verified_summary.md)
  entity_master_raw.csv          -> entity_id, legal_name, country_code,
                                    regulatory_regime, in_scope_esg_flag
  scenario_model_out_raw.csv     -> scenario_id, temperature_pathway_c, reporting_year
  esg_kpi_tracker_raw.csv        -> kpi_code, kpi_name, category, reporting_year,
                                    target_value, target_year, baseline_year
  internal_carbon_price_raw.csv  -> entity_id, reporting_year,
                                    carbon_price_eur_per_tco2e,
                                    applies_to_financed_emissions

LLM narrative fields (generated via gpt-4o-mini, OpenAI API)
  - policy_context_narrative
  - intl_agreement_alignment_note
  - jurisdictional_commitment_summary
  - scenario_policy_assumption_note
  - target_informed_by_agreement_note

All numerical values are pulled from existing tables; the LLM receives them as
context and must NOT invent new figures.
"""

import os
import json
import time
import datetime
import pandas as pd
import numpy as np
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DATA_DIR   = Path("Data")
OUTPUT_CSV = DATA_DIR / "climate_policy_reference.csv"
USAGE_CSV  = DATA_DIR / "llm_usage_log.csv"   # cumulative cross-run usage ledger

LLM_MODEL      = "gpt-4o-mini"
OPENAI_API_URL = "https://eyq-incubator.europe.fabric.ey.com/eyq/eu/api/openai/deployments/gpt-4o-mini/chat/completions"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")  # set env var before running

# gpt-4o-mini pricing USD per 1 000 tokens (update if OpenAI changes rates)
PRICE_INPUT_PER_1K  = 0.000150   # $0.150 / 1M input tokens
PRICE_OUTPUT_PER_1K = 0.000600   # $0.600 / 1M output tokens

MAX_TOKENS          = 900
SLEEP_BETWEEN_CALLS = 0.5   # seconds; raise if you hit rate limits

SCRIPT_NAME = "generate_climate_policy_reference.py"
TABLE_NAME  = "climate_policy_reference"

# ---------------------------------------------------------------------------
# International agreements catalogue
# ---------------------------------------------------------------------------
INTL_AGREEMENTS = {
    "Paris Agreement 1.5°C": {"temp_c": 1.5, "year": 2015, "body": "UNFCCC"},
    "Paris Agreement 2°C":   {"temp_c": 2.0, "year": 2015, "body": "UNFCCC"},
    "Kyoto Protocol":        {"temp_c": None, "year": 1997, "body": "UNFCCC"},
    "Glasgow Climate Pact":  {"temp_c": 1.5, "year": 2021, "body": "COP26"},
    "UAE Consensus COP28":   {"temp_c": 1.5, "year": 2023, "body": "COP28"},
}

# Country -> primary regulatory regime mapping
COUNTRY_POLICY_MAP = {
    "GB": {
        "regime":        "UK Climate Change Act / FCA TCFD mandatory",
        "ndc_ambition":  "68% by 2030 vs 1990",
        "net_zero_yr":   2050,
    },
    "DE": {
        "regime":        "EU CSRD / EU ETS / German Climate Action Programme",
        "ndc_ambition":  "EU: 55% by 2030 vs 1990",
        "net_zero_yr":   2045,
    },
    "FR": {
        "regime":        "EU CSRD / EU ETS / Loi Energie-Climat",
        "ndc_ambition":  "EU: 55% by 2030 vs 1990",
        "net_zero_yr":   2050,
    },
    "NL": {
        "regime":        "EU CSRD / EU ETS / Dutch Climate Agreement",
        "ndc_ambition":  "EU: 55% by 2030 vs 1990",
        "net_zero_yr":   2050,
    },
    "US": {
        "regime":        "SEC Climate Disclosure Rule / US IRA",
        "ndc_ambition":  "50-52% by 2030 vs 2005",
        "net_zero_yr":   2050,
    },
    "SG": {
        "regime":        "MAS Guidelines / Singapore Carbon Tax",
        "ndc_ambition":  "60 MtCO2e by 2030",
        "net_zero_yr":   2050,
    },
    "AU": {
        "regime":        "ASRS (AASB S2 aligned) / Australian Safeguard Mechanism",
        "ndc_ambition":  "43% by 2030 vs 2005",
        "net_zero_yr":   2050,
    },
    "JP": {
        "regime":        "Japan GX Promotion Act / TCFD-aligned SSBJ",
        "ndc_ambition":  "46% by 2030 vs 2013",
        "net_zero_yr":   2050,
    },
    "CA": {
        "regime":        "Canadian ISSB-aligned draft / Carbon Pricing Act",
        "ndc_ambition":  "40-45% by 2030 vs 2005",
        "net_zero_yr":   2050,
    },
    "ZA": {
        "regime":        "JSE Sustainability Disclosure Guidance / SA Carbon Tax",
        "ndc_ambition":  "350-420 MtCO2e by 2030",
        "net_zero_yr":   2050,
    },
}
DEFAULT_POLICY = {
    "regime":       "National climate legislation (UNFCCC signatory)",
    "ndc_ambition": "NDC committed",
    "net_zero_yr":  2050,
}


# ---------------------------------------------------------------------------
# Usage tracker
# ---------------------------------------------------------------------------
class UsageTracker:
    """
    Tracks token consumption and estimated cost for every LLM call.

    Records are appended to USAGE_CSV so costs accumulate across runs.
    Column schema of llm_usage_log.csv:
      run_id, script, table, model, timestamp_utc, row_id, entity_id,
      reporting_year, prompt_tokens, completion_tokens, total_tokens,
      cost_usd, latency_s, status, error_msg
    """

    def __init__(self, csv_path, model, script, table):
        self.csv_path  = Path(csv_path)
        self.model     = model
        self.script    = script
        self.table     = table
        self.run_id    = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        self.records   = []
        # Session accumulators
        self._prompt_tok = 0
        self._compl_tok  = 0
        self._total_tok  = 0
        self._calls_ok   = 0
        self._calls_err  = 0

    def log(self, row_id, entity_id, reporting_year,
            prompt_tokens, completion_tokens, total_tokens,
            status, latency_s, error_msg=""):
        cost_usd = (
            prompt_tokens     / 1000 * PRICE_INPUT_PER_1K +
            completion_tokens / 1000 * PRICE_OUTPUT_PER_1K
        )
        self.records.append({
            "run_id"            : self.run_id,
            "script"            : self.script,
            "table"             : self.table,
            "model"             : self.model,
            "timestamp_utc"     : datetime.datetime.utcnow().isoformat(timespec="seconds"),
            "row_id"            : row_id,
            "entity_id"         : entity_id,
            "reporting_year"    : reporting_year,
            "prompt_tokens"     : prompt_tokens,
            "completion_tokens" : completion_tokens,
            "total_tokens"      : total_tokens,
            "cost_usd"          : round(cost_usd, 6),
            "latency_s"         : round(latency_s, 3),
            "status"            : status,
            "error_msg"         : error_msg,
        })
        if "error" not in status:
            self._prompt_tok += prompt_tokens
            self._compl_tok  += completion_tokens
            self._total_tok  += total_tokens
            self._calls_ok   += 1
        else:
            self._calls_err  += 1

    def save(self):
        if not self.records:
            return
        new_df = pd.DataFrame(self.records)
        if self.csv_path.exists():
            combined = pd.concat(
                [pd.read_csv(self.csv_path), new_df], ignore_index=True
            )
        else:
            combined = new_df
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        combined.to_csv(self.csv_path, index=False)

    def summary(self):
        total_cost = (
            self._prompt_tok / 1000 * PRICE_INPUT_PER_1K +
            self._compl_tok  / 1000 * PRICE_OUTPUT_PER_1K
        )
        print("\n" + "-" * 55)
        print(f"  LLM Usage Summary   run {self.run_id}")
        print("-" * 55)
        print(f"  Model              : {self.model}")
        print(f"  Table              : {self.table}")
        print(f"  Successful calls   : {self._calls_ok}")
        print(f"  Failed calls       : {self._calls_err}")
        print(f"  Prompt tokens      : {self._prompt_tok:,}")
        print(f"  Completion tokens  : {self._compl_tok:,}")
        print(f"  Total tokens       : {self._total_tok:,}")
        print(f"  Estimated cost     : ${total_cost:.4f} USD")
        print(f"  Usage log          : {self.csv_path}")
        print("-" * 55)


# ---------------------------------------------------------------------------
# Load source tables
# ---------------------------------------------------------------------------
def load_tables():
    em  = pd.read_csv(DATA_DIR / "entity_master_raw.csv")
    sc  = pd.read_csv(DATA_DIR / "scenario_model_out_raw.csv")
    kpi = pd.read_csv(DATA_DIR / "esg_kpi_tracker_raw.csv")
    icp = pd.read_csv(DATA_DIR / "internal_carbon_price_raw.csv")
    return em, sc, kpi, icp


# ---------------------------------------------------------------------------
# Build skeleton rows — one per in-scope entity x reporting_year
# ---------------------------------------------------------------------------
def build_skeleton(em, sc, kpi, icp):
    years = sorted(
        set(sc["reporting_year"].dropna().astype(int).tolist()) |
        set(kpi["reporting_year"].dropna().astype(int).tolist())
    )
    entities = em[em["in_scope_esg_flag"] == 1].copy()

    rows = []
    for _, ent in entities.iterrows():
        cc  = str(ent["country_code"]).strip().upper()
        pol = COUNTRY_POLICY_MAP.get(cc, DEFAULT_POLICY)

        for yr in years:
            sc_yr          = sc[sc["reporting_year"] == yr]
            scenario_ids   = sc_yr["scenario_id"].dropna().unique().tolist()
            scenario_temps = sorted(
                sc_yr["temperature_pathway_c"].dropna().unique().tolist()
            )

            # Resolve which international agreement the scenario set covers
            if scenario_temps:
                min_temp = min(scenario_temps)
                if min_temp <= 1.5:
                    agr_key = "Paris Agreement 1.5°C"
                elif min_temp <= 2.0:
                    agr_key = "Paris Agreement 2°C"
                else:
                    agr_key = "Glasgow Climate Pact"
            else:
                agr_key = "Paris Agreement 2°C"

            ag = INTL_AGREEMENTS[agr_key]

            # Climate KPI targets for this year
            kpi_yr = kpi[
                (kpi["reporting_year"] == yr) &
                (kpi["category"].str.lower().str.contains(
                    "climate|emission|ghg|carbon", na=False
                ))
            ][["kpi_code", "kpi_name", "target_value", "target_year",
               "baseline_year"]].head(3)
            kpi_summary = kpi_yr.to_dict(orient="records") if not kpi_yr.empty else []

            # Internal carbon price
            icp_row = icp[
                (icp["entity_id"] == ent["entity_id"]) &
                (icp["reporting_year"] == yr)
            ]
            carbon_price_eur = (
                float(icp_row["carbon_price_eur_per_tco2e"].iloc[0])
                if not icp_row.empty else None
            )
            applies_financed = (
                bool(icp_row["applies_to_financed_emissions"].iloc[0])
                if not icp_row.empty else None
            )

            rows.append({
                # -- Identifiers ------------------------------------------
                "policy_ref_id"             : f"POLREF-{ent['entity_id']}-{yr}",
                "entity_id"                 : ent["entity_id"],
                "entity_legal_name"         : ent["legal_name"],
                "country_code"              : cc,
                "reporting_year"            : yr,
                "regulatory_regime"         : ent.get("regulatory_regime",
                                                       pol["regime"]),
                # -- International agreement ------------------------------
                "intl_agreement_name"       : agr_key,
                "intl_agreement_year"       : ag["year"],
                "intl_agreement_body"       : ag["body"],
                "temperature_pathway_c"     : ag["temp_c"],
                # -- Jurisdictional policy --------------------------------
                "jurisdiction_policy_regime": pol["regime"],
                "ndc_ambition_summary"      : pol["ndc_ambition"],
                "national_net_zero_year"    : pol["net_zero_yr"],
                # -- Scenario linkage -------------------------------------
                "linked_scenario_ids"       : json.dumps(scenario_ids[:5]),
                "scenario_temp_pathways"    : json.dumps(scenario_temps),
                "scenario_includes_1_5c"    : int(
                    any(t <= 1.5 for t in scenario_temps)
                ),
                # -- KPI / target linkage ---------------------------------
                "linked_kpi_targets_json"   : json.dumps(kpi_summary),
                "carbon_price_eur_per_tco2e": carbon_price_eur,
                "carbon_price_applies_to_financed_emissions": applies_financed,
                # -- IFRS S2 tagging --------------------------------------
                "ifrs_s2_para_refs"         : (
                    "§14(a), §22(i)(4), §22(ii)(1), §33(h), §34(a)"
                ),
                # -- Narrative fields (LLM) -------------------------------
                "policy_context_narrative"          : None,
                "intl_agreement_alignment_note"     : None,
                "jurisdictional_commitment_summary" : None,
                "scenario_policy_assumption_note"   : None,
                "target_informed_by_agreement_note" : None,
                # -- Provenance -------------------------------------------
                "data_source" : (
                    "Derived: entity_master + scenario_model_out + "
                    "esg_kpi_tracker + internal_carbon_price"
                ),
                "created_from": SCRIPT_NAME,
            })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "You are a climate disclosure specialist helping prepare qualitative "
    "evidence tables for an IFRS S2-compliant report. You will receive "
    "structured context about ONE entity-year record and must return ONLY "
    "a JSON object with exactly five keys:\n\n"
    "  policy_context_narrative          (2-3 sentences)\n"
    "  intl_agreement_alignment_note     (1-2 sentences)\n"
    "  jurisdictional_commitment_summary (2-3 sentences)\n"
    "  scenario_policy_assumption_note   (1-2 sentences)\n"
    "  target_informed_by_agreement_note (2-3 sentences)\n\n"
    "Rules:\n"
    "- Write in third-person disclosure style.\n"
    "- Do NOT invent any numbers not present in the context.\n"
    "- Do NOT invent risks, entities, dates, or policy names.\n"
    "- Reference only the policies and agreements given to you.\n"
    "- Each field is a qualitative evidence note, NOT a final report paragraph.\n"
    "- Return valid JSON with no markdown fences, no preamble, no extra keys."
)


def build_user_prompt(row):
    try:
        kpis = json.loads(row.get("linked_kpi_targets_json") or "[]")
        kpi_block = "\n".join(
            f"  - {k['kpi_name']} | target={k['target_value']} "
            f"by {k['target_year']} (base {k['baseline_year']})"
            for k in kpis
        ) if kpis else "  (none available)"
    except Exception:
        kpi_block = "  (none available)"

    try:
        temps    = json.loads(row.get("scenario_temp_pathways") or "[]")
        sc_block = ", ".join(f"{t}C" for t in temps) if temps else "not specified"
    except Exception:
        sc_block = "not specified"

    carbon_price_str = (
        f"EUR {row['carbon_price_eur_per_tco2e']:.1f}/tCO2e "
        f"(applies to financed emissions: "
        f"{row['carbon_price_applies_to_financed_emissions']})"
        if row.get("carbon_price_eur_per_tco2e")
        else "not set for this entity-year"
    )

    return (
        f"Entity              : {row['entity_legal_name']} ({row['entity_id']})\n"
        f"Country             : {row['country_code']}\n"
        f"Reporting year      : {row['reporting_year']}\n"
        f"Regulatory regime   : {row['regulatory_regime']}\n\n"
        f"International agreement : {row['intl_agreement_name']} "
        f"({row['intl_agreement_year']}, {row['intl_agreement_body']})\n"
        f"Temperature pathway     : {row['temperature_pathway_c']}C\n"
        f"Includes 1.5C pathway   : {'Yes' if row['scenario_includes_1_5c'] else 'No'}\n"
        f"All temp pathways       : {sc_block}\n\n"
        f"Jurisdictional policy regime  : {row['jurisdiction_policy_regime']}\n"
        f"NDC ambition summary          : {row['ndc_ambition_summary']}\n"
        f"National net-zero target year : {row['national_net_zero_year']}\n\n"
        f"Internal carbon price         : {carbon_price_str}\n\n"
        f"Linked climate KPI targets:\n{kpi_block}\n\n"
        f"IFRS S2 paragraph references  : {row['ifrs_s2_para_refs']}\n\n"
        "Generate the five narrative fields described in the system prompt."
    )


# ---------------------------------------------------------------------------
# OpenAI API call with full usage capture
# ---------------------------------------------------------------------------
NARRATIVE_KEYS = [
    "policy_context_narrative",
    "intl_agreement_alignment_note",
    "jurisdictional_commitment_summary",
    "scenario_policy_assumption_note",
    "target_informed_by_agreement_note",
]


def call_openai(user_content, tracker, row_id, entity_id, reporting_year,
                retries=3):
    import urllib.request, urllib.error

    if not OPENAI_API_KEY:
        raise EnvironmentError(
            "OPENAI_API_KEY is not set.\n"
            "Export it before running:  export OPENAI_API_KEY=sk-..."
        )

    payload = {
        "model"      : LLM_MODEL,
        "max_tokens" : MAX_TOKENS,
        "messages"   : [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_content},
        ],
    }

    for attempt in range(retries):
        t0 = time.perf_counter()
        try:
            req = urllib.request.Request(
                OPENAI_API_URL,
                data    = json.dumps(payload).encode(),
                headers = {
                    "Content-Type" : "application/json",
                    "api-key": OPENAI_API_KEY,
                },
                method  = "POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())

            latency = time.perf_counter() - t0
            usage   = data.get("usage", {})
            ptok    = usage.get("prompt_tokens", 0)
            ctok    = usage.get("completion_tokens", 0)
            ttok    = usage.get("total_tokens", 0)

            raw = data["choices"][0]["message"]["content"].strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            result = json.loads(raw)

            status = "ok" if attempt == 0 else f"retry_{attempt}_ok"
            tracker.log(row_id, entity_id, reporting_year,
                        ptok, ctok, ttok, status, latency)
            return result

        except urllib.error.HTTPError as e:
            latency = time.perf_counter() - t0
            msg     = f"HTTP {e.code}: {e.read().decode(errors='replace')[:200]}"
            print(f"    [API error attempt {attempt+1}]: {msg}")
            tracker.log(row_id, entity_id, reporting_year,
                        0, 0, 0, f"error_attempt_{attempt+1}", latency, msg)
            time.sleep(2 ** attempt)

        except urllib.error.URLError as e:
            latency = time.perf_counter() - t0
            msg     = str(e)
            print(f"    [Network error attempt {attempt+1}]: {msg}")
            tracker.log(row_id, entity_id, reporting_year,
                        0, 0, 0, f"error_attempt_{attempt+1}", latency, msg)
            time.sleep(2 ** attempt)

        except json.JSONDecodeError as e:
            latency = time.perf_counter() - t0
            msg     = f"JSON parse error: {e}"
            print(f"    [Parse error attempt {attempt+1}]: {msg}")
            tracker.log(row_id, entity_id, reporting_year,
                        0, 0, 0, f"error_attempt_{attempt+1}", latency, msg)
            time.sleep(1)

    tracker.log(row_id, entity_id, reporting_year,
                0, 0, 0, "error_exhausted", 0.0, "All retries failed")
    return {}


# ---------------------------------------------------------------------------
# Narrative fill loop
# ---------------------------------------------------------------------------
def fill_narratives(df, tracker):
    total = len(df)
    for idx, row in df.iterrows():
        r = row.to_dict()
        print(
            f"  [{idx+1}/{total}] {r['entity_legal_name']} "
            f"{r['reporting_year']}",
            end="  ",
        )
        prompt   = build_user_prompt(r)
        response = call_openai(
            prompt, tracker,
            row_id        = r["policy_ref_id"],
            entity_id     = str(r["entity_id"]),
            reporting_year= int(r["reporting_year"]),
        )
        for key in NARRATIVE_KEYS:
            df.at[idx, key] = response.get(key, "")

        last = tracker.records[-1] if tracker.records else {}
        print(
            f"-> {last.get('total_tokens','?')} tok  "
            f"${last.get('cost_usd', 0):.5f}"
        )
        time.sleep(SLEEP_BETWEEN_CALLS)

    return df


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate(df):
    import re
    errors, warnings = [], []

    # 1. Primary key uniqueness
    dupes = df["policy_ref_id"].duplicated().sum()
    if dupes:
        errors.append(f"FAIL  Duplicate policy_ref_id: {dupes} rows")
    else:
        print("  PASS  policy_ref_id is unique")

    # 2. No blank entity_id
    blank = df["entity_id"].isna().sum()
    if blank:
        errors.append(f"FAIL  Blank entity_id: {blank} rows")
    else:
        print("  PASS  No blank entity_id")

    # 3. All narrative fields populated
    for key in NARRATIVE_KEYS:
        n = df[key].isna().sum() + (df[key] == "").sum()
        if n:
            warnings.append(f"WARN  Blank [{key}]: {n} rows")
        else:
            print(f"  PASS  {key} populated")

    # 4. temperature_pathway_c numeric where present
    bad = df[
        df["temperature_pathway_c"].notna() &
        ~pd.to_numeric(df["temperature_pathway_c"], errors="coerce").notna()
    ]
    if not bad.empty:
        errors.append(f"FAIL  Non-numeric temperature_pathway_c: {len(bad)} rows")
    else:
        print("  PASS  temperature_pathway_c numeric where present")

    # 5. Heuristic: no bare currency amounts in narratives (LLM invention guard)
    pat = re.compile(r"(?<!\w)(EUR|USD|\$|euro)\s*[\d,]+", re.IGNORECASE)
    for key in NARRATIVE_KEYS:
        hits = df[key].dropna().apply(
            lambda t: bool(pat.search(str(t)))
        ).sum()
        if hits:
            warnings.append(
                f"WARN  Possible invented figure in [{key}]: {hits} rows — review"
            )

    # 6. IFRS para refs present
    missing = (df["ifrs_s2_para_refs"].fillna("") == "").sum()
    if missing:
        warnings.append(f"WARN  Missing ifrs_s2_para_refs: {missing} rows")
    else:
        print("  PASS  ifrs_s2_para_refs populated")

    print(
        f"\n  Result: {len(df)} rows | "
        f"{len(errors)} errors | {len(warnings)} warnings"
    )
    for m in errors + warnings:
        print(f"  {m}")
    return len(errors) == 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 65)
    print("climate_policy_reference.csv  —  Generation Pipeline")
    print(f"  Model  : {LLM_MODEL}")
    print(f"  Output : {OUTPUT_CSV}")
    print(f"  Usage  : {USAGE_CSV}")
    print("=" * 65)

    tracker = UsageTracker(
        csv_path=USAGE_CSV, model=LLM_MODEL,
        script=SCRIPT_NAME, table=TABLE_NAME,
    )

    print("\n[1/5] Loading source tables ...")
    em, sc, kpi, icp = load_tables()
    print(f"  entity_master         : {len(em)} rows")
    print(f"  scenario_model_out    : {len(sc)} rows")
    print(f"  esg_kpi_tracker       : {len(kpi)} rows")
    print(f"  internal_carbon_price : {len(icp)} rows")

    print("\n[2/5] Building skeleton ...")
    df = build_skeleton(em, sc, kpi, icp)
    print(f"  Skeleton rows : {len(df)}")

    print("\n[3/5] Generating LLM narratives ...")
    df = fill_narratives(df, tracker)

    print("\n[4/5] Validation checks ...")
    ok = validate(df)

    print("\n[5/5] Saving output ...")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_CSV, index=False)
    print(
        f"  Saved -> {OUTPUT_CSV}  "
        f"({len(df)} rows x {len(df.columns)} columns)"
    )

    tracker.save()
    tracker.summary()

    if not ok:
        raise SystemExit("Validation errors found — review output before use.")

    print("\nDone.")
    return df


if __name__ == "__main__":
    main()