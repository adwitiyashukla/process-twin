"""Download the public policy corpus with pinned versions + checksums (brief §4.1).

    python scripts/fetch_policies.py            # fetch all, write checksums.json
    python scripts/fetch_policies.py --verify   # re-hash existing files, report drift
    python scripts/fetch_policies.py --url-override ffiec_cip=https://…   # fix a moved page

Pinning strategy: the CFR text comes from the eCFR versioner API AT A FIXED DATE, so
re-fetches are byte-stable; FFIEC/FATF have no versioned API, so drift is *detected*
(checksum mismatch on --verify) rather than prevented, and reviewed before re-indexing.

NOTE (first local run): FFIEC page slugs and the FATF PDF path occasionally move.
If a fetch 404s, locate the section under https://bsaaml.ffiec.gov/manual (chapter
"Assessing Compliance with BSA Regulatory Requirements") or the consolidated
recommendations PDF on fatf-gafi.org, then pass --url-override name=<new-url> and
log the move in FAILURES.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

RAW_DIR = Path("data/policies/raw")
ECFR_AS_OF = "2026-01-01"  # pinned: reproducible CFR text run-to-run

SOURCES: dict[str, dict] = {
    "cfr_1010_230": {
        "url": (
            f"https://www.ecfr.gov/api/versioner/v1/full/{ECFR_AS_OF}/title-31.xml"
            "?part=1010&section=1010.230"
        ),
        "kind": "ecfr",
        "section": "1010.230",
        "filename": "cfr_1010_230.xml",
        "title": "FinCEN CDD Final Rule — Beneficial Ownership (31 CFR 1010.230)",
    },
    "ffiec_cip": {
        "url": "https://bsaaml.ffiec.gov/manual/AssessingComplianceWithBSARegulatoryRequirements/04",
        "kind": "html",
        "section_code": "CIP",
        "filename": "ffiec_cip.html",
        "title": "FFIEC Manual — Customer Identification Program",
    },
    "ffiec_cdd": {
        "url": "https://bsaaml.ffiec.gov/manual/AssessingComplianceWithBSARegulatoryRequirements/05",
        "kind": "html",
        "section_code": "CDD",
        "filename": "ffiec_cdd.html",
        "title": "FFIEC Manual — Customer Due Diligence",
    },
    "ffiec_bo": {
        "url": "https://bsaaml.ffiec.gov/manual/AssessingComplianceWithBSARegulatoryRequirements/06",
        "kind": "html",
        "section_code": "BO",
        "filename": "ffiec_bo.html",
        "title": "FFIEC Manual — Beneficial Ownership Requirements for Legal Entity Customers",
    },
    "fatf_r10": {
        "url": (
            "https://www.fatf-gafi.org/content/dam/fatf-gafi/recommendations/"
            "FATF%20Recommendations%202012.pdf.coredownload.inline.pdf"
        ),
        "kind": "pdf",
        # Interpretive note to R10 — verify page range on first local run (edition-dependent)
        "pages": [60, 75],
        "filename": "fatf_recommendations.pdf",
        "title": "FATF Recommendation 10 — Interpretive Note (excerpts)",
    },
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def fetch(args: argparse.Namespace) -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    overrides = dict(kv.split("=", 1) for kv in args.url_override)
    manifest = {"ecfr_as_of": ECFR_AS_OF, "fetched_at": None, "sources": {}}
    failures = []

    with httpx.Client(
        follow_redirects=True,
        timeout=90,
        headers={"User-Agent": "process-twin/0.1 (research project; contact in repo)"},
    ) as client:
        for name, meta in SOURCES.items():
            url = overrides.get(name, meta["url"])
            dest = RAW_DIR / meta["filename"]
            try:
                resp = client.get(url)
                resp.raise_for_status()
                dest.write_bytes(resp.content)
                digest = sha256_file(dest)
                manifest["sources"][name] = {**meta, "url": url, "sha256": digest,
                                             "bytes": len(resp.content)}
                print(f"  [ok] {name}: {len(resp.content):,} bytes  sha256={digest[:12]}…")
            except httpx.HTTPError as exc:
                failures.append(name)
                print(f"  [FAIL] {name}: {exc}\n         url: {url}\n"
                      f"         -> find the moved page (see module docstring), then re-run with"
                      f" --url-override {name}=<url>")

    manifest["fetched_at"] = datetime.now(timezone.utc).isoformat()  # noqa: UP017
    (RAW_DIR / "checksums.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nManifest -> {RAW_DIR / 'checksums.json'}")
    if failures:
        print(f"{len(failures)} source(s) failed: {', '.join(failures)}")
        return 1
    return 0


def verify() -> int:
    manifest_path = RAW_DIR / "checksums.json"
    if not manifest_path.exists():
        print("Nothing to verify — run a fetch first.")
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    drift = 0
    for name, meta in manifest["sources"].items():
        path = RAW_DIR / meta["filename"]
        if not path.exists():
            print(f"  [MISSING] {name}")
            drift += 1
            continue
        actual = sha256_file(path)
        if actual != meta["sha256"]:
            print(f"  [DRIFT] {name}: recorded {meta['sha256'][:12]}… actual {actual[:12]}…")
            drift += 1
        else:
            print(f"  [ok] {name}")
    if drift:
        print(f"\n{drift} file(s) drifted — review upstream changes, then re-run `make parse`.")
    return 1 if drift else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--url-override", action="append", default=[], metavar="NAME=URL")
    args = parser.parse_args()
    return verify() if args.verify else fetch(args)


if __name__ == "__main__":
    sys.exit(main())
