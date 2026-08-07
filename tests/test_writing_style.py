"""Keeps characters that read as machine-generated out of the repo."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent

BANNED = {
    "—": "em dash, use a plain hyphen",
    "–": "en dash, use a plain hyphen",
    "−": "minus sign, use a plain hyphen",
    "✅": "check mark emoji, write the word",
    "❌": "cross mark emoji, write the word",
    "⚠": "warning emoji, write the word",
    "\U0001f512": "lock emoji, write the word",
    "\U0001f534": "red circle emoji, write the word",
    "\U0001f7e0": "orange circle emoji, write the word",
    "\U0001f7e1": "yellow circle emoji, write the word",
    "⏳": "hourglass emoji, write the word",
    "≥": "greater-or-equal sign, write >=",
    "≤": "less-or-equal sign, write <=",
    "·": "middle dot, use a comma",
    "→": "arrow, write the word",
    "▲": "up triangle, write the word",
    "▼": "down triangle, write the word",
}

ALLOWED_NOTE = """
These stay, because each one carries meaning:
  ¶  paragraph marker inside clause ids, for example FFIEC-CDD-¶12
  §  section reference in a real policy citation
"""

SEARCH_DIRS = ["src", "tests", "scripts", "docs", "data", "explorer", ".github"]
SEARCH_FILES = ["README.md", "FAILURES.md", "Makefile", "pyproject.toml",
                "docker-compose.yml", ".gitignore", ".env.example"]
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".ico", ".zip", ".bundle"}
SKIP_NAMES = {"test_writing_style.py"}


def repo_text_files() -> list[Path]:
    paths = [ROOT / name for name in SEARCH_FILES]
    for directory in SEARCH_DIRS:
        target = ROOT / directory
        if target.exists():
            paths.extend(p for p in target.rglob("*") if p.is_file())
    return [
        p for p in paths
        if p.exists() and p.suffix.lower() not in SKIP_SUFFIXES and p.name not in SKIP_NAMES
    ]


@pytest.mark.parametrize("char,reason", list(BANNED.items()))
def test_banned_character_absent(char, reason):
    offenders = []
    for path in repo_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue
        if char in text:
            line = next((i for i, ln in enumerate(text.splitlines(), 1) if char in ln), 0)
            offenders.append(f"{path.relative_to(ROOT)}:{line}")
    assert not offenders, f"found U+{ord(char):04X}, {reason}. In: {', '.join(offenders[:8])}"


def test_clause_id_marker_survives():
    """The paragraph mark in clause ids must stay, citation checking depends on it."""
    atoms = (ROOT / "src/process_twin/runtime/atoms.py").read_text(encoding="utf-8")
    assert "¶" in atoms


SPEC_REF = re.compile(r"brief\s*§|ground rule \d|\(§\d|the brief", re.IGNORECASE)

CODE_DIRS = ["src", "scripts", "tests", "explorer", ".github"]
CODE_FILES = ["pyproject.toml", "Makefile", "docker-compose.yml", ".env.example",
              "data/golden_cases/suite.yaml", "data/policies/probes.yaml",
              "data/interviews/personas.yaml", "data/interviews/ledger.yaml"]


def code_files() -> list[Path]:
    paths = [ROOT / name for name in CODE_FILES]
    for directory in CODE_DIRS:
        target = ROOT / directory
        if target.exists():
            paths.extend(p for p in target.rglob("*") if p.is_file())
    return [
        p for p in paths
        if p.exists() and p.suffix.lower() not in SKIP_SUFFIXES
        and p.name not in SKIP_NAMES
        and "fixtures" not in p.relative_to(ROOT).parts
        and "__pycache__" not in p.relative_to(ROOT).parts
    ]


def test_the_style_scan_actually_reaches_the_repo():
    """Every check in this file passes trivially on an empty file list."""
    assert len(code_files()) > 50
    assert len(repo_text_files()) > 50


def test_no_reference_to_an_external_spec():
    offenders = []
    for path in code_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if SPEC_REF.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{i}")
    assert not offenders, (
        "a reader cannot see any document this points at. In: " + ", ".join(offenders[:8])
    )


def test_no_docstring_stops_mid_sentence():
    """An earlier cleanup truncated one-line docstrings. This stops that recurring."""
    dangling = re.compile(r'^\s*""".*(,|;|:|\b(the|a|an|and|of|to|with|that|is))"""$')
    offenders = []
    for path in code_files():
        if path.suffix != ".py":
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if dangling.match(line):
                offenders.append(f"{path.relative_to(ROOT)}:{i}")
    assert not offenders, f"docstring ends mid-sentence. In: {', '.join(offenders[:8])}"
