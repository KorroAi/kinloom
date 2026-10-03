"""Summarize docs/phase0b/interviews.csv against the interview threshold.

Usage: python docs/phase0b/summarize.py [path/to/interviews.csv]
Only the Python standard library is used.
"""
import csv
import sys
from collections import Counter
from pathlib import Path

STRONG_SIGNALS = {"offered_to_test", "asked_about_price", "offered_to_pay"}
VALID_SIGNALS = {"none", "asked_for_demo"} | STRONG_SIGNALS


def summarize(path: Path) -> str:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    problems = []
    for n, row in enumerate(rows, start=2):  # line 1 is the header
        if row.get("pain_unprompted", "").strip() not in {"yes", "no"}:
            problems.append(f"line {n}: pain_unprompted must be 'yes' or 'no'")
        if row.get("would_pay_signal", "").strip() not in VALID_SIGNALS:
            problems.append(f"line {n}: would_pay_signal must be one of {sorted(VALID_SIGNALS)}")

    pain = [r for r in rows if r.get("pain_unprompted", "").strip() == "yes"]
    pain_and_strong = [r for r in pain if r.get("would_pay_signal", "").strip() in STRONG_SIGNALS]
    signals = Counter(r.get("would_pay_signal", "").strip() or "(empty)" for r in rows)
    tools = Counter()
    for r in rows:
        for tool in (r.get("tools_or_assets_bought") or "").split(";"):
            if tool.strip():
                tools[tool.strip()] += 1

    lines = [
        f"Interviews: {len(rows)}",
        f"pain_unprompted = yes: {len(pain)}",
        f"pain_unprompted = yes AND strong pay signal: {len(pain_and_strong)}",
        "would_pay_signal counts: " + (", ".join(f"{k}={v}" for k, v in sorted(signals.items())) or "none"),
        "Most cited tools/assets (first bridges): " + (", ".join(f"{k} ({v})" for k, v in tools.most_common(5)) or "none"),
    ]
    if problems:
        lines.append("Data problems:")
        lines.extend(f"  - {p}" for p in problems)
    return "\n".join(lines)


if __name__ == "__main__":
    default = Path(__file__).with_name("interviews.csv")
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else default
    if not target.exists():
        sys.exit(f"File not found: {target}")
    print(summarize(target))
