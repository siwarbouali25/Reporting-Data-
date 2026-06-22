for _m in governance_missing_ifrs:
    print(
        "  -",
        _m.get("standard"),
        _m.get("paragraph"),
        "-",
        (_m.get("requirement_text") or "")[:80]
    )