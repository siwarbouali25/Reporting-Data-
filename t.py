# ============================================================
# CELL B11 — SCORE VERIFICATION
# ============================================================

import copy
import random

VERIFY_SECTIONS = RUN_SECTIONS            # or a subset
CANARY_SECTION = "governance"             # section used for the recall test
RUN_COLD_AUDIT = True                     # 2 judge calls per section
RUN_CANARY = True                         # 1 judge call + deterministic gates

_POSTURE_INVARIANTS = {
    # directive: (topic trigger -> only checked if the section discusses it, required patterns)
    "GAP-01": (r"[Ss]cope 1", [r"stationary combustion", r"not available|2024 only|for 2024\b"]),
    "GAP-02": (r"business travel|[Cc]ategory 6", [r"not available|2024 only|for 2024\b"]),
    "GAP-03": (r"sovereign|listed equity|investment", [r"portfolio level", r"data quality score (?:of )?3"]),
    "GAP-04": (r"intensity", [r"denominator", r"constant", r"absolute (?:financed )?emissions"]),
}


def deterministic_invariants(section_key: str) -> dict:
    wp = json.loads((PHASE_A_OUTPUT_DIR / f"work_package_{section_key}.json").read_text(encoding="utf-8"))
    draft = json.loads((PHASE_B_OUTPUT_DIR / f"draft_{section_key}.json").read_text(encoding="utf-8"))
    blocks = draft["blocks"]
    allowed = set(json.loads((PHASE_A_OUTPUT_DIR / "allowed_numbers.json").read_text(encoding="utf-8")))
    years = {str(wp["reporting_year"])} | {str(y) for y in wp["comparative_years"]}
    issues = []

    ng = number_gate(blocks, allowed, years, wp.get("entity_allowlist"))
    issues += [f"number: {v['detail']}" for v in ng["violations"]]

    mg = meta_commentary_gate(blocks)
    issues += [f"meta: block {v['block_id']}" for v in mg["violations"]]

    # citations resolve against every legitimate namespace:
    #   payload paths | computed metric ids (bare or 'metric:' prefixed)
    #   derived-facts paths | gap directive ids
    metric_ids = set(wp["computed_metrics"].keys())
    df_keys = set((wp.get("derived_facts") or {}).keys())
    gap_ids = {g["directive_id"] for g in wp.get("gap_directives", [])}

    def _resolves(cit: str) -> bool:
        cit = cit.strip()
        if cit.startswith("metric:"):
            return cit[7:] in metric_ids
        if cit in metric_ids or cit in gap_ids:
            return True
        top = re.split(r"[.\[]", cit, maxsplit=1)[0]
        return bool(top) and (top in wp["payload_slice"] or top in df_keys
                              or top in ("derived_facts", "computed_metrics"))

    for b in blocks:
        for cit in b.get("citations", []) or []:
            if isinstance(cit, str) and not _resolves(cit):
                issues.append(f"citation: unresolvable '{cit}' in {b['block_id']}")

    # mandatory coverage claimed
    mandatory = {r["requirement_id"] for r in wp["requirements"] if r["mandatory"]}
    claimed = {rid for b in blocks for rid in b.get("requirement_ids", [])}
    for rid in sorted(mandatory - claimed):
        issues.append(f"coverage: mandatory {rid} not claimed")

    # gap postures present where the topic is discussed
    full_text = " ".join(b.get("text", "") for b in blocks)
    for gid, (trigger, pats) in _POSTURE_INVARIANTS.items():
        if re.search(trigger, full_text):
            for p in pats:
                if not re.search(p, full_text, re.IGNORECASE):
                    issues.append(f"posture {gid}: pattern '{p}' absent though topic discussed")

    return {"section": section_key, "n_blocks": len(blocks), "issues": issues,
            "passed": not issues}


def cold_audit(section_key: str) -> dict:
    """Independent full-pass fact + coverage judgment of the FINAL blocks."""
    wp = json.loads((PHASE_A_OUTPUT_DIR / f"work_package_{section_key}.json").read_text(encoding="utf-8"))
    wp["_allowed_numbers"] = json.loads((PHASE_A_OUTPUT_DIR / "allowed_numbers.json").read_text(encoding="utf-8"))
    draft = json.loads((PHASE_B_OUTPUT_DIR / f"draft_{section_key}.json").read_text(encoding="utf-8"))
    state = {"section_key": section_key, "work_package": wp, "blocks": draft["blocks"],
             "plan": draft.get("plan") or {"subsections": []}, "revision_count": 0}
    fr = node_fact_judge(state)["fact_report"]
    cr = node_coverage_judge(state)["coverage_report"]
    defects = [dict(v, gate="fact_judge") for v in fr.get("violations", [])
               if v.get("kind") in FACT_BLOCKING_KINDS and not _is_pseudo_violation(v)]
    for w in cr.get("weak", []) + cr.get("missing", []):
        defects.append({"kind": "weak_coverage" if w.get("fixable_with_provided_data", True)
                        else "add_limitation_statement",
                        "detail": w.get("detail"), "gate": "coverage_judge"})
    score = section_quality_score(defects, len(draft["blocks"]))
    return {"section": section_key, "verified_score": score, "n_defects": len(defects),
            "defects": defects}


