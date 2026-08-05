"""CI guard for the Temporal determinism rule (brief §8).

Workflow code must contain no LLM calls, clock reads, randomness, or I/O — those belong
in activities, whose results Temporal reads back from history on replay. This is the #1
Temporal interview topic, so the rule is enforced mechanically, not by memory.

Implementation note: the scan walks the AST and inspects CALL TARGETS ONLY. A regex over
raw text flags this very module's own docstring (see FAILURES.md 2026-08-04) — and worse,
a comment explaining the rule would "violate" it. Analyzing calls means we check what the
code DOES, not what it says.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

WORKFLOW_FILE = Path("src/process_twin/durability/workflows.py")

# dotted call target -> why it breaks replay determinism
FORBIDDEN_CALLS = {
    "datetime.now": "clock read (use workflow.now(), or move it into an activity)",
    "datetime.utcnow": "clock read",
    "time.time": "clock read",
    "time.sleep": "blocking sleep (use workflow.sleep)",
    "random.random": "randomness",
    "random.choice": "randomness",
    "random.randint": "randomness",
    "uuid.uuid4": "randomness",
    "open": "file I/O",
    "requests.get": "network I/O",
    "requests.post": "network I/O",
    "httpx.get": "network I/O",
    "httpx.post": "network I/O",
    "anthropic.Anthropic": "LLM client construction (must live in an activity)",
    "GraphDatabase.driver": "database I/O",
}


def dotted_name(node: ast.AST) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def main() -> int:
    tree = ast.parse(WORKFLOW_FILE.read_text(encoding="utf-8"))
    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = dotted_name(node.func)
        for forbidden, reason in FORBIDDEN_CALLS.items():
            if name == forbidden or name.endswith("." + forbidden):
                violations.append(f"line {node.lineno}: {name}() — {reason}")
    if violations:
        print(f"DETERMINISM RULE VIOLATED in {WORKFLOW_FILE}:")
        for v in violations:
            print("  -", v)
        print("\nMove the offending call into durability/activities.py: Temporal replays "
              "workflow code from history, so anything non-deterministic must be recorded "
              "as an activity result instead of recomputed.")
        return 1
    print(f"determinism rule OK — {WORKFLOW_FILE} makes no non-deterministic calls")
    return 0


if __name__ == "__main__":
    sys.exit(main())
