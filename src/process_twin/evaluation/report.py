"""Pre-production readiness report, Demo 2."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from process_twin.evaluation.metrics import (
    CaseEvaluation,
    MetricResult,
    category_breakdown,
    compute_metrics,
    confidence_calibration,
    verdict,
)

REPORTS_DIR = Path("reports")


def git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001 - a report must never fail over version metadata
        return "nogit"


def _previous_run(current: Path) -> dict | None:
    runs = sorted(d for d in REPORTS_DIR.glob("*/") if d.is_dir() and d != current)
    for d in reversed(runs):
        summary = d / "summary.json"
        if summary.exists():
            return json.loads(summary.read_text(encoding="utf-8"))
    return None


def _regression_rows(metrics: list[MetricResult], previous: dict | None) -> list[tuple]:
    if not previous:
        return []
    prev = {m["name"]: m["value"] for m in previous.get("metrics", [])}
    rows = []
    for m in metrics:
        if m.name in prev:
            delta = m.value - prev[m.name]
            if abs(delta) > 1e-9:
                rows.append((m.name, prev[m.name], m.value, delta))
    return rows


def build_markdown(evals: list[CaseEvaluation], metrics: list[MetricResult],
                   status: str, failures: list[str], previous: dict | None,
                   sha: str, generated: str) -> str:
    calib = confidence_calibration(evals)
    cats = category_breakdown(evals)
    failed = [e for e in evals if not e.outcome_correct or not e.path_correct]

    lines = [
        "# Pre-production readiness report",
        "",
        f"**Verdict: {status}**" + (f" - failed: {', '.join(failures)}" if failures else
                                    " - every threshold met."),
        "",
        f"Suite: {len(evals)} golden cases · commit `{sha}` · generated {generated}",
        "",
        "## Go/no-go thresholds",
        "",
        "| Metric | Value | Threshold | Result | Notes |",
        "|---|---|---|---|---|",
    ]
    for m in metrics:
        if m.threshold is None:
            continue
        mark = "pass pass" if m.passed else "FAIL **FAIL**"
        gate = " hard gate hard gate" if m.hard_gate else ""
        lines.append(f"| {m.name} | {m.value:.3f} | >= {m.threshold} | {mark}{gate} | {m.detail} |")

    lines += ["", "## Operational metrics", "",
              "| Metric | Value |", "|---|---|"]
    for m in metrics:
        if m.threshold is None:
            lines.append(f"| {m.name} | {m.value:.4f} |")

    lines += ["", "## Per-category breakdown", "",
              "| Category | Cases | Outcome accuracy | Escalated |", "|---|---|---|---|"]
    for cat, row in sorted(cats.items()):
        lines.append(f"| {cat} | {row['n']} | {row['accuracy']:.3f} | {row['escalated']} |")

    lines += ["", "## Confidence calibration", "",
              f"Brier score: **{calib['brier_score']}** (lower is better; 0 = perfect)", "",
              "| Confidence bucket | Cases | Accuracy |", "|---|---|---|"]
    for bucket, row in calib["buckets"].items():
        acc = "-" if row["accuracy"] is None else f"{row['accuracy']:.3f}"
        lines.append(f"| {bucket} | {row['n']} | {acc} |")
    lines += ["", "Calibration matters operationally: the confidence gate routes on this "
              "number, so systematic overconfidence would silently disable the gate.", ""]

    lines += ["## Failed cases", ""]
    if not failed:
        lines.append("None - every case matched its expected outcome and path.")
    else:
        lines += ["| Case | Category | Expected | Actual | Path OK | Escalation reasons | Trace |",
                  "|---|---|---|---|---|---|---|"]
        for e in failed:
            trace = f"[trace]({e.trace_url})" if e.trace_url else "-"
            path_ok = "pass" if e.path_correct else "FAIL"
            reasons = "; ".join(e.escalation_reasons) or "-"
            lines.append(
                f"| {e.case_id} | {e.category} | {e.expected_outcome} | {e.actual_outcome} "
                f"| {path_ok} | {reasons} | {trace} |"
            )

    rows = _regression_rows(metrics, previous)
    lines += ["", "## Regression vs previous run", ""]
    if not rows:
        lines.append("No previous run to compare against."
                     if previous is None else "No metric changed since the previous run.")
    else:
        lines += ["| Metric | Previous | Current | Δ |", "|---|---|---|---|"]
        for name, prev_v, cur_v, delta in rows:
            arrow = "▲" if delta > 0 else "▼"
            lines.append(f"| {name} | {prev_v:.3f} | {cur_v:.3f} | {arrow} {delta:+.3f} |")

    lines += ["", "## All cases", "",
              "| Case | Category | Expected | Actual | Escalated | Citations |",
              "|---|---|---|---|---|---|"]
    for e in evals:
        mark = "pass" if e.outcome_correct else "FAIL"
        lines.append(f"| {mark} {e.case_id} | {e.category} | {e.expected_outcome} | "
                     f"{e.actual_outcome} | {'yes' if e.actual_escalation else 'no'} | "
                     f"{len(e.cited)} |")
    lines += ["", "---", "",
              "Thresholds are justified in `docs/eval-methodology.md`. The policy-conflict "
              "escalation gate is 1.0 because silently resolving an unresolved policy "
              "question is the one unforgivable failure in a regulated deployment.", ""]
    return "\n".join(lines)


def build_html(markdown: str, status: str) -> str:
    colour = "#1b5e20" if status == "GO" else "#b71c1c"
    body = []
    in_table = False
    for line in markdown.splitlines():
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue
            tag = "th" if not in_table else "td"
            if not in_table:
                body.append("<table>")
                in_table = True
            body.append("<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>")
            continue
        if in_table:
            body.append("</table>")
            in_table = False
        if line.startswith("# "):
            body.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("## "):
            body.append(f"<h2>{line[3:]}</h2>")
        elif line.strip() == "---":
            body.append("<hr>")
        elif line.strip():
            body.append(f"<p>{line}</p>")
    if in_table:
        body.append("</table>")
    html_body = "\n".join(body).replace("**", "")
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>process-twin readiness report</title>
<style>
 body {{ font-family: system-ui, sans-serif; max-width: 1080px; margin: 2rem auto;
        padding: 0 1.5rem; color: #222; line-height: 1.5; }}
 h1 {{ border-bottom: 3px solid {colour}; padding-bottom: .4rem; }}
 h1 + p strong, h1 + p {{ font-size: 1.15rem; color: {colour}; font-weight: 700; }}
 h2 {{ margin-top: 2rem; color: #333; }}
 table {{ border-collapse: collapse; width: 100%; margin: .8rem 0 1.4rem; font-size: 14px; }}
 th, td {{ border: 1px solid #ddd; padding: 7px 10px; text-align: left; }}
 th {{ background: #f4f6f8; }}
 tr:nth-child(even) td {{ background: #fafbfc; }}
 hr {{ border: none; border-top: 1px solid #eee; margin: 2rem 0; }}
</style></head><body>
{html_body}
</body></html>"""


def generate(evals: list[CaseEvaluation], out_dir: Path | None = None) -> Path:
    metrics = compute_metrics(evals)
    status, failures = verdict(metrics)
    sha = git_sha()
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")  # noqa: UP017
    run_dir = out_dir or (REPORTS_DIR / f"{datetime.now(timezone.utc):%Y-%m-%d}_{sha}")  # noqa: UP017
    run_dir.mkdir(parents=True, exist_ok=True)

    previous = _previous_run(run_dir)
    markdown = build_markdown(evals, metrics, status, failures, previous, sha, generated)
    (run_dir / "report.md").write_text(markdown, encoding="utf-8")
    (run_dir / "report.html").write_text(build_html(markdown, status), encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps({
        "verdict": status, "failures": failures, "git_sha": sha, "generated": generated,
        "metrics": [m.model_dump() for m in metrics],
        "cases": [e.model_dump() for e in evals],
    }, indent=2), encoding="utf-8")
    return run_dir
