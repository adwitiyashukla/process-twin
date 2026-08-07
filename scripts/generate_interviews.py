"""Synthetic interview tooling (brief §4.2)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

INTERVIEWS_DIR = Path("data/interviews")
TRANSCRIPTS_DIR = INTERVIEWS_DIR / "transcripts"

CHECK_PHRASES: dict[str, list[str]] = {
    "D1": ["at 20", "20 percent"],
    "D2": ["renewal receipt"],
    "D3": ["two address mismatches"],
    "D4": ["screening first", "screen first", "screen runs first"],
    "D5": ["60 days"],
    "D6": ["skip the callback", "callback gets skipped", "no callback"],
    "D7": ["verbally before any ticket", "walk over", "walks over"],
    "D8": ["match tolerance"],
    "D9": ["foreign tax id"],
    "D10": ["po box"],
}

AUTHORING_PROMPT = """\
You are generating a SYNTHETIC expert interview for a KYC-onboarding process-mining
project. Persona: {name}, {role}, {tenure} years. Risk attitude: {attitude}.
Speech style: {style}. Answer the interview guide questions below in character.

You MUST naturally voice each of these tacit-knowledge deltas as lived workplace
practice (anecdotes, opinions, defenses) WITHOUT quoting any ledger or naming delta IDs:
{delta_briefs}

Also include 2-3 red herrings: complaints that sound process-y but are NOT process
divergences (tooling slowness, staffing, dashboards). Keep 500-750 words, Q&A format.

Interview guide:
{guide}
"""


def _load_personas() -> dict:
    return yaml.safe_load((INTERVIEWS_DIR / "personas.yaml").read_text(encoding="utf-8"))


def _transcript_for(persona_id: str) -> Path:
    matches = sorted(TRANSCRIPTS_DIR.glob(f"{persona_id}_*.md"))
    if len(matches) != 1:
        raise FileNotFoundError(f"expected exactly one transcript for {persona_id}, got {matches}")
    return matches[0]


def check() -> int:
    spec = _load_personas()
    failures: list[str] = []

    for persona in spec["personas"]:
        text = _transcript_for(persona["id"]).read_text(encoding="utf-8").lower()
        for delta in persona["knows_deltas"]:
            phrases = CHECK_PHRASES[delta]
            if not any(p in text for p in phrases):
                failures.append(
                    f"{persona['id']} ({persona['name']}): {delta} not voiced - "
                    f"expected one of {phrases}"
                )
            else:
                print(f"  [ok] {persona['id']} voices {delta}")

    qa = _transcript_for("P2").read_text(encoding="utf-8").lower()
    fl = _transcript_for("P4").read_text(encoding="utf-8").lower()
    if "reject" not in qa:
        failures.append("D10 conflict: P2 (QA) transcript lacks a reject stance on PO boxes")
    if "accept" not in fl:
        failures.append("D10 conflict: P4 (frontline) transcript lacks an accept stance")

    if failures:
        print("\nCHECK FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nAll ledger deltas voiced by their assigned personas; D10 conflict intact.")
    return 0


def regenerate() -> int:
    spec = _load_personas()
    guide = "\n".join(f"- {q}" for q in spec["interview_guide"])
    for persona in spec["personas"]:
        briefs = "\n".join(
            f"  * {d}: see SYNTHETIC.md ledger row {d}" for d in persona["knows_deltas"]
        )
        print("=" * 78)
        print(AUTHORING_PROMPT.format(
            name=persona["name"], role=persona["role"], tenure=persona["tenure_years"],
            attitude=persona["risk_attitude"], style=persona["speech_style"],
            delta_briefs=briefs, guide=guide,
        ))
    print("=" * 78)
    print("NOTE: regenerating and committing new transcripts REQUIRES re-reviewing the")
    print("ledger and re-running delta-detection evals - frozen ground truth changed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--regenerate", action="store_true")
    args = parser.parse_args()
    return check() if args.check else regenerate()


if __name__ == "__main__":
    sys.exit(main())
