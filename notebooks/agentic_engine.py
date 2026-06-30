"""
Agentic LangGraph engine for the IFRS per-section loop.

Design (chosen for an audit context):
- Writer + Reviser are TRUE tool-using agents: a bounded, fully-logged tool loop.
  Every tool call is recorded in state['agent_trace'] as an audit artifact.
- Judges are STRUCTURED graph nodes (one per criterion) -> aggregator. No autonomy.
- The 8 deterministic gates stay pure code, called via injected deps (unchanged logic).
- Prep (requirements/evidence/plan) runs linearly BEFORE the graph and is passed in as
  immutable `context`. Assembly runs linearly AFTER, consuming approved sections.

The chat model is abstracted behind `ChatModel`. Use `LangChainChatModel` wrapping
`AzureChatOpenAI(...).bind_tools(...)` in production; use `FakeChatModel` for tests.
"""
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol, TypedDict
from langgraph.graph import StateGraph, END


# --------------------------------------------------------------------------- #
# Chat model abstraction
# --------------------------------------------------------------------------- #
@dataclass
class ToolCall:
    name: str
    args: Dict[str, Any]
    id: str = ""


@dataclass
class AIResponse:
    content: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)


class ChatModel(Protocol):
    def complete(self, messages: List[Dict[str, Any]], tools: Optional[List["Tool"]] = None) -> AIResponse: ...


class LangChainChatModel:
    """Adapter over any LangChain chat model that supports .bind_tools (e.g. AzureChatOpenAI)."""
    def __init__(self, lc_model):
        self._m = lc_model

    def complete(self, messages, tools=None):
        from langchain_core.messages import (HumanMessage, SystemMessage, AIMessage, ToolMessage)
        lc = []
        for m in messages:
            r = m["role"]
            if r == "system": lc.append(SystemMessage(m["content"]))
            elif r == "user": lc.append(HumanMessage(m["content"]))
            elif r == "assistant": lc.append(AIMessage(m.get("content", ""), tool_calls=m.get("tool_calls", [])))
            elif r == "tool": lc.append(ToolMessage(m["content"], tool_call_id=m.get("tool_call_id", "")))
        model = self._m.bind_tools([t.as_lc() for t in tools]) if tools else self._m
        ai = model.invoke(lc)
        tcs = [ToolCall(tc["name"], tc.get("args", {}), tc.get("id", "")) for tc in getattr(ai, "tool_calls", []) or []]
        return AIResponse(content=ai.content or "", tool_calls=tcs)


# --------------------------------------------------------------------------- #
# Tools (close over the immutable prep context)
# --------------------------------------------------------------------------- #
@dataclass
class Tool:
    name: str
    description: str
    func: Callable[..., str]

    def as_lc(self):
        from langchain_core.tools import StructuredTool
        return StructuredTool.from_function(func=self.func, name=self.name, description=self.description)


def build_section_tools(context: Dict[str, Any], deps: "AgentDeps") -> List[Tool]:
    """Tool surface the writer/reviser agents may call. Thin wrappers over prep outputs."""
    sn = context["section_name"]
    return [
        Tool("get_requirements", "Get the IFRS requirements assigned to this section.",
             lambda: deps.get_requirements(sn, context)),
        Tool("get_evidence", "Get the BANK01 payload evidence mapped to this section.",
             lambda: deps.get_evidence(sn, context)),
        Tool("get_disclosure_plan", "Get the disclosure plan/blueprint for this section.",
             lambda: deps.get_disclosure_plan(sn, context)),
        Tool("search_evidence", "Search the payload evidence for a keyword or figure.",
             lambda query: deps.search_evidence(sn, context, query)),
    ]


# --------------------------------------------------------------------------- #
# Bounded, logged tool-using agent
# --------------------------------------------------------------------------- #
class ToolAgent:
    def __init__(self, model: ChatModel, tools: List[Tool], max_steps: int = 6):
        self.model = model
        self.tools = tools
        self.reg = {t.name: t for t in tools}
        self.max_steps = max_steps

    def run(self, system: str, user: str):
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        trace = []
        for _ in range(self.max_steps):
            resp = self.model.complete(messages, tools=self.tools)
            if not resp.tool_calls:
                return resp.content, trace
            messages.append({"role": "assistant", "content": resp.content,
                             "tool_calls": [tc.__dict__ for tc in resp.tool_calls]})
            for tc in resp.tool_calls:
                try:
                    obs = self.reg[tc.name].func(**tc.args)
                except Exception as e:  # tool errors are observations, not crashes
                    obs = f"ERROR: {e}"
                trace.append({"tool": tc.name, "args": tc.args, "observation_chars": len(str(obs))})
                messages.append({"role": "tool", "content": str(obs), "tool_call_id": tc.id})
        # step budget exhausted: force a final answer with no tools
        final = self.model.complete(messages + [{"role": "user", "content": "Provide the final answer now."}])
        return final.content, trace


