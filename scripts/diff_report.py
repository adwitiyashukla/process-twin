"""Demo 1 as a CLI: the tacit-vs-written diff as Markdown."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DERIVED = Path("data/derived")
SEV_ORDER = {"high": 0, "medium": 1, "low": 2}
SEV_BADGE = {"high": "high high", "medium": "medium medium", "low": "low low"}


def build_markdown() -> str:
    deltas = json.loads((DERIVED / "deltas.json").read_text(encoding="utf-8"))
    canonicals = {c["id"]: c for c in
                  json.loads((DERIVED / "canonicals.json").read_text(encoding="utf-8"))}
    score = json.loads((DERIVED / "ledger_score.json").read_text(encoding="utf-8"))
    deltas.sort(key=lambda d: (SEV_ORDER[d["severity"]], d["id"]))

    lines = [
        "# Tacit-vs-written diff report",
        "",
        f"{len(deltas)} divergences between written policy and actual practice. "
        f"Detection vs frozen ground-truth ledger: precision {score['precision']:.2f}, "
        f"recall {score['recall']:.2f}.",
        "",
        "| # | Kind | Severity | Divergence | Seen in cases | Recommendation |",
        "|---|------|----------|------------|---------------|----------------|",
    ]
    for d in deltas:
        support = f"{d['support_count']}/60" if d["support_count"] else "-"
        lines.append(
            f"| {d['id']} | {d['kind']} | {SEV_BADGE[d['severity']]} | {d['description']} "
            f"| {support} | {d['recommendation']} |"
        )

    lines += ["", "## Evidence detail", ""]
    for d in deltas:
        about = canonicals.get(d["about_element_id"], {})
        lines += [
            f"### {d['id']} - {d['kind']} ({d['severity']})",
            "",
            d["description"],
            "",
            f"* **About:** {about.get('name', d['about_element_id'])}",
            "* **Written view:** "
            + (', '.join(d['written_view']) or '(policy silent - that is the point)'),
            f"* **Practiced view:** {', '.join(d['practiced_view'])}",
            f"* **Case-log support:** {d['support_count']} of 60 historical cases",
            f"* **Recommendation:** {d['recommendation']}",
            "",
        ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--format", choices=["md"], default="md")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    if not (DERIVED / "deltas.json").exists():
        print("No derived artifacts - run seed_graph first (make seed).")
        return 1
    md = build_markdown()
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
