"""Reconstruct a case's full history from the audit log alone (brief §7.6)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, "src")

from process_twin.schemas.audit import AuditLog  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("case_id", nargs="?")
    ap.add_argument("--log", default="data/audit/audit_log.jsonl")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()

    log = AuditLog(Path(args.log))
    intact, problem = log.verify_chain()
    print(f"chain integrity: {'INTACT' if intact else 'BROKEN - ' + str(problem)}")
    if args.verify or not args.case_id:
        return 0 if intact else 1

    events = log.replay(args.case_id)
    if not events:
        print(f"no events for {args.case_id}")
        return 1
    print(f"\nreplay of {args.case_id} ({len(events)} events)\n" + "-" * 72)
    for e in events:
        cites = f"  cites={','.join(e.citations)}" if e.citations else ""
        conf = f"  conf={e.confidence:.2f}" if e.confidence is not None else ""
        print(f"{e.ts}  [{e.actor:6}] {e.event_type:18} {e.step_id:32} {e.decision[:60]}"
              f"{conf}{cites}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
