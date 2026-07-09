"""Policy corpus -> clause-level records with STABLE IDs (brief §4.1).

Name kept from the brief's tree; it handles three source kinds, only one of which is PDF:
  * eCFR structured XML (31 CFR 1010.230)   -> IDs like CFR-1010.230(b)(1)(ii)
  * FFIEC manual HTML pages (CIP/CDD/BO)    -> IDs like FFIEC-CDD-¶12
  * FATF R10 interpretive note (PDF)        -> IDs like FATF-R10-IN-¶7

Why IDs come from document structure, never chunk offsets: the citation guardrail (§7.3)
and every eval `must_cite` check compare against these strings. Re-parsing identical
source bytes MUST yield byte-identical output — enforced by tests. A clause that grows
past the size cap splits deterministically with suffixed IDs (…¶3a, …¶3b).
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict

# ~400 tokens ≈ 1600 chars: citations must map to a human-checkable span, so we split
# oversized clauses rather than embed walls of text (brief §4.1).
MAX_CLAUSE_CHARS = 1600

_ROMAN = {
    "i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x",
    "xi", "xii", "xiii", "xiv", "xv",
}


class ClauseRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clause_id: str
    source_doc: str
    section_path: str
    text: str
    page: int | None = None
    checksum: str  # sha256[:16] of normalized text — drift detector across re-fetches


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def make_record(
    clause_id: str, source_doc: str, section_path: str, text: str, page: int | None = None
) -> ClauseRecord:
    text = normalize_text(text)
    return ClauseRecord(
        clause_id=clause_id,
        source_doc=source_doc,
        section_path=section_path,
        text=text,
        page=page,
        checksum=_checksum(text),
    )


# --------------------------------------------------------------------------- eCFR XML

_MARKER_PREFIX = re.compile(r"^\s*((?:\([a-zA-Z0-9]{1,4}\))+)")
_MARKER_EACH = re.compile(r"\(([a-zA-Z0-9]{1,4})\)")


class _CfrHierarchy:
    """Tracks (letter)(number)(roman) nesting for inline CFR paragraph markers.

    The classic ambiguity: after (h) comes (i) — a LETTER, even though 'i' is also a
    roman numeral. Rule: a marker that continues the letter sequence wins over the
    roman reading; romans are only accepted while a numbered level is open.
    (This exact case exists in 31 CFR 1010.230, which has paragraphs (a) through (j).)
    """

    def __init__(self) -> None:
        self.letter: str | None = None
        self.number: str | None = None
        self.roman: str | None = None

    def _next_letter(self) -> str | None:
        return chr(ord(self.letter) + 1) if self.letter and self.letter < "z" else None

    def classify(self, marker: str) -> str | None:
        if marker.isdigit():
            return "number"
        low = marker.lower()
        if marker.islower():
            if marker == self._next_letter():
                return "letter"  # (h) -> (i): letter continuation beats roman reading
            if low in _ROMAN and self.number is not None:
                return "roman"
            if len(marker) == 1 or (self.letter is None and low not in _ROMAN):
                return "letter"
            return "roman" if low in _ROMAN else "letter"
        return None  # upper-case / unexpected — caller warns and treats as continuation

    def apply(self, marker: str) -> bool:
        kind = self.classify(marker)
        if kind == "letter":
            self.letter, self.number, self.roman = marker, None, None
        elif kind == "number":
            self.number, self.roman = marker, None
        elif kind == "roman":
            self.roman = marker
        else:
            return False
        return True

    def clause_id(self, section: str) -> str:
        parts = "".join(f"({m})" for m in (self.letter, self.number, self.roman) if m)
        return f"CFR-{section}{parts}"


def parse_ecfr_xml(xml_bytes: bytes, section: str = "1010.230") -> list[ClauseRecord]:
    """eCFR versioner XML -> one record per designated paragraph.

    Structured XML instead of PDF scraping: the (b)(1)(ii) hierarchy is in the document
    itself, so stable IDs fall out by construction (docs/architecture.md, phase 1).
    """
    import xml.etree.ElementTree as ET

    root = ET.fromstring(xml_bytes)
    section_divs = [
        div for div in root.iter("DIV8") if section in (div.get("N") or "").replace(" ", "")
    ]
    paras: list[tuple[str, str]] = []  # (clause_id, text) in document order
    hier = _CfrHierarchy()
    warnings: list[str] = []

    for div in section_divs or [root]:
        for p in div.iter():
            if p.tag not in {"P", "FP"}:
                continue
            text = normalize_text("".join(p.itertext()))
            if not text:
                continue
            m = _MARKER_PREFIX.match(text)
            if m:
                ok = all(hier.apply(marker) for marker in _MARKER_EACH.findall(m.group(1)))
                if not ok:
                    warnings.append(f"unclassifiable marker in: {text[:60]}…")
                paras.append((hier.clause_id(section), text))
            elif paras:
                cid, prev = paras[-1]  # undesignated paragraph -> continuation of current
                paras[-1] = (cid, f"{prev} {text}")
            else:
                paras.append((f"CFR-{section}", text))

    for w in warnings:
        print(f"  [warn] ecfr: {w}", file=sys.stderr)

    merged: dict[str, str] = {}
    order: list[str] = []
    for cid, text in paras:
        if cid in merged:  # same designation continued across <P> tags
            merged[cid] = f"{merged[cid]} {text}"
        else:
            merged[cid] = text
            order.append(cid)

    return [
        make_record(cid, f"31 CFR {section} (FinCEN CDD Final Rule)", f"§{section}", merged[cid])
        for cid in order
    ]


# --------------------------------------------------------------------------- FFIEC HTML

_NOISE_TAGS = {"script", "style", "nav", "header", "footer", "aside", "form", "button"}


def parse_ffiec_html(html: str, section_code: str, section_title: str) -> list[ClauseRecord]:
    """FFIEC BSA/AML manual page -> FFIEC-<CODE>-¶n records, numbered in document order.

    ¶ numbering is stable because it derives from the page's paragraph sequence; the
    checksum field catches upstream edits (a re-fetch that changes text shows up as a
    checksum diff, reviewed before re-indexing — IDs never silently re-point).
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(_NOISE_TAGS):
        tag.decompose()
    main = soup.find("main") or soup.find(id=re.compile("main|content", re.I)) or soup.body
    if main is None:
        return []

    records: list[ClauseRecord] = []
    seen: set[str] = set()
    n = 0
    for el in main.find_all(["p", "li"]):
        text = normalize_text(el.get_text(" "))
        if len(text) < 60 or text in seen:  # drop nav crumbs, dedupe boilerplate
            continue
        seen.add(text)
        n += 1
        records.append(
            make_record(
                f"FFIEC-{section_code}-¶{n}",
                "FFIEC BSA/AML Examination Manual",
                section_title,
                text,
            )
        )
    return records


