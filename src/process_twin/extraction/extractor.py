"""Per-source LLM extraction with the MANDATORY self-correction loop (brief §6.1).

The loop — call → Pydantic-validate → on ValidationError re-prompt with the error text
and the offending output → max N attempts → dead-letter and continue — is the single
most reused pattern in this project: runtime guardrails (§7.3) import THIS function
rather than reimplementing it. Every retry is a Langfuse span event; every dead-letter
is FAILURES.md material.

Cost discipline (ground rule 6): extraction runs on the cheap tier by default;
`--model-tier reasoning` exists to produce the quality-vs-cost comparison data point.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from process_twin.config import get_settings
from process_twin.observability import tracing
from process_twin.schemas.process import ProcessElement

ModelCall = Callable[[str, str], str]  # (system, user) -> raw text


class ElementBatch(BaseModel):
    """Top-level shape the model must return: {"elements": [...]}."""

    model_config = ConfigDict(extra="forbid")
    elements: list[ProcessElement] = Field(default_factory=list)


class ExtractionOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")
    elements: list[ProcessElement] = Field(default_factory=list)
    attempts: int = 0
    dead_lettered: bool = False


SYSTEM_TEMPLATE = """\
You extract process knowledge from {source_desc} for a KYC/CDD customer-onboarding
process twin. Return ONLY a JSON object: {{"elements": [ProcessElement, ...]}}.

ProcessElement fields:
  element_type: one of "step" | "control" | "exception" | "evidence_requirement" | "escalation"
  name: short canonical-ish verb phrase (e.g. "verify identity documents")
  description: one-two sentences, faithful to the source
  actor: "human" | "agent" | "system" | null
  preconditions, evidence_required, controls_referenced, exception_triggers: string lists
  sequence_hint: integer order of the element within this source, or null
  attributes: object of named parameters found in the text, values as strings —
    use these exact keys when the concept appears:
      bo_threshold_pct (beneficial-ownership identification threshold),
      bo_scrutiny_pct (any stricter operational scrutiny threshold),
      utility_bill_max_age_days, callback_min_activity_usd,
      screening_match_tolerance, edd_trigger
  source_spans: list of {{"source_type": "{source_type}", "ref": "<exact id given>",
    "quote": "<short supporting quote>"}} — refs MUST come from the ids provided
  extractor_confidence: float 0..1

Extract only what the source actually supports. Do NOT invent policy. Ignore complaints
about tooling/staffing that do not describe how the process is performed.\
"""

USER_TEMPLATE = """\
Source items (id :: text):

{items}

Extract the process elements these items support, as {{"elements": [...]}}. JSON only.\
"""

RETRY_TEMPLATE = """\
Your previous output failed schema validation.

Validation errors:
{errors}

Your previous output was:
{previous}

Return the corrected {{"elements": [...]}} JSON object ONLY. Fix every listed error;
change nothing that was already valid.\
"""

SOURCE_DESCRIPTIONS = {
    "policy": "written regulatory policy clauses",
    "interview": "practitioner interview segments (tacit knowledge)",
    "case_log": "historical case records and mined behavioral patterns",
}


def default_model_call(model: str) -> ModelCall:
    """Real Anthropic call. Lazy import so tests/CI never need the SDK loaded."""

    def call(system: str, user: str) -> str:
        import anthropic

        client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)
        msg = client.messages.create(
            model=model, max_tokens=4096, system=system,
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text

    return call


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        raw = raw.rsplit("```", 1)[0]
    return raw.strip()


def extract_batch(
    items: list[tuple[str, str]],  # (ref_id, text)
    source_type: str,
    model_call: ModelCall,
    *,
    max_retries: int | None = None,
    dead_letter_dir: Path | None = None,
    span=None,
) -> ExtractionOutcome:
    """The self-correction loop. Never raises on model failure — dead-letters instead."""
    settings = get_settings()
    max_attempts = (max_retries or settings.max_schema_retries)
    dead_letter_dir = dead_letter_dir or settings.dead_letter_dir

    system = SYSTEM_TEMPLATE.format(
        source_desc=SOURCE_DESCRIPTIONS[source_type], source_type=source_type
    )
    user = USER_TEMPLATE.format(items="\n\n".join(f"{ref} :: {text}" for ref, text in items))

    error_chain: list[str] = []
    previous_raw = ""
    for attempt in range(1, max_attempts + 1):
        prompt = user if attempt == 1 else RETRY_TEMPLATE.format(
            errors=error_chain[-1], previous=previous_raw[:4000]
        )
        raw = model_call(system, prompt)
        previous_raw = raw
        try:
            batch = ElementBatch.model_validate_json(_strip_fences(raw))
        except ValidationError as exc:
            error_chain.append(str(exc))
            if span is not None:  # retries are trace events (§9) — the story of the case
                span.event(name=f"schema_retry_{attempt}", metadata={"error": str(exc)[:500]})
            continue
        return ExtractionOutcome(elements=batch.elements, attempts=attempt)

    # exhausted: dead-letter with the full error chain and CONTINUE the pipeline
    dead_letter_dir.mkdir(parents=True, exist_ok=True)
    dl_path = dead_letter_dir / f"{source_type}-{int(time.time() * 1000)}.json"
    dl_path.write_text(json.dumps({
        "source_type": source_type,
        "item_refs": [ref for ref, _ in items],
        "attempts": max_attempts,
        "error_chain": error_chain,
        "last_output": previous_raw[:8000],
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    return ExtractionOutcome(elements=[], attempts=max_attempts, dead_lettered=True)


def extract_source(
    name: str,
    items: list[tuple[str, str]],
    source_type: str,
    *,
    model_tier: str = "fast",
    batch_size: int = 8,
    cache_dir: Path = Path("data/extracted"),
    force: bool = False,
    model_call: ModelCall | None = None,
    trace=None,
) -> list[ProcessElement]:
    """Batch + cache wrapper. Cache makes seed-graph re-runs free (cost discipline) and,
    once committed post-review, lets a fresh clone seed the graph without an API key."""
    cache_path = cache_dir / f"{name}.jsonl"
    if cache_path.exists() and not force:
        return [
            ProcessElement.model_validate_json(line)
            for line in cache_path.read_text(encoding="utf-8").splitlines() if line.strip()
        ]

    settings = get_settings()
    model = settings.model_fast if model_tier == "fast" else settings.model_reasoning
    call = model_call or default_model_call(model)

    elements: list[ProcessElement] = []
    dead = 0
    for start in range(0, len(items), batch_size):
        chunk = items[start : start + batch_size]
        with tracing.atom_span(trace, f"extract:{name}:{start}") as span:
            outcome = extract_batch(chunk, source_type, call, span=span)
        elements.extend(outcome.elements)
        dead += int(outcome.dead_lettered)

    cache_dir.mkdir(parents=True, exist_ok=True)
    with cache_path.open("w", encoding="utf-8", newline="\n") as f:
        for el in elements:
            f.write(el.model_dump_json() + "\n")
    if dead:
        print(f"  [warn] {name}: {dead} batch(es) dead-lettered -> data/dead_letter/ "
              "(FAILURES.md material)")
    return elements
