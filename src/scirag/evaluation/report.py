"""Shows a run as a table, or two runs side by side.

python -m scirag.evaluation.report eval-results/a.json [eval-results/b.json]
"""

import json
import sys
from pathlib import Path
from typing import Any

from scirag.evaluation import metrics


def _value(entry: dict[str, Any] | None) -> float | None:
    if entry is None:
        return None
    return entry.get("mean", entry.get("p50"))


def _shown(name: str, entry: dict[str, Any]) -> str:
    if "p50" in entry:
        return f"{entry['p50']:.0f} / {entry['p95']:.0f}"
    return f"{entry['mean']:.1f}" if name.startswith("tokens_") else f"{entry['mean']:.3f}"


def _heading(result: dict[str, Any]) -> str:
    data = result["dataset"]
    return (
        f"**{result['name']}** ({data['name']}, {data['papers']} papers, "
        f"{data['questions']} questions, {data['errors']} errors, commit {result['commit']})"
    )


def table(result: dict[str, Any]) -> str:
    """One run: each measure with the number of questions behind it. Times are p50 / p95."""
    lines = [_heading(result), "", "| Measure | Value | Questions |", "| --- | ---: | ---: |"]
    for name, entry in result["metrics"].items():
        lines.append(f"| {name} | {_shown(name, entry)} | {entry['n']} |")
    return "\n".join(lines)


def _answered(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["id"]: row for row in result["rows"] if "error" not in row}


def comparison(before: dict[str, Any], after: dict[str, Any]) -> str:
    """Two runs: each measure in both, and the change from the first to the second.

    Only the questions both runs got through are compared, so a run that lost
    questions to errors, or asked fewer, is not set against another set of questions.
    """
    first, second = _answered(before), _answered(after)
    shared = [question for question in first if question in second]
    before = before | {"metrics": metrics.summary([first[question] for question in shared])}
    after = after | {"metrics": metrics.summary([second[question] for question in shared])}
    lines = [
        _heading(before) + " → " + _heading(after),
        "",
        f"On the {len(shared)} questions both runs answered.",
        "",
        f"| Measure | {before['name']} | {after['name']} | Change |",
        "| --- | ---: | ---: | ---: |",
    ]
    for name in dict.fromkeys([*before["metrics"], *after["metrics"]]):
        left, right = before["metrics"].get(name), after["metrics"].get(name)
        cells = [_shown(name, entry) if entry else "–" for entry in (left, right)]
        old, new = _value(left), _value(right)
        digits = 0 if name in metrics.TIMINGS else 3
        change = f"{new - old:+.{digits}f}" if old is not None and new is not None else "–"
        lines.append(f"| {name} | {cells[0]} | {cells[1]} | {change} |")
    return "\n".join(lines)


def main() -> None:
    results = [json.loads(Path(path).read_text()) for path in sys.argv[1:3]]
    if not results:
        raise SystemExit(__doc__)
    print(table(results[0]) if len(results) == 1 else comparison(*results))


if __name__ == "__main__":
    main()
