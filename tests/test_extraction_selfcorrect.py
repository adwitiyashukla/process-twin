"""The self-correction loop - the most reused pattern in the project."""

import json

from process_twin.extraction.extractor import ExtractionOutcome, extract_batch, extract_source

VALID = json.dumps({
    "elements": [{
        "element_type": "step",
        "name": "verify identity documents",
        "description": "Check the applicant's identity documents.",
        "actor": "human",
        "source_spans": [{"source_type": "policy", "ref": "FFIEC-CIP-¶2", "quote": "verify"}],
        "extractor_confidence": 0.9,
    }]
})
INVALID_ENUM = VALID.replace('"step"', '"stepp"')
INVALID_EXTRA = json.dumps({"elements": [{"element_type": "step", "name": "x",
                                          "description": "y", "hallucinated": 1,
                                          "source_spans": [{"source_type": "policy", "ref": "A"}],
                                          "extractor_confidence": 0.5}]})
ITEMS = [("FFIEC-CIP-¶2", "The bank must verify the identity of each customer.")]


class ScriptedModel:
    """Returns scripted responses in order; records the prompts it was given."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def __call__(self, system: str, user: str) -> str:
        self.prompts.append(user)
        return self.responses.pop(0)


def test_first_try_success_makes_one_call(tmp_path):
    model = ScriptedModel([VALID])
    out = extract_batch(ITEMS, "policy", model, dead_letter_dir=tmp_path)
    assert out.attempts == 1 and not out.dead_lettered
    assert out.elements[0].name == "verify identity documents"


def test_fail_twice_then_succeed_feeds_errors_back(tmp_path):
    model = ScriptedModel([INVALID_ENUM, INVALID_EXTRA, VALID])
    out = extract_batch(ITEMS, "policy", model, dead_letter_dir=tmp_path)
    assert out.attempts == 3 and not out.dead_lettered
    assert "element_type" in model.prompts[1] and "stepp" in model.prompts[1]
    assert "hallucinated" in model.prompts[2]
    assert list(tmp_path.iterdir()) == []


def test_exhaustion_dead_letters_and_continues(tmp_path):
    model = ScriptedModel([INVALID_ENUM] * 3)
    out = extract_batch(ITEMS, "policy", model, max_retries=3, dead_letter_dir=tmp_path)
    assert out.dead_lettered and out.attempts == 3 and out.elements == []
    dl = json.loads(next(tmp_path.glob("policy-*.json")).read_text(encoding="utf-8"))
    assert dl["item_refs"] == ["FFIEC-CIP-¶2"]
    assert len(dl["error_chain"]) == 3


def test_markdown_fences_are_tolerated(tmp_path):
    model = ScriptedModel([f"```json\n{VALID}\n```"])
    out = extract_batch(ITEMS, "policy", model, dead_letter_dir=tmp_path)
    assert out.attempts == 1 and out.elements


def test_extract_source_caches_and_reuses(tmp_path):
    model = ScriptedModel([VALID])
    first = extract_source("probe", ITEMS, "policy", cache_dir=tmp_path, model_call=model)
    assert len(first) == 1 and (tmp_path / "probe.jsonl").exists()
    second = extract_source("probe", ITEMS, "policy", cache_dir=tmp_path, model_call=model)
    assert [e.model_dump() for e in second] == [e.model_dump() for e in first]


def test_outcome_schema_is_strict():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ExtractionOutcome(elements=[], attempts=1, surprise_field=True)
