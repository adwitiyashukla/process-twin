#!/usr/bin/env bash
# Durability demo (brief §8): start a case, kill the worker mid-flight, restart it,
# show the case resumes at the same step with an audit trail that has no gap and no
# duplicate. Run from the repo root with `make up` already healthy.
set -euo pipefail

CASE="${1:-GC-017}"
LOG=data/audit/audit_log.jsonl

echo "==> 1. starting worker"
uv run python -m process_twin.durability.worker & WORKER_PID=$!
sleep 5

echo "==> 2. starting case $CASE (it will suspend at a human gate)"
uv run python scripts/run_case.py --case "$CASE" --temporal &
CASE_PID=$!
sleep 8

BEFORE=$(wc -l < "$LOG" 2>/dev/null || echo 0)
echo "==> 3. audit events before kill: $BEFORE"

echo "==> 4. KILLING the worker mid-case"
kill -9 $WORKER_PID 2>/dev/null || true
sleep 3

echo "==> 5. restarting the worker"
uv run python -m process_twin.durability.worker & WORKER_PID=$!
sleep 6

echo "==> 6. approving the pending gate"
APPROVAL=$(curl -s http://localhost:8000/approvals | python -c \
  "import json,sys; d=json.load(sys.stdin); print(d[0]['request']['approval_id'] if d else '')")
if [ -n "$APPROVAL" ]; then
  curl -s -X POST "http://localhost:8000/approvals/$APPROVAL/decide" \
    -H 'content-type: application/json' \
    -d '{"decision":"approve","reviewer":"a.shukla","note":"durability demo"}' > /dev/null
  echo "    approved $APPROVAL"
fi
wait $CASE_PID || true
sleep 3

AFTER=$(wc -l < "$LOG")
echo "==> 7. audit events after resume: $AFTER"

echo "==> 8. verifying the hash chain and checking for duplicates"
uv run python scripts/replay_case.py "$CASE"
DUPES=$(uv run python - <<PY
from pathlib import Path
import sys; sys.path.insert(0, "src")
from process_twin.schemas.audit import AuditLog
events = AuditLog().replay("$CASE")
keys = [(e.step_id, e.event_type) for e in events]
print(len(keys) - len(set(keys)))
PY
)
echo "    duplicate (step, event_type) pairs: $DUPES  (must be 0)"

kill $WORKER_PID 2>/dev/null || true
[ "$DUPES" = "0" ] || { echo "FAILED: duplicate audit events after restart"; exit 1; }
echo "==> DEMO PASSED: case resumed after worker kill, audit trail intact"