def canary_recall(section_key: str, seed: int = 7) -> dict:
    """Inject known defects into a copy of the final blocks; measure gate+judge recall."""
    rng = random.Random(seed)
    wp = json.loads((PHASE_A_OUTPUT_DIR / f"work_package_{section_key}.json").read_text(encoding="utf-8"))
    wp["_allowed_numbers"] = json.loads((PHASE_A_OUTPUT_DIR / "allowed_numbers.json").read_text(encoding="utf-8"))
    draft = json.loads((PHASE_B_OUTPUT_DIR / f"draft_{section_key}.json").read_text(encoding="utf-8"))
    blocks = copy.deepcopy(draft["blocks"])
    paras = [b for b in blocks if b.get("type") == "paragraph" and len(b.get("text", "")) > 120]
    if len(paras) < 5:  # fall back to any paragraph blocks
        paras = [b for b in blocks if b.get("type") == "paragraph"]
    if len(paras) < 5:
        return {"section": section_key, "error": "not enough paragraph blocks for canaries"}
    targets = rng.sample(paras, 5)
    canaries = []

    # C1 fabricated number (not in allowed set) - must be caught by the number gate
    targets[0]["text"] += " Additional emissions of 123,456.7 tCO2e were recorded in the period."
    canaries.append(("C1_fabricated_number", targets[0]["block_id"], "number_gate"))
    # C2 fabricated committee - fact judge (entity/unsupported)
    targets[1]["text"] += " These matters were also reviewed by the Quantum Climate Steering Council."
    canaries.append(("C2_fabricated_entity", targets[1]["block_id"], "fact_judge"))
    # C3 forbidden gap-year figure (uses an allowed numeral so only the judge can catch it)
    yr = wp["comparative_years"][0]
    some_disp = next(iter(wp["computed_metrics"].values()))["display"]
    targets[2]["text"] += f" Fleet Scope 1 emissions for {yr} amounted to {some_disp} tCO2e."
    canaries.append(("C3_forbidden_gap_claim", targets[2]["block_id"], "fact_judge"))
    # C4 flipped pairing / false attribution
    targets[3]["text"] += " The Full Board approved the climate scenario analysis methodology in 2022."
    canaries.append(("C4_false_pairing", targets[3]["block_id"], "fact_judge"))
    # C5 unsupported process claim
    targets[4]["text"] += (" Management operates a proprietary AI-based early warning system that "
                           "automatically reprices loans on climate signals.")
    canaries.append(("C5_unsupported_process", targets[4]["block_id"], "fact_judge"))

    allowed = set(wp["_allowed_numbers"])
    years = {str(wp["reporting_year"])} | {str(y) for y in wp["comparative_years"]}
    ng = number_gate(blocks, allowed, years, wp.get("entity_allowlist"))
    flagged_by_gate = {v["block_id"] for v in ng["violations"]}

    state = {"section_key": section_key, "work_package": wp, "blocks": blocks,
             "plan": draft.get("plan") or {"subsections": []}, "revision_count": 0}
    fr = node_fact_judge(state)["fact_report"]
    flagged_by_judge = {v.get("block_id") for v in fr.get("violations", [])
                        if not _is_pseudo_violation(v)}

    results = []
    for name, bid, expected in canaries:
        caught = bid in (flagged_by_gate if expected == "number_gate"
                         else flagged_by_gate | flagged_by_judge)
        results.append({"canary": name, "block": bid, "expected_by": expected, "caught": caught})
    recall = sum(r["caught"] for r in results) / len(results)
    return {"section": section_key, "recall": recall, "results": results}


# ---------------- run ----------------
print("=== 1) Deterministic invariants ===")
inv_rows = []
for sec in VERIFY_SECTIONS:
    r = deterministic_invariants(sec)
    inv_rows.append({"section": sec, "invariants_passed": r["passed"], "issues": len(r["issues"])})
    status = "OK" if r["passed"] else "ISSUES"
    print(f"  {sec:<24} {status}  ({len(r['issues'])} issues)")
    for i in r["issues"][:6]:
        print("     -", i[:140])
display(pd.DataFrame(inv_rows))

if RUN_COLD_AUDIT and not PHASE_B_CONFIG["mock_mode"]:
    print("\n=== 2) Cold-read audit (independent judge pass) ===")
    recorded = {r["section_key"]: r.get("quality_score") for r in results}
    audit_rows = []
    for sec in VERIFY_SECTIONS:
        a = cold_audit(sec)
        delta = None if recorded.get(sec) is None else round(a["verified_score"] - recorded[sec], 1)
        audit_rows.append({"section": sec, "recorded": recorded.get(sec),
                           "verified": a["verified_score"], "delta": delta,
                           "audit_defects": a["n_defects"]})
        print(f"  {sec:<24} recorded={recorded.get(sec)} verified={a['verified_score']} delta={delta}")
    display(pd.DataFrame(audit_rows))

if RUN_CANARY and not PHASE_B_CONFIG["mock_mode"]:
    print("\n=== 3) Canary recall test ===")
    c = canary_recall(CANARY_SECTION)
    if "error" in c:
        print(" ", c["error"])
    else:
        for r in c["results"]:
            print(f"  {r['canary']:<26} expected_by={r['expected_by']:<12} caught={r['caught']}")
        print(f"  JUDGE+GATE RECALL: {c['recall']:.0%}  "
              f"({'meaningful scores' if c['recall'] >= 0.8 else 'treat scores as upper bounds'})")