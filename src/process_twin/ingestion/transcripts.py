"""Transcript loader/segmenter (brief §6.1 input side).

Segments are Q&A exchanges with STABLE ids (P1-S3 = persona P1, 3rd exchange): the
graph's InterviewSegment provenance nodes and the delta PRACTICED_VIEW edges point at
these ids, so segmentation must be deterministic given the committed transcripts.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

TRANSCRIPTS_DIR = Path("data/interviews/transcripts")
_INTERVIEWER = re.compile(r"^\*\*Interviewer:\*\*\s*(.+)$")
_SPEAKER = re.compile(r"^\*\*(?!Interviewer)([A-Z][a-z]+):\*\*\s*(.+)$")


class TranscriptSegment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str  # "P1-S3"
    persona_id: str
    persona_name: str
    question: str
    text: str
    quote_span: str = Field(default="")  # first sentence — display handle for evidence UIs


def _first_sentence(text: str) -> str:
    m = re.match(r"(.+?[.!?])\s", text + " ")
    return (m.group(1) if m else text)[:200]


def segment_transcript(path: Path) -> list[TranscriptSegment]:
    persona_id = path.name.split("_", 1)[0]  # "P1_priya_raghavan.md" -> "P1"
    persona_name = " ".join(w.capitalize() for w in path.stem.split("_")[1:])
    segments: list[TranscriptSegment] = []
    question, answer_lines = None, []

    def flush() -> None:
        nonlocal question, answer_lines
        if question and answer_lines:
            text = " ".join(answer_lines).strip()
            seg_id = f"{persona_id}-S{len(segments) + 1}"
            segments.append(TranscriptSegment(
                id=seg_id, persona_id=persona_id, persona_name=persona_name,
                question=question, text=text, quote_span=_first_sentence(text),
            ))
        question, answer_lines = None, []

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if m := _INTERVIEWER.match(line):
            flush()
            question = m.group(1)
        elif m := _SPEAKER.match(line):
            answer_lines.append(m.group(2))
        elif line and answer_lines:  # continuation paragraph of the current answer
            if not line.startswith(("#", "*Synthetic", "<!--")):
                answer_lines.append(line)
    flush()
    return segments


def load_all_transcripts(directory: Path = TRANSCRIPTS_DIR) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []
    for path in sorted(directory.glob("P*_*.md")):
        segments.extend(segment_transcript(path))
    return segments