# --------------------------------------------------------------------------- #
# Injected dependencies (code leaves + tool backends + judge backend)
# --------------------------------------------------------------------------- #
@dataclass
class AgentDeps:
    # code leaves (unchanged logic, from the notebook)
    finalize_prose: Callable
    build_claims_register: Callable
    repair_claim_evidence_sources: Callable
    run_deterministic_gates: Callable
    composite_approval_gate: Callable
    score_section_generation_output: Callable
    same_issue_signature: Callable
    save_section_iteration: Callable
    write_text: Callable
    write_json: Callable
    # tool backends (retrieval over prep context)
    get_requirements: Callable
    get_evidence: Callable
    get_disclosure_plan: Callable
    search_evidence: Callable
    # structured judge backend: (kind, section, draft, claims, context) -> {score_key: value}
    judge: Callable
    # constants
    MAX_REVISION_LOOPS: int
    SECTION_SLUGS: Dict[str, str]
    DIRS: Dict[str, Any]
    SENIOR_IFRS_VERSION: str
    # prompts (ported from the notebook's writer/reviser prompts)
    writer_system: str = "You are an IFRS S1/S2 disclosure writer. Use tools to gather requirements and evidence, then write the section in Markdown grounded only in retrieved evidence."
    reviser_system: str = "You are an IFRS reviser. Read the failures, use tools to fetch evidence, and minimally fix the section without inventing facts."
    writer_max_steps: int = 6
    reviser_max_steps: int = 6


class SectionState(TypedDict, total=False):
    section_name: str
    context: Dict[str, Any]
    draft_markdown: str
    agent_trace: List[Dict[str, Any]]
    claims: Dict[str, Any]
    deterministic: Dict[str, Any]
    judges: Optional[Dict[str, Any]]
    section_score: Dict[str, Any]
    approval: Dict[str, Any]
    iteration: int
    previous_issue_signature: Any
    _decision: str
    result: Dict[str, Any]


