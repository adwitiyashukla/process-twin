"""CI guard for the Temporal determinism rule."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

WORKFLOW_FILE = Path("src/process_twin/durability/workflows.py")

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
                violations.append(f"line {node.lineno}: {name}() - {reason}")
    if violations:
        print(f"DETERMINISM RULE VIOLATED in {WORKFLOW_FILE}:")
        for v in violations:
            print("  -", v)
        print("\nMove the offending call into durability/activities.py: Temporal replays "
              "workflow code from history, so anything non-deterministic must be recorded "
              "as an activity result instead of recomputed.")
        return 1
    print(f"determinism rule OK - {WORKFLOW_FILE} makes no non-deterministic calls")
    return 0


if __name__ == "__main__":
    sys.exit(main())
