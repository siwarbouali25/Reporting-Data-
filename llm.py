print("Strategy word count:", len(strategy_result["final_section"].split()))
print("Has all required headings:")
for h in [
    "#### Climate-related risks and opportunities",
    "#### Effects on business model and value chain",
    "#### Effects on strategy and decision-making",
    "#### Financial effects and resource allocation",
    "#### Climate resilience and scenario analysis",
    "#### Strategy limitations and evidence boundaries",
]:
    print(h, h in strategy_result["final_section"])

print("\nFinal 1000 characters:")
print(strategy_result["final_section"][-1000:])

print("\nJudge false checklist items:")
for k, v in strategy_result["judge_result"].get("checklist", {}).items():
    if v is False:
        print("-", k)