# --------------------------------------------------------------------------- #
# Graph
# --------------------------------------------------------------------------- #
def build_agentic_section_graph(model: ChatModel, deps: AgentDeps):

    def writer_agent(state: SectionState) -> SectionState:
        ctx = state["context"]
        agent = ToolAgent(model, build_section_tools(ctx, deps), deps.writer_max_steps)
        user = f"Write the IFRS section '{state['section_name']}'. Gather requirements and evidence via tools first."
        draft, trace = agent.run(deps.writer_system, user)
        dm = deps.finalize_prose(draft, state["section_name"])
        return {"draft_markdown": dm, "agent_trace": [{"agent": "writer", "steps": trace}],
                "iteration": 0, "previous_issue_signature": None,
                "approval": {"approved": False, "reason": "not_run"}}

    def finalize_and_claims(state: SectionState) -> SectionState:
        sn = state["section_name"]
        dm = deps.finalize_prose(state["draft_markdown"], sn)
        claims = deps.repair_claim_evidence_sources(sn, deps.build_claims_register(sn, dm))
        return {"draft_markdown": dm, "claims": claims}

    def gates(state: SectionState) -> SectionState:
        sn = state["section_name"]
        det = deps.run_deterministic_gates(sn, state["draft_markdown"], state["claims"])
        return {"deterministic": det}

    def route_after_gates(state: SectionState) -> str:
        return "judge" if state["deterministic"].get("passed", False) else "approve_gate"

    # --- structured judges: one node per criterion -> aggregate ---
    def _judge(kind):
        def node(state: SectionState) -> SectionState:
            sn = state["section_name"]
            sc = deps.judge(kind, sn, state["draft_markdown"], state["claims"], state["context"])
            merged = dict(state.get("judges") or {})
            merged[kind] = sc
            return {"judges": merged}
        return node

    def aggregate_judges(state: SectionState) -> SectionState:
        return {}  # judges already merged into state['judges'] by the per-judge nodes

    def approve_gate(state: SectionState) -> SectionState:
        sn = state["section_name"]
        det = state["deterministic"]
        judges = state.get("judges")
        approval = deps.composite_approval_gate(sn, det, judges)
        score = deps.score_section_generation_output(sn, state["draft_markdown"], det, judges, approval)
        approval["section_generation_score"] = score
        if score.get("missing_data_language_hits"):
            approval["approved"] = False
            approval.setdefault("failures", []).append(
                {"gate": "report_cleanliness_missing_data_language", "required_fixes": score["missing_data_language_hits"]})
        deps.save_section_iteration(sn, state["iteration"],
                                    {"section_name": sn, "draft_markdown": state["draft_markdown"],
                                     "senior_ifrs_version": deps.SENIOR_IFRS_VERSION},
                                    state["claims"], det, judges, approval)
        return {"approval": approval, "section_score": score}

    def route_after_approve(state: SectionState) -> str:
        return "approved" if state["approval"].get("approved") else "decide"

    def decide(state: SectionState) -> SectionState:
        sig = deps.same_issue_signature(state["approval"])
        if sig == state["previous_issue_signature"] and state["deterministic"].get("passed", False):
            return {"_decision": "human_review"}
        dec = "human_review" if state["iteration"] >= deps.MAX_REVISION_LOOPS else "revise"
        return {"previous_issue_signature": sig, "_decision": dec}

    def reviser_agent(state: SectionState) -> SectionState:
        sn = state["section_name"]
        ctx = state["context"]
        agent = ToolAgent(model, build_section_tools(ctx, deps), deps.reviser_max_steps)
        failures = state["approval"].get("failures", [])
        user = (f"Section '{sn}' failed checks: {failures}. Here is the current draft:\n\n"
                f"{state['draft_markdown']}\n\nFetch evidence as needed and return the corrected Markdown.")
        revised, trace = agent.run(deps.reviser_system, user)
        dm = deps.finalize_prose(revised, sn)
        deps.write_json({"revised_markdown": revised, "agent_trace": trace},
                        deps.DIRS["revisions"] / f"revision_{deps.SECTION_SLUGS[sn]}_iter{state['iteration']}.json")
        return {"draft_markdown": dm, "iteration": state["iteration"] + 1,
                "agent_trace": [{"agent": "reviser", "iteration": state["iteration"], "steps": trace}]}

    def approved_exit(state: SectionState) -> SectionState:
        sn = state["section_name"]; slug = deps.SECTION_SLUGS[sn]
        md_path = deps.DIRS["approved"] / f"approved_{slug}.md"
        json_path = deps.DIRS["approved"] / f"approved_{slug}.json"
        deps.write_text(state["draft_markdown"], md_path)
        deps.write_json({"section_name": sn, "status": "approved", "draft_markdown": state["draft_markdown"],
                         "claims_register": state["claims"], "approval": state["approval"],
                         "section_generation_score": state["section_score"],
                         "agent_trace": state.get("agent_trace", []),
                         "senior_ifrs_version": deps.SENIOR_IFRS_VERSION}, json_path)
        return {"result": {"section_name": sn, "status": "approved",
                           "approved_markdown_path": str(md_path), "approved_json_path": str(json_path),
                           "iterations": state["iteration"], "approval": state["approval"],
                           "section_generation_score": state["section_score"]}}

    def human_review_exit(state: SectionState) -> SectionState:
        sn = state["section_name"]; slug = deps.SECTION_SLUGS[sn]
        path = deps.DIRS["approved"] / f"human_review_{slug}.md"
        deps.write_text(deps.finalize_prose(state["draft_markdown"], sn), path)
        return {"result": {"section_name": sn, "status": "human_review", "markdown_path": str(path),
                           "approval": state["approval"],
                           "section_generation_score": state["approval"].get("section_generation_score", {}),
                           "senior_ifrs_version": deps.SENIOR_IFRS_VERSION}}

    # judges merge into a single dict across the per-criterion nodes
    from langgraph.graph import StateGraph as _SG  # noqa
    def merge_judges(old, new):
        if not old: return new
        if not new: return old
        out = dict(old); out.update(new); return out
    # annotate the reducer for 'judges'
    import typing
    g = StateGraph(SectionState)
    g.add_node("writer", writer_agent)
    g.add_node("finalize_claims", finalize_and_claims)
    g.add_node("gates", gates)
    for k in ("ifrs_coverage_judge", "evidence_judge", "style_judge"):
        g.add_node(k, _judge(k))
    g.add_node("aggregate_judges", aggregate_judges)
    g.add_node("approve_gate", approve_gate)
    g.add_node("decide", decide)
    g.add_node("revise", reviser_agent)
    g.add_node("approved", approved_exit)
    g.add_node("human_review", human_review_exit)

    g.set_entry_point("writer")
    g.add_edge("writer", "finalize_claims")
    g.add_edge("finalize_claims", "gates")
    g.add_conditional_edges("gates", route_after_gates,
                            {"judge": "ifrs_coverage_judge", "approve_gate": "approve_gate"})
    # judges run in sequence then aggregate (parallel fan-out also possible with a reducer)
    g.add_edge("ifrs_coverage_judge", "evidence_judge")
    g.add_edge("evidence_judge", "style_judge")
    g.add_edge("style_judge", "aggregate_judges")
    g.add_edge("aggregate_judges", "approve_gate")
    g.add_conditional_edges("approve_gate", route_after_approve,
                            {"approved": "approved", "decide": "decide"})
    g.add_conditional_edges("decide", lambda s: s["_decision"],
                            {"revise": "revise", "human_review": "human_review"})
    g.add_edge("revise", "finalize_claims")
    g.add_edge("approved", END)
    g.add_edge("human_review", END)
    return g.compile()


def run_section_agentic(section_name: str, context: Dict[str, Any], model: ChatModel, deps: AgentDeps) -> Dict[str, Any]:
    graph = build_agentic_section_graph(model, deps)
    limit = (deps.MAX_REVISION_LOOPS + 1) * 8 + 12
    out = graph.invoke({"section_name": section_name, "context": context},
                       config={"recursion_limit": limit})
    return out["result"]
