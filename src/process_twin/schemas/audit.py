"""Append-only, hash-chained audit log (brief §7.6).

Every state transition is one event. Each event carries `prev_event_hash`, so the log is
a chain: altering or deleting any historical event breaks every hash after it, and
`verify_chain()` reports exactly where. Cheap to build, disproportionately valuable in a
regulated domain — you can prove the trail wasn't edited after the fact.

Inputs/outputs are stored as HASHES, not raw payloads: the log proves what was decided
and on what basis without becoming a second copy of customer data.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

GENESIS_HASH = "0" * 64


class AuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ts: str
    case_id: str
    step_id: str
    actor: str  # "agent" | "human" | "system"
    event_type: str
    input_hash: str
    output_hash: str
    decision: str
    citations: list[str] = Field(default_factory=list)
    confidence: float | None = None
    trace_id: str | None = None
    prev_event_hash: str
    event_hash: str = ""

    def compute_hash(self) -> str:
        """Hash every field except event_hash itself, in a stable key order."""
        payload = self.model_dump(exclude={"event_hash"})
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()


def hash_payload(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:32]


class AuditLog:
    """JSONL append-only writer/reader. One file, one chain."""

    def __init__(self, path: Path = Path("data/audit/audit_log.jsonl")):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _last_hash(self) -> str:
        events = self.read_all()
        return events[-1].event_hash if events else GENESIS_HASH

    def append(self, *, case_id: str, step_id: str, actor: str, event_type: str,
               decision: str, citations: list[str] | None = None,
               confidence: float | None = None, input_payload: object = None,
               output_payload: object = None, trace_id: str | None = None) -> AuditEvent:
        event = AuditEvent(
            ts=datetime.now(timezone.utc).isoformat(),  # noqa: UP017
            case_id=case_id, step_id=step_id, actor=actor, event_type=event_type,
            input_hash=hash_payload(input_payload), output_hash=hash_payload(output_payload),
            decision=decision, citations=citations or [], confidence=confidence,
            trace_id=trace_id, prev_event_hash=self._last_hash(),
        )
        event.event_hash = event.compute_hash()
        with self.path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(event.model_dump_json() + "\n")
        return event

    def read_all(self) -> list[AuditEvent]:
        if not self.path.exists():
            return []
        return [AuditEvent.model_validate_json(line)
                for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def verify_chain(self) -> tuple[bool, str | None]:
        """Returns (intact, first_problem). Detects tampering AND deletion."""
        prev = GENESIS_HASH
        for i, event in enumerate(self.read_all()):
            if event.prev_event_hash != prev:
                return False, f"event {i} ({event.case_id}/{event.step_id}): broken link"
            if event.compute_hash() != event.event_hash:
                return False, f"event {i} ({event.case_id}/{event.step_id}): content altered"
            prev = event.event_hash
        return True, None

    def replay(self, case_id: str) -> list[AuditEvent]:
        """Reconstruct one case's full history from the log alone (brief §7.6)."""
        return [e for e in self.read_all() if e.case_id == case_id]
