"""Phase-0 acceptance check: run the hello-world atom end to end.

    python scripts/hello_atom.py            # real Haiku call; trace + cost in Langfuse
    python scripts/hello_atom.py --dry-run  # no API key / services needed
"""

from __future__ import annotations

import argparse
import sys

from process_twin.config import get_settings
from process_twin.observability import tracing
from process_twin.runtime.atoms import run_hello_atom


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="skip the real model call")
    args = parser.parse_args()

    settings = get_settings()
    if not args.dry_run and not settings.anthropic_api_key:
        print("No ANTHROPIC_API_KEY in .env — run with --dry-run, or add the key first.")
        return 2

    trace = tracing.start_case_trace("CASE-HELLO", model_tier="fast", phase="0")
    output, cost = run_hello_atom(dry_run=args.dry_run, trace=trace)
    tracing.flush()

    print(output.model_dump_json(indent=2))
    print(f"\nestimated cost: ${cost:.6f}")
    if trace is not None:
        print(f"trace sent to Langfuse -> {settings.langfuse_host} (project: process-twin)")
    else:
        print("Langfuse keys not set -> tracing ran in no-op mode (expected in CI/dry dev).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