# --------------------------------------------------------------------------- FATF PDF

_FATF_PARA = re.compile(r"^\s*(\d{1,2})\.\s+", re.M)


def parse_fatf_pdf(pdf_bytes: bytes, page_range: tuple[int, int]) -> list[ClauseRecord]:
    """FATF R10 interpretive note pages -> FATF-R10-IN-¶<n> records.

    IDs use the note's own printed paragraph numbers (not a running counter), so a
    slightly-off page range shifts coverage but never renumbers existing clauses.
    """
    import io

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    lo, hi = page_range
    chunks: list[tuple[int, str]] = []
    for idx in range(max(0, lo - 1), min(hi, len(reader.pages))):
        chunks.append((idx + 1, reader.pages[idx].extract_text() or ""))

    records: list[ClauseRecord] = []
    for page_no, text in chunks:
        pieces = _FATF_PARA.split(text)
        # pieces = [preamble, num1, body1, num2, body2, ...]
        for num, body in zip(pieces[1::2], pieces[2::2], strict=False):
            body = normalize_text(body)
            if len(body) < 40:
                continue
            records.append(
                make_record(
                    f"FATF-R10-IN-¶{num}",
                    "FATF Recommendation 10 — Interpretive Note",
                    "Customer Due Diligence",
                    body,
                    page=page_no,
                )
            )
    return records


# --------------------------------------------------------------------------- shared

def split_long_clauses(records: list[ClauseRecord]) -> list[ClauseRecord]:
    """Deterministic split of oversized clauses with suffixed IDs (…¶3a, …¶3b)."""
    out: list[ClauseRecord] = []
    for rec in records:
        if len(rec.text) <= MAX_CLAUSE_CHARS:
            out.append(rec)
            continue
        sentences = re.split(r"(?<=[.;:])\s+", rec.text)
        chunks: list[str] = []
        current = ""
        for s in sentences:
            if current and len(current) + len(s) + 1 > MAX_CLAUSE_CHARS:
                chunks.append(current)
                current = s
            else:
                current = f"{current} {s}".strip()
        if current:
            chunks.append(current)
        for i, chunk in enumerate(chunks):
            suffix = chr(ord("a") + i)
            out.append(
                make_record(
                    f"{rec.clause_id}{suffix}", rec.source_doc, rec.section_path, chunk, rec.page
                )
            )
    return out


def write_clauses_jsonl(records: list[ClauseRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for rec in records:  # document order preserved; determinism comes from the source
            f.write(json.dumps(rec.model_dump(), ensure_ascii=False, sort_keys=True) + "\n")


def read_clauses_jsonl(path: Path) -> list[ClauseRecord]:
    with path.open(encoding="utf-8") as f:
        return [ClauseRecord.model_validate_json(line) for line in f if line.strip()]


def main() -> int:
    """Process everything present in data/policies/raw/ per the fetch manifest."""
    from process_twin.config import get_settings

    raw = get_settings().data_dir / "policies" / "raw"
    processed = get_settings().data_dir / "policies" / "processed"
    manifest_path = raw / "checksums.json"
    if not manifest_path.exists():
        print("No raw corpus found. Run `make fetch` first (scripts/fetch_policies.py).")
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    total = 0
    for name, meta in manifest["sources"].items():
        src_path = raw / meta["filename"]
        if not src_path.exists():
            print(f"  [skip] {name}: {meta['filename']} missing")
            continue
        kind = meta["kind"]
        if kind == "ecfr":
            recs = parse_ecfr_xml(src_path.read_bytes(), meta["section"])
        elif kind == "html":
            recs = parse_ffiec_html(
                src_path.read_text(encoding="utf-8", errors="replace"),
                meta["section_code"],
                meta["title"],
            )
        elif kind == "pdf":
            recs = parse_fatf_pdf(src_path.read_bytes(), tuple(meta["pages"]))
        else:
            print(f"  [skip] {name}: unknown kind {kind}")
            continue
        recs = split_long_clauses(recs)
        out = processed / f"{name}.jsonl"
        write_clauses_jsonl(recs, out)
        total += len(recs)
        sample = recs[0].clause_id if recs else "—"
        print(f"  [ok] {name}: {len(recs)} clauses -> {out} (first: {sample})")
        if len(recs) < 5:
            print(f"  [WARNING] {name}: suspiciously few clauses — inspect the raw file")
    print(f"Done: {total} clauses total.")
    return 0 if total else 1


if __name__ == "__main__":
    sys.exit(main())